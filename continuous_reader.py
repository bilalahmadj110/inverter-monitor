import threading
import time
import logging
from inverter_status import (
    get_inverter_status, get_device_mode, get_warning_status, get_inverter_config,
    GRID_PRESENT_MIN_VOLTAGE,
)

logger = logging.getLogger(__name__)

IDLE_YIELD_SECONDS = 0.005  # CPU yield between reads; not a rate limiter
EXTRAS_INTERVAL_SECONDS = 30.0
CONFIG_INTERVAL_SECONDS = 60.0

# QMOD is interleaved with the QPIGS loop so the operating mode (Line / Battery) that gates
# the grid-power estimate is never more than this stale. One QMOD transaction costs ~0.6 s of
# bus time, so at 20 s that is ~3% of samples. The poll is forced early whenever grid
# presence flips, which is exactly when the mode changes.
MODE_POLL_INTERVAL_SECONDS = 20.0
MODE_POLL_RETRY_SECONDS = 5.0
# Past this age the cached QMOD letter is discarded and the mode is derived from QPIGS
# (bypass signature + status flags) instead of trusting a stale answer.
MODE_STALE_SECONDS = 90.0


class ContinuousReader:
    """
    Continuously reads the inverter (QPIGS every cycle) and records to database.
    QMOD is interleaved every MODE_POLL_INTERVAL_SECONDS (and immediately when grid
    presence changes) because the mode gates the grid-power estimate. QPIWS / QPIRI
    are fetched on demand (page load, modal open) via refresh_extras. Latest
    mode/warnings are merged into every QPIGS reading before it's cached + recorded.
    """
    def __init__(self, stats_manager, on_reading=None):
        self.stats_manager = stats_manager
        self.on_reading = on_reading  # fired after every successful read: on_reading(status, total_readings)
        self.running = False
        self.reader_thread = None
        self.extras_thread = None
        self.latest_data = None
        self.data_lock = threading.Lock()

        self._mode = None
        self._mode_time = 0.0          # wall-clock time of the last successful QMOD
        self._next_mode_poll = 0.0     # monotonic deadline for the next interleaved QMOD
        self._grid_present = None      # last seen grid-presence, to force a QMOD on flips
        self._warnings = []
        self._config = {}
        self._extras_lock = threading.Lock()
        self._last_extras_time = 0.0
        self._last_config_time = 0.0

        self.total_readings = 0
        self.error_count = 0
        self.last_reading_time = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self.reader_thread.start()
        # Warnings + config are fetched on demand from the frontend via /refresh-extras.
        # Do one initial fetch in a thread so the first page load already has them.
        threading.Thread(target=self._initial_extras_fetch, daemon=True).start()
        logger.info("Continuous reader started (QPIGS back-to-back, QMOD interleaved, extras on demand)")

    def stop(self):
        self.running = False
        for t in (self.reader_thread, self.extras_thread):
            if t and t.is_alive():
                t.join(timeout=5)
        logger.info("Continuous reader stopped")

    def _initial_extras_fetch(self):
        """Fetch mode + warnings + config once at startup so the UI isn't empty."""
        try:
            self.refresh_extras(min_age_seconds=0)
        except Exception as e:
            logger.debug(f"Initial extras fetch failed (will retry on demand): {e}")

    def get_latest_data(self):
        with self.data_lock:
            return self.latest_data

    def _get_extras(self):
        """Return (mode, warnings). mode is None when the last QMOD answer is older than
        MODE_STALE_SECONDS so the status builder falls back to deriving it."""
        with self._extras_lock:
            fresh = self._mode is not None and (time.time() - self._mode_time) <= MODE_STALE_SECONDS
            return (self._mode if fresh else None), list(self._warnings)

    def _set_mode(self, mode):
        with self._extras_lock:
            self._mode = mode
            self._mode_time = time.time()

    def _set_extras(self, mode, warnings):
        with self._extras_lock:
            if mode is not None:
                self._mode = mode
                self._mode_time = time.time()
            self._warnings = warnings
            self._last_extras_time = time.time()

    def _poll_mode(self):
        """One interleaved QMOD. Goes through the same PI30 lock as QPIGS, so the bus
        stays half-duplex-safe; on failure retry sooner rather than waiting a full interval."""
        mode = get_device_mode()
        now = time.monotonic()
        if mode:
            self._set_mode(mode)
            self._next_mode_poll = now + MODE_POLL_INTERVAL_SECONDS
        else:
            self._next_mode_poll = now + MODE_POLL_RETRY_SECONDS

    def get_config(self):
        with self._extras_lock:
            return dict(self._config)

    def refresh_config(self, min_age_seconds=5.0):
        """Refresh QPIRI config. If we refreshed within the last `min_age_seconds`,
        return the cached value instead of re-querying — prevents thundering-herd
        when multiple clients request /config simultaneously."""
        with self._extras_lock:
            age = time.time() - self._last_config_time
            if self._config and age < min_age_seconds:
                return dict(self._config)
        try:
            cfg = get_inverter_config()
            if cfg:
                with self._extras_lock:
                    self._config = cfg
                    self._last_config_time = time.time()
            return cfg
        except Exception as e:
            logger.warning(f"Config refresh failed: {e}")
            with self._extras_lock:
                return dict(self._config)

    def refresh_extras(self, min_age_seconds=2.0):
        """Run QMOD + QPIWS + QPIRI through the inverter lock and return the combined state.
        Debounced: if all three were refreshed within the last `min_age_seconds`, returns the
        cached values without re-querying."""
        with self._extras_lock:
            extras_age = time.time() - self._last_extras_time
            cfg_age = time.time() - self._last_config_time
            if extras_age < min_age_seconds and cfg_age < min_age_seconds and self._mode is not None and self._config:
                return {
                    'mode': self._mode,
                    'warnings': list(self._warnings),
                    'config': dict(self._config),
                    'cached': True,
                    'extras_age_s': round(extras_age, 1),
                }
        result = {'cached': False}
        try:
            mode = get_device_mode()
            warnings = get_warning_status()
            self._set_extras(mode, warnings)
            if mode:
                self._next_mode_poll = time.monotonic() + MODE_POLL_INTERVAL_SECONDS
            result['mode'] = mode
            result['warnings'] = warnings
        except Exception as e:
            logger.warning(f"refresh_extras: mode/warnings failed: {e}")
            with self._extras_lock:
                result['mode'] = self._mode
                result['warnings'] = list(self._warnings)
        try:
            cfg = get_inverter_config()
            if cfg:
                with self._extras_lock:
                    self._config = cfg
                    self._last_config_time = time.time()
                result['config'] = cfg
            else:
                with self._extras_lock:
                    result['config'] = dict(self._config)
        except Exception as e:
            logger.warning(f"refresh_extras: config failed: {e}")
            with self._extras_lock:
                result['config'] = dict(self._config)
        result['extras_age_s'] = 0
        return result

    def _read_loop(self):
        logger.info("Starting continuous reading loop")
        while self.running:
            try:
                if time.monotonic() >= self._next_mode_poll:
                    self._poll_mode()

                mode, warnings = self._get_extras()
                status = get_inverter_status(mode=mode, warnings=warnings)
                self.total_readings += 1
                self.last_reading_time = time.time()

                with self.data_lock:
                    self.latest_data = status

                if status['success'] and 'timing' in status:
                    # Grid appeared or vanished: the inverter transfers L<->B within seconds,
                    # so re-read QMOD on the very next cycle instead of waiting out the interval.
                    grid_present = status['metrics']['grid']['voltage'] >= GRID_PRESENT_MIN_VOLTAGE
                    if self._grid_present is not None and grid_present != self._grid_present:
                        self._next_mode_poll = 0.0
                    self._grid_present = grid_present

                    # record_reading wants the system block too (heat-sink temperature).
                    self.stats_manager.record_reading(
                        {**status['metrics'], 'system': status['system']},
                        status['timing']['start_time'],
                        status['timing']['end_time'],
                    )
                    if self.total_readings % 100 == 0:
                        d_ms = status['timing']['duration_ms']
                        logger.info(f"Reading #{self.total_readings}: {d_ms:.1f}ms - "
                                    f"Mode: {status['system']['mode']}({status['system']['mode_source']}), "
                                    f"Solar: {status['metrics']['solar']['power']}W, "
                                    f"Grid: {status['metrics']['grid']['power']}W, "
                                    f"Load: {status['metrics']['load']['power']}W")
                else:
                    self.error_count += 1
                    logger.warning(f"Failed reading #{self.total_readings}: "
                                   f"{status.get('error', 'Unknown error')}")

                if self.on_reading is not None:
                    try:
                        self.on_reading(status, self.total_readings)
                    except Exception as cb_err:
                        logger.warning(f"on_reading callback failed: {cb_err}")

                if self.total_readings % 500 == 0:
                    err_rate = (self.error_count / self.total_readings) * 100
                    logger.info(f"Reader @ #{self.total_readings}: error rate {err_rate:.1f}%")

            except Exception as e:
                self.error_count += 1
                logger.error(f"Error in reading loop: {e}")
                time.sleep(0.2)  # brief back-off only on unexpected error

            time.sleep(IDLE_YIELD_SECONDS)

    def get_statistics(self):
        error_rate = (self.error_count / max(1, self.total_readings))
        mode, warnings = self._get_extras()
        with self._extras_lock:
            mode_age = round(time.time() - self._mode_time, 1) if self._mode_time else None
        return {
            'total_readings': self.total_readings,
            'error_count': self.error_count,
            'error_rate': error_rate,
            'running': self.running,
            'last_reading_time': self.last_reading_time,
            'extras_last_poll': self._last_extras_time,
            'extras_mode': mode,
            'mode_age_s': mode_age,
            'extras_warning_count': len(warnings),
        }
