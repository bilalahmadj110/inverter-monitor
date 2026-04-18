import sqlite3
import time
import os
import logging
import threading
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

GAP_CAP_SECONDS = 15.0
# On restart, seed time-weighted accumulators with stored averages so the
# day's *_avg columns aren't overwritten with a partial-day value on the
# first flush. One hour of pseudo-weight lets fresh samples catch up but
# keeps the morning's average visible through a midday reboot.
AVG_SEED_TSUM_SECONDS = 3600.0


class PowerStats:
    """
    Manages power statistics storage and retrieval with SQLite.
    Uses in-memory buffer with periodic flush to minimize SD card writes.
    Energy is integrated trapezoidally using the real timestamp delta
    between consecutive readings (with a gap cap to drop stale intervals).
    Averages are time-weighted.
    """
    def __init__(self, db_path='power_stats.db', flush_interval=60):
        self.db_path = db_path
        self.flush_interval = flush_interval
        self.memory_buffer = []
        self.last_flush_time = time.time()
        self.buffer_lock = threading.Lock()
        self.running = True

        self.current_day = self._empty_day_accumulator()
        self.current_day_date = datetime.now().strftime('%Y-%m-%d')

        self.last_sample = None

        self.reading_stats = {
            'total_duration': 0,
            'total_readings': 0,
            'min_duration': float('inf'),
            'max_duration': 0,
            'avg_duration': 0,
        }

        self._init_db()
        self._load_today_stats()

        self.flush_thread = threading.Thread(target=self._periodic_flush, daemon=True)
        self.flush_thread.start()

    @staticmethod
    def _empty_day_accumulator():
        return {
            'solar': {'min': float('inf'), 'max': 0, 'wsum': 0.0, 'tsum': 0.0, 'total_energy': 0.0},
            'grid': {'min': float('inf'), 'max': 0, 'wsum': 0.0, 'tsum': 0.0, 'total_energy': 0.0},
            'load': {'min': float('inf'), 'max': 0, 'wsum': 0.0, 'tsum': 0.0, 'total_energy': 0.0},
            'battery': {
                'min': float('inf'), 'max': 0, 'wsum': 0.0, 'tsum': 0.0,
                'charge_energy': 0.0, 'discharge_energy': 0.0,
            },
            'pf': {'wsum': 0.0, 'tsum': 0.0},
            'temperature': {'max': 0},
        }

    def _init_db(self):
        try:
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir)

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute('''
                CREATE TABLE IF NOT EXISTS power_readings (
                    id INTEGER PRIMARY KEY,
                    timestamp INTEGER NOT NULL,
                    start_timestamp REAL,
                    end_timestamp REAL,
                    solar_power REAL,
                    grid_power REAL,
                    load_power REAL,
                    battery_power REAL,
                    battery_percentage REAL,
                    grid_voltage REAL
                )
                ''')

                readings_cols = {row[1] for row in cursor.execute('PRAGMA table_info(power_readings)')}
                if 'grid_voltage' not in readings_cols:
                    cursor.execute('ALTER TABLE power_readings ADD COLUMN grid_voltage REAL')

                cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_stats (
                    id INTEGER PRIMARY KEY,
                    date TEXT UNIQUE NOT NULL,
                    solar_min REAL, solar_max REAL, solar_avg REAL, solar_energy REAL,
                    grid_min REAL, grid_max REAL, grid_avg REAL, grid_energy REAL,
                    load_min REAL, load_max REAL, load_avg REAL, load_energy REAL,
                    battery_min REAL, battery_max REAL,
                    battery_charge_energy REAL, battery_discharge_energy REAL
                )
                ''')

                cursor.execute('''
                CREATE TABLE IF NOT EXISTS monthly_stats (
                    id INTEGER PRIMARY KEY,
                    month TEXT UNIQUE NOT NULL,
                    solar_energy REAL, grid_energy REAL, load_energy REAL,
                    battery_charge_energy REAL, battery_discharge_energy REAL
                )
                ''')

                cursor.execute('CREATE INDEX IF NOT EXISTS idx_readings_timestamp ON power_readings(timestamp)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_stats(date)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_monthly_month ON monthly_stats(month)')

                existing = {row[1] for row in cursor.execute("PRAGMA table_info(daily_stats)")}
                for col in ('pf_avg REAL', 'temperature_max REAL'):
                    name = col.split()[0]
                    if name not in existing:
                        cursor.execute(f'ALTER TABLE daily_stats ADD COLUMN {col}')

                conn.commit()

            logger.info(f"Database initialized at {self.db_path}")

        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def _load_today_stats(self):
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM daily_stats WHERE date = ?', (today,))
                row = cursor.fetchone()

                if row:
                    keys = row.keys()
                    for source in ('solar', 'grid', 'load', 'battery'):
                        self.current_day[source]['min'] = row[f'{source}_min'] or float('inf')
                        self.current_day[source]['max'] = row[f'{source}_max'] or 0
                        if source != 'battery':
                            self.current_day[source]['total_energy'] = row[f'{source}_energy'] or 0
                        else:
                            self.current_day['battery']['charge_energy'] = row['battery_charge_energy'] or 0
                            self.current_day['battery']['discharge_energy'] = row['battery_discharge_energy'] or 0

                    for source in ('solar', 'grid', 'load'):
                        avg_val = row[f'{source}_avg'] or 0
                        if avg_val > 0:
                            self.current_day[source]['wsum'] = avg_val * AVG_SEED_TSUM_SECONDS
                            self.current_day[source]['tsum'] = AVG_SEED_TSUM_SECONDS

                    if 'pf_avg' in keys and row['pf_avg']:
                        self.current_day['pf']['wsum'] = row['pf_avg'] * AVG_SEED_TSUM_SECONDS
                        self.current_day['pf']['tsum'] = AVG_SEED_TSUM_SECONDS

                    if 'temperature_max' in keys and row['temperature_max'] is not None:
                        self.current_day['temperature']['max'] = row['temperature_max']
                    logger.info("Loaded existing daily stats (averages seeded from DB)")
        except Exception as e:
            logger.error(f"Error loading today's stats: {e}")

    def record_reading(self, metrics, start_time=None, end_time=None):
        """Record a single reading. `metrics` is the enriched dict from inverter_status."""
        try:
            now = time.time()
            timestamp = int(now)
            start_timestamp = start_time or now
            end_timestamp = end_time or now

            today = datetime.now().strftime('%Y-%m-%d')
            if today != self.current_day_date:
                self._rollover_day(today)

            solar_power = metrics['solar']['power']
            grid_power = metrics['grid']['power']
            grid_voltage = metrics['grid'].get('voltage', 0) or 0
            load_power = metrics['load'].get('active_power', metrics['load'].get('power', 0))
            battery_voltage = metrics['battery']['voltage']
            battery_percentage = metrics['battery']['percentage']
            charging_w = metrics['battery']['charging_current'] * battery_voltage
            discharging_w = metrics['battery']['discharge_current'] * battery_voltage
            battery_power = charging_w - discharging_w

            temperature = metrics.get('system', {}).get('temperature', 0) or 0
            power_factor = metrics['load'].get('power_factor', 0) or 0

            record = {
                'timestamp': timestamp,
                'start_timestamp': start_timestamp,
                'end_timestamp': end_timestamp,
                'solar_power': solar_power,
                'grid_power': grid_power,
                'grid_voltage': grid_voltage,
                'load_power': load_power,
                'battery_power': battery_power,
                'battery_percentage': battery_percentage,
            }

            if start_time and end_time:
                duration = end_time - start_time
                self.reading_stats['total_duration'] += duration
                self.reading_stats['total_readings'] += 1
                if duration < self.reading_stats['min_duration']:
                    self.reading_stats['min_duration'] = duration
                if duration > self.reading_stats['max_duration']:
                    self.reading_stats['max_duration'] = duration
                self.reading_stats['avg_duration'] = (
                    self.reading_stats['total_duration'] / self.reading_stats['total_readings']
                )

            self._integrate(
                now=now,
                solar_power=solar_power,
                grid_power=grid_power,
                load_power=load_power,
                charging_w=charging_w,
                discharging_w=discharging_w,
                battery_power=battery_power,
                power_factor=power_factor,
                temperature=temperature,
            )

            with self.buffer_lock:
                self.memory_buffer.append(record)

            if time.time() - self.last_flush_time >= self.flush_interval:
                self.flush_to_disk()

        except Exception as e:
            logger.error(f"Error recording reading: {e}")

    def _integrate(self, now, solar_power, grid_power, load_power,
                   charging_w, discharging_w, battery_power, power_factor, temperature):
        prev = self.last_sample
        self.last_sample = {
            't': now,
            'solar': solar_power,
            'grid': grid_power,
            'load': load_power,
            'charging_w': charging_w,
            'discharging_w': discharging_w,
            'battery_abs': abs(battery_power),
            'pf': power_factor,
        }

        self._update_min_max('solar', solar_power)
        self._update_min_max('grid', grid_power)
        self._update_min_max('load', load_power)
        self._update_min_max('battery', abs(battery_power))

        if temperature > self.current_day['temperature']['max']:
            self.current_day['temperature']['max'] = temperature

        if prev is None:
            return

        dt = now - prev['t']
        if dt <= 0 or dt > GAP_CAP_SECONDS:
            return

        dt_h = dt / 3600.0

        def trap(a, b):
            return (a + b) / 2.0 * dt_h

        self.current_day['solar']['total_energy'] += trap(prev['solar'], solar_power)
        self.current_day['grid']['total_energy'] += trap(prev['grid'], grid_power)
        self.current_day['load']['total_energy'] += trap(prev['load'], load_power)
        self.current_day['battery']['charge_energy'] += trap(prev['charging_w'], charging_w)
        self.current_day['battery']['discharge_energy'] += trap(prev['discharging_w'], discharging_w)

        for src, val in (('solar', solar_power), ('grid', grid_power),
                         ('load', load_power), ('battery', abs(battery_power))):
            avg_val = (prev[src if src != 'battery' else 'battery_abs'] + val) / 2.0
            self.current_day[src]['wsum'] += avg_val * dt
            self.current_day[src]['tsum'] += dt

        if power_factor > 0:
            pf_avg = (prev['pf'] + power_factor) / 2.0 if prev['pf'] > 0 else power_factor
            self.current_day['pf']['wsum'] += pf_avg * dt
            self.current_day['pf']['tsum'] += dt

    def _update_min_max(self, source, value):
        stats = self.current_day[source]
        if value < stats['min'] or stats['min'] == float('inf'):
            stats['min'] = value
        if value > stats['max']:
            stats['max'] = value

    def _rollover_day(self, new_date):
        logger.info(f"Day rollover: {self.current_day_date} -> {new_date}")
        try:
            self.flush_to_disk()
        finally:
            self.current_day = self._empty_day_accumulator()
            self.current_day_date = new_date
            self.last_sample = None

    def flush_to_disk(self):
        with self.buffer_lock:
            if not self.memory_buffer:
                self.last_flush_time = time.time()
                return
            buffer_copy = self.memory_buffer.copy()
            self.memory_buffer = []

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.executemany(
                    '''INSERT INTO power_readings (
                        timestamp, start_timestamp, end_timestamp,
                        solar_power, grid_power, load_power, battery_power, battery_percentage, grid_voltage
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    [(r['timestamp'], r['start_timestamp'], r['end_timestamp'],
                      r['solar_power'], r['grid_power'], r['load_power'],
                      r['battery_power'], r['battery_percentage'], r.get('grid_voltage', 0)) for r in buffer_copy]
                )

                today = self.current_day_date

                def safe_min(val):
                    return 0 if val == float('inf') else val

                def wavg(source):
                    tsum = self.current_day[source]['tsum']
                    return self.current_day[source]['wsum'] / tsum if tsum > 0 else 0

                pf_tsum = self.current_day['pf']['tsum']
                pf_avg = self.current_day['pf']['wsum'] / pf_tsum if pf_tsum > 0 else 0

                cursor.execute('''
                INSERT OR REPLACE INTO daily_stats (
                    date,
                    solar_min, solar_max, solar_avg, solar_energy,
                    grid_min, grid_max, grid_avg, grid_energy,
                    load_min, load_max, load_avg, load_energy,
                    battery_min, battery_max, battery_charge_energy, battery_discharge_energy,
                    pf_avg, temperature_max
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    today,
                    safe_min(self.current_day['solar']['min']),
                    self.current_day['solar']['max'],
                    wavg('solar'),
                    self.current_day['solar']['total_energy'],
                    safe_min(self.current_day['grid']['min']),
                    self.current_day['grid']['max'],
                    wavg('grid'),
                    self.current_day['grid']['total_energy'],
                    safe_min(self.current_day['load']['min']),
                    self.current_day['load']['max'],
                    wavg('load'),
                    self.current_day['load']['total_energy'],
                    safe_min(self.current_day['battery']['min']),
                    self.current_day['battery']['max'],
                    self.current_day['battery']['charge_energy'],
                    self.current_day['battery']['discharge_energy'],
                    pf_avg,
                    self.current_day['temperature']['max'],
                ))

                current_month = today[:7]
                cursor.execute('''
                INSERT OR REPLACE INTO monthly_stats (
                    month, solar_energy, grid_energy, load_energy,
                    battery_charge_energy, battery_discharge_energy
                )
                SELECT
                    strftime('%Y-%m', date),
                    SUM(solar_energy), SUM(grid_energy), SUM(load_energy),
                    SUM(battery_charge_energy), SUM(battery_discharge_energy)
                FROM daily_stats
                WHERE strftime('%Y-%m', date) = ?
                GROUP BY strftime('%Y-%m', date)
                ''', (current_month,))

                conn.commit()

            self.last_flush_time = time.time()
            logger.debug(f"Flushed {len(buffer_copy)} records to disk")

        except Exception as e:
            logger.error(f"Failed to flush to disk: {e}")
            with self.buffer_lock:
                self.memory_buffer = buffer_copy + self.memory_buffer

    def _periodic_flush(self):
        while self.running:
            time.sleep(self.flush_interval)
            try:
                self.flush_to_disk()
            except Exception as e:
                logger.error(f"Error in periodic flush: {e}")

    def get_daily_stats(self, day=None):
        if day is None:
            day = datetime.now().strftime('%Y-%m-%d')
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM daily_stats WHERE date = ?', (day,))
                row = cursor.fetchone()
                if row:
                    return dict(row)
                if day == datetime.now().strftime('%Y-%m-%d'):
                    return self._get_current_day_dict(day)
                return self._get_empty_day_stats(day)
        except Exception as e:
            logger.error(f"Error getting daily stats: {e}")
            return None

    def _get_current_day_dict(self, day):
        def safe_min(val):
            return 0 if val == float('inf') else val

        def wavg(source):
            tsum = self.current_day[source]['tsum']
            return self.current_day[source]['wsum'] / tsum if tsum > 0 else 0

        pf_tsum = self.current_day['pf']['tsum']
        pf_avg = self.current_day['pf']['wsum'] / pf_tsum if pf_tsum > 0 else 0

        return {
            'date': day,
            'solar_min': safe_min(self.current_day['solar']['min']),
            'solar_max': self.current_day['solar']['max'],
            'solar_avg': wavg('solar'),
            'solar_energy': self.current_day['solar']['total_energy'],
            'grid_min': safe_min(self.current_day['grid']['min']),
            'grid_max': self.current_day['grid']['max'],
            'grid_avg': wavg('grid'),
            'grid_energy': self.current_day['grid']['total_energy'],
            'load_min': safe_min(self.current_day['load']['min']),
            'load_max': self.current_day['load']['max'],
            'load_avg': wavg('load'),
            'load_energy': self.current_day['load']['total_energy'],
            'battery_min': safe_min(self.current_day['battery']['min']),
            'battery_max': self.current_day['battery']['max'],
            'battery_charge_energy': self.current_day['battery']['charge_energy'],
            'battery_discharge_energy': self.current_day['battery']['discharge_energy'],
            'pf_avg': pf_avg,
            'temperature_max': self.current_day['temperature']['max'],
        }

    def _get_empty_day_stats(self, day):
        return {
            'date': day,
            'solar_min': 0, 'solar_max': 0, 'solar_avg': 0, 'solar_energy': 0,
            'grid_min': 0, 'grid_max': 0, 'grid_avg': 0, 'grid_energy': 0,
            'load_min': 0, 'load_max': 0, 'load_avg': 0, 'load_energy': 0,
            'battery_min': 0, 'battery_max': 0, 'battery_charge_energy': 0, 'battery_discharge_energy': 0,
            'pf_avg': 0, 'temperature_max': 0,
        }

    def get_monthly_stats(self, month=None):
        if month is None:
            month = datetime.now().strftime('%Y-%m')
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM monthly_stats WHERE month = ?', (month,))
                row = cursor.fetchone()
                if row:
                    return dict(row)
                return {
                    'month': month,
                    'solar_energy': 0, 'grid_energy': 0, 'load_energy': 0,
                    'battery_charge_energy': 0, 'battery_discharge_energy': 0,
                }
        except Exception as e:
            logger.error(f"Error getting monthly stats: {e}")
            return None

    def get_yearly_stats(self, year=None):
        if year is None:
            year = datetime.now().strftime('%Y')
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                SELECT
                    SUM(solar_energy) as solar_energy,
                    SUM(grid_energy) as grid_energy,
                    SUM(load_energy) as load_energy,
                    SUM(battery_charge_energy) as battery_charge_energy,
                    SUM(battery_discharge_energy) as battery_discharge_energy
                FROM monthly_stats WHERE month LIKE ?
                ''', (f'{year}-%',))
                row = cursor.fetchone()
                if row and row['solar_energy'] is not None:
                    result = dict(row)
                    result['year'] = year
                    return result
                return {
                    'year': year,
                    'solar_energy': 0, 'grid_energy': 0, 'load_energy': 0,
                    'battery_charge_energy': 0, 'battery_discharge_energy': 0,
                }
        except Exception as e:
            logger.error(f"Error getting yearly stats: {e}")
            return None

    def get_all_stats(self):
        return {
            'day': self.get_daily_stats(),
            'month': self.get_monthly_stats(),
            'year': self.get_yearly_stats(),
        }

    def get_summary(self, day=None):
        """Day summary in kWh + derived self-sufficiency and solar-fraction of load."""
        stats = self.get_daily_stats(day)
        if not stats:
            return None

        def kwh(wh):
            return round((wh or 0) / 1000.0, 3)

        solar_kwh = kwh(stats.get('solar_energy'))
        grid_kwh = kwh(stats.get('grid_energy'))
        load_kwh = kwh(stats.get('load_energy'))
        charge_kwh = kwh(stats.get('battery_charge_energy'))
        discharge_kwh = kwh(stats.get('battery_discharge_energy'))

        self_sufficiency = 0
        if load_kwh > 0:
            self_sufficiency = max(0.0, min(1.0, 1 - (grid_kwh / load_kwh)))
        solar_fraction = 0
        if load_kwh > 0:
            solar_fraction = max(0.0, min(1.0, solar_kwh / load_kwh))

        return {
            'date': stats.get('date'),
            'solar_kwh': solar_kwh,
            'grid_kwh': grid_kwh,
            'load_kwh': load_kwh,
            'battery_charge_kwh': charge_kwh,
            'battery_discharge_kwh': discharge_kwh,
            'solar_peak_w': round(stats.get('solar_max') or 0, 1),
            'load_peak_w': round(stats.get('load_max') or 0, 1),
            'grid_peak_w': round(stats.get('grid_max') or 0, 1),
            'pf_avg': round(stats.get('pf_avg') or 0, 3),
            'temperature_max': round(stats.get('temperature_max') or 0, 1),
            'self_sufficiency': round(self_sufficiency, 3),
            'solar_fraction': round(solar_fraction, 3),
        }

    def get_history(self, days=30):
        """Per-day energy history (kWh)."""
        try:
            days = max(1, min(int(days), 365))
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                SELECT date, solar_energy, grid_energy, load_energy,
                       battery_charge_energy, battery_discharge_energy
                FROM daily_stats
                WHERE date >= date('now', 'localtime', ?)
                ORDER BY date ASC
                ''', (f'-{days - 1} days',))
                rows = cursor.fetchall()

                return [{
                    'date': row['date'],
                    'solar_energy': round((row['solar_energy'] or 0) / 1000, 2),
                    'grid_energy': round((row['grid_energy'] or 0) / 1000, 2),
                    'load_energy': round((row['load_energy'] or 0) / 1000, 2),
                    'battery_charge_energy': round((row['battery_charge_energy'] or 0) / 1000, 2),
                    'battery_discharge_energy': round((row['battery_discharge_energy'] or 0) / 1000, 2),
                } for row in rows]
        except Exception as e:
            logger.error(f"Error getting history: {e}")
            return []

    def recompute_daily_stats(self, day=None):
        """Recompute daily_stats for a given day from raw power_readings (trapezoid rule).
        Useful for fixing rows that were inflated/deflated by earlier bugs or service races.
        If `day` is None, recomputes every day present in power_readings."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                if day:
                    days = [day]
                else:
                    rows = cursor.execute("SELECT DISTINCT date(timestamp, 'unixepoch', 'localtime') FROM power_readings").fetchall()
                    days = [r[0] for r in rows if r[0]]

                updated = []
                for d in days:
                    start_dt = datetime.strptime(d, '%Y-%m-%d')
                    end_dt = start_dt + timedelta(days=1)
                    start_ts = int(start_dt.timestamp())
                    end_ts = int(end_dt.timestamp())
                    rows = cursor.execute('''
                        SELECT timestamp, solar_power, grid_power, load_power, battery_power
                        FROM power_readings
                        WHERE timestamp >= ? AND timestamp < ?
                        ORDER BY timestamp ASC
                    ''', (start_ts, end_ts)).fetchall()

                    solar_wh = grid_wh = load_wh = charge_wh = discharge_wh = 0.0
                    solar_min, solar_max = float('inf'), 0.0
                    grid_min, grid_max = float('inf'), 0.0
                    load_min, load_max = float('inf'), 0.0
                    batt_min, batt_max = float('inf'), 0.0
                    solar_wsum = grid_wsum = load_wsum = 0.0
                    total_dt = 0.0

                    for i in range(len(rows)):
                        ts, s, g, l, b = rows[i]
                        s = s or 0; g = g or 0; l = l or 0; b = b or 0
                        solar_min, solar_max = min(solar_min, s), max(solar_max, s)
                        grid_min, grid_max = min(grid_min, g), max(grid_max, g)
                        load_min, load_max = min(load_min, l), max(load_max, l)
                        batt_min, batt_max = min(batt_min, abs(b)), max(batt_max, abs(b))
                        if i == 0:
                            continue
                        pts, ps, pg, pl, pb = rows[i - 1]
                        dt = ts - pts
                        if dt <= 0 or dt > GAP_CAP_SECONDS:
                            continue
                        dt_h = dt / 3600.0
                        solar_wh += (ps + s) / 2.0 * dt_h
                        grid_wh  += (pg + g) / 2.0 * dt_h
                        load_wh  += (pl + l) / 2.0 * dt_h
                        prev_charge = max(0, pb); curr_charge = max(0, b)
                        prev_disch = max(0, -pb); curr_disch = max(0, -b)
                        charge_wh += (prev_charge + curr_charge) / 2.0 * dt_h
                        discharge_wh += (prev_disch + curr_disch) / 2.0 * dt_h
                        solar_wsum += (ps + s) / 2.0 * dt
                        grid_wsum  += (pg + g) / 2.0 * dt
                        load_wsum  += (pl + l) / 2.0 * dt
                        total_dt += dt

                    if not rows:
                        continue

                    def safe_min(v): return 0 if v == float('inf') else v
                    def avg(wsum): return wsum / total_dt if total_dt > 0 else 0

                    cursor.execute('''
                    INSERT OR REPLACE INTO daily_stats (
                        date, solar_min, solar_max, solar_avg, solar_energy,
                        grid_min, grid_max, grid_avg, grid_energy,
                        load_min, load_max, load_avg, load_energy,
                        battery_min, battery_max, battery_charge_energy, battery_discharge_energy
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        d,
                        safe_min(solar_min), solar_max, avg(solar_wsum), solar_wh,
                        safe_min(grid_min),  grid_max,  avg(grid_wsum),  grid_wh,
                        safe_min(load_min),  load_max,  avg(load_wsum),  load_wh,
                        safe_min(batt_min),  batt_max,  charge_wh, discharge_wh,
                    ))
                    updated.append({'date': d, 'solar_wh': round(solar_wh, 2), 'grid_wh': round(grid_wh, 2), 'load_wh': round(load_wh, 2)})

                conn.commit()

            # Refresh in-memory current_day from DB so live totals line up
            self.current_day = self._empty_day_accumulator()
            self.last_sample = None
            self._load_today_stats()
            return {'updated': updated, 'count': len(updated)}
        except Exception as e:
            logger.error(f"Error recomputing daily stats: {e}")
            return {'updated': [], 'count': 0, 'error': str(e)}

    def get_recent_readings(self, minutes=30, bucket_seconds=None, target_points=200):
        """Return power series for the last N minutes with adaptive server-side bucketing.
        Returns avg/min/max per bucket so the frontend can draw a mean line with a min/max envelope."""
        try:
            minutes = max(1, min(int(minutes), 720))
            total_seconds = minutes * 60
            if bucket_seconds is None:
                bucket_seconds = max(3, total_seconds // max(1, target_points))
            bucket_seconds = max(3, min(int(bucket_seconds), 3600))
            cutoff = int(time.time()) - total_seconds

            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(f'''
                SELECT
                    (timestamp / {bucket_seconds}) * {bucket_seconds} AS bucket,
                    AVG(solar_power)   AS solar_avg,   MIN(solar_power)   AS solar_min,   MAX(solar_power)   AS solar_max,
                    AVG(grid_power)    AS grid_avg,    MIN(grid_power)    AS grid_min,    MAX(grid_power)    AS grid_max,
                    AVG(load_power)    AS load_avg,    MIN(load_power)    AS load_min,    MAX(load_power)    AS load_max,
                    AVG(battery_power) AS battery_avg, MIN(battery_power) AS battery_min, MAX(battery_power) AS battery_max,
                    AVG(battery_percentage) AS battery_percentage,
                    AVG(grid_voltage)  AS grid_voltage
                FROM power_readings
                WHERE timestamp >= ?
                GROUP BY bucket
                ORDER BY bucket ASC
                ''', (cutoff,))
                rows = cursor.fetchall()

            def r(v):
                return round(v or 0, 1)

            return {
                'minutes': minutes,
                'bucket_seconds': bucket_seconds,
                'points': [{
                    'timestamp': row['bucket'],
                    'solar_avg': r(row['solar_avg']),   'solar_min': r(row['solar_min']),   'solar_max': r(row['solar_max']),
                    'grid_avg':  r(row['grid_avg']),    'grid_min':  r(row['grid_min']),    'grid_max':  r(row['grid_max']),
                    'load_avg':  r(row['load_avg']),    'load_min':  r(row['load_min']),    'load_max':  r(row['load_max']),
                    'battery_avg': r(row['battery_avg']), 'battery_min': r(row['battery_min']), 'battery_max': r(row['battery_max']),
                    'battery_percentage': r(row['battery_percentage']),
                    'grid_voltage': r(row['grid_voltage']),
                } for row in rows],
            }
        except Exception as e:
            logger.error(f"Error getting recent readings: {e}")
            return {'minutes': minutes, 'bucket_seconds': 0, 'points': []}

    def get_day_readings(self, date=None, bucket_seconds=60):
        """Per-reading power series for a given day, downsampled to `bucket_seconds` buckets."""
        try:
            day = date or datetime.now().strftime('%Y-%m-%d')
            start_dt = datetime.strptime(day, '%Y-%m-%d')
            end_dt = start_dt + timedelta(days=1)
            start_ts = int(start_dt.timestamp())
            end_ts = int(end_dt.timestamp())
            bucket_seconds = max(10, min(int(bucket_seconds), 600))

            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(f'''
                SELECT
                    (timestamp / {bucket_seconds}) * {bucket_seconds} AS bucket,
                    AVG(solar_power)    AS solar_power,
                    AVG(grid_power)     AS grid_power,
                    AVG(load_power)     AS load_power,
                    AVG(battery_power)  AS battery_power,
                    AVG(battery_percentage) AS battery_percentage,
                    AVG(grid_voltage)   AS grid_voltage
                FROM power_readings
                WHERE timestamp >= ? AND timestamp < ?
                GROUP BY bucket
                ORDER BY bucket ASC
                ''', (start_ts, end_ts))
                rows = cursor.fetchall()
                return {
                    'date': day,
                    'bucket_seconds': bucket_seconds,
                    'points': [{
                        'timestamp': row['bucket'],
                        'solar_power': round(row['solar_power'] or 0, 1),
                        'grid_power': round(row['grid_power'] or 0, 1),
                        'load_power': round(row['load_power'] or 0, 1),
                        'battery_power': round(row['battery_power'] or 0, 1),
                        'battery_percentage': round(row['battery_percentage'] or 0, 1),
                        'grid_voltage': round(row['grid_voltage'] or 0, 1),
                    } for row in rows],
                }
        except Exception as e:
            logger.error(f"Error getting day readings: {e}")
            return {'date': date, 'bucket_seconds': bucket_seconds, 'points': []}

    def get_outages(self, from_date=None, to_date=None, min_voltage=180.0, min_duration_seconds=30):
        """Identify contiguous grid outage windows from power_readings.grid_voltage.
        Returns list of {start, end, duration_seconds} plus a totals dict."""
        try:
            if to_date:
                end_dt = datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1)
            else:
                end_dt = datetime.now() + timedelta(days=1)
            if from_date:
                start_dt = datetime.strptime(from_date, '%Y-%m-%d')
            else:
                start_dt = end_dt - timedelta(days=7)

            start_ts = int(start_dt.timestamp())
            end_ts = int(end_dt.timestamp())

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                SELECT timestamp, grid_voltage
                FROM power_readings
                WHERE timestamp >= ? AND timestamp < ? AND grid_voltage IS NOT NULL
                ORDER BY timestamp ASC
                ''', (start_ts, end_ts))
                rows = cursor.fetchall()

            outages = []
            current_start = None
            last_ts = None
            gap_threshold = 60  # seconds — split if reading gap exceeds this
            for ts, voltage in rows:
                is_down = (voltage or 0) < min_voltage
                if is_down:
                    if current_start is None:
                        current_start = ts
                    last_ts = ts
                else:
                    if current_start is not None and last_ts is not None:
                        duration = last_ts - current_start
                        if duration >= min_duration_seconds:
                            outages.append({
                                'start': current_start,
                                'end': last_ts,
                                'duration_seconds': duration,
                            })
                    current_start = None
                    last_ts = None
                if last_ts is not None and (ts - last_ts) > gap_threshold and is_down:
                    pass  # handled above
            if current_start is not None and last_ts is not None:
                duration = last_ts - current_start
                if duration >= min_duration_seconds:
                    outages.append({
                        'start': current_start,
                        'end': last_ts,
                        'duration_seconds': duration,
                    })

            total_down = sum(o['duration_seconds'] for o in outages)
            total_range = end_ts - start_ts
            return {
                'from': datetime.fromtimestamp(start_ts).strftime('%Y-%m-%d'),
                'to': datetime.fromtimestamp(end_ts - 1).strftime('%Y-%m-%d'),
                'outages': outages,
                'count': len(outages),
                'total_down_seconds': total_down,
                'availability': round(1 - (total_down / total_range), 4) if total_range > 0 else 1.0,
            }
        except Exception as e:
            logger.error(f"Error getting outages: {e}")
            return {'outages': [], 'count': 0, 'total_down_seconds': 0, 'availability': 1.0}

    def get_reading_statistics(self):
        return {
            'avg_duration': self.reading_stats['avg_duration'],
            'min_duration': self.reading_stats['min_duration'] if self.reading_stats['min_duration'] != float('inf') else 0,
            'max_duration': self.reading_stats['max_duration'],
            'total_readings': self.reading_stats['total_readings'],
            'total_duration': self.reading_stats['total_duration'],
        }

    def cleanup(self):
        try:
            self.running = False
            self.flush_to_disk()
            if hasattr(self, 'flush_thread') and self.flush_thread and self.flush_thread.is_alive():
                self.flush_thread.join(timeout=5)
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def __del__(self):
        try:
            self.cleanup()
        except Exception:
            pass

    def get_raw_readings(self, page=1, page_size=25):
        try:
            offset = (page - 1) * page_size
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) as count FROM power_readings')
                total_count = cursor.fetchone()['count']
                cursor.execute('''
                SELECT
                    datetime(timestamp, 'unixepoch', 'localtime') as timestamp_formatted,
                    solar_power,
                    grid_power,
                    load_power,
                    battery_power,
                    battery_percentage,
                    (end_timestamp - start_timestamp) * 1000 as duration_ms,
                    timestamp
                FROM power_readings
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
                ''', (page_size, offset))
                rows = cursor.fetchall()
                data = []
                for row in rows:
                    data.append({
                        'timestamp_formatted': row['timestamp_formatted'],
                        'solar_power': round(row['solar_power'] or 0, 1),
                        'grid_power': round(row['grid_power'] or 0, 1),
                        'grid_voltage': 220,
                        'battery_percentage': round(row['battery_percentage'] or 0, 1),
                        'load_power': round(row['load_power'] or 0, 1),
                        'battery_power': round(row['battery_power'] or 0, 1),
                        'temperature': 35,
                        'duration_ms': round(row['duration_ms'] or 0, 1),
                        'timestamp': row['timestamp'],
                    })
                return data, total_count
        except Exception as e:
            logger.error(f"Error getting raw readings: {e}")
            return [], 0


_instance = None


def get_instance():
    global _instance
    if _instance is None:
        db_path = os.path.join(os.path.dirname(__file__), 'data', 'power_stats.db')
        _instance = PowerStats(db_path)
    return _instance
