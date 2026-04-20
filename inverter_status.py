import json
import logging
import re
import time

from lib.pi30_hid import get_default_reader
from lib.pi30_parse import parse_qmod, parse_qpigs, parse_qpiri, parse_qpiws

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MPP_PORT = '/dev/hidraw0'

INVERTER_EFFICIENCY = 0.92
GRID_ESTIMATE_TOLERANCE_W = 15
GRID_PRESENT_MIN_VOLTAGE = 180

MODE_LABELS = {
    'P': 'Power On',
    'S': 'Standby',
    'L': 'Line Mode',
    'B': 'Battery Mode',
    'F': 'Fault',
    'H': 'Power Saving',
    'C': 'Charging',
    'D': 'Shutdown',
}

# QPIWS bit order (PI30 protocol, 32-bit warning string).
# Indices here are 0-based positions in the returned string.
WARNING_MAP = [
    (0,  'pv_loss',                  'PV Loss',                    'warning'),
    (1,  'inverter_fault',           'Inverter Fault',             'fault'),
    (2,  'bus_over_voltage',         'Bus Over Voltage',           'fault'),
    (3,  'bus_under_voltage',        'Bus Under Voltage',          'fault'),
    (4,  'bus_soft_fail',            'Bus Soft Fail',              'fault'),
    (5,  'line_fail',                'Line Fail',                  'warning'),
    (6,  'opv_short',                'OPV Short',                  'fault'),
    (7,  'inverter_voltage_low',     'Inverter Voltage Too Low',   'fault'),
    (8,  'inverter_voltage_high',    'Inverter Voltage Too High',  'fault'),
    (9,  'over_temperature',         'Over Temperature',           'warning'),
    (10, 'fan_locked',               'Fan Locked',                 'warning'),
    (11, 'battery_voltage_high',     'Battery Voltage High',       'warning'),
    (12, 'battery_low_alarm',        'Battery Low Alarm',          'warning'),
    (13, 'overcharge',               'Overcharge',                 'warning'),
    (14, 'battery_under_shutdown',   'Battery Under Shutdown',     'fault'),
    (16, 'overload',                 'Overload',                   'warning'),
    (17, 'eeprom_fault',             'EEPROM Fault',               'warning'),
    (18, 'inverter_over_current',    'Inverter Over Current',      'fault'),
    (19, 'inverter_soft_fail',       'Inverter Soft Fail',         'fault'),
    (20, 'self_test_fail',           'Self Test Fail',             'fault'),
    (21, 'op_dc_voltage_over',       'Output DC Voltage Over',     'fault'),
    (22, 'battery_open',             'Battery Open',               'fault'),
    (23, 'current_sensor_fail',      'Current Sensor Fail',        'fault'),
    (24, 'battery_short',            'Battery Short',              'fault'),
    (25, 'power_limit',              'Power Limit',                'warning'),
    (26, 'pv_voltage_high',          'PV Voltage High',            'warning'),
    (27, 'mppt_overload_fault',      'MPPT Overload Fault',        'fault'),
    (28, 'mppt_overload_warning',    'MPPT Overload Warning',      'warning'),
    (29, 'battery_too_low_to_charge','Battery Too Low To Charge',  'warning'),
]


def _query(command_code, retries=3):
    """Query the inverter over HID and return the raw payload string."""
    reader = get_default_reader(MPP_PORT)
    payload = reader.query(command_code, retries=retries)
    return payload.decode('ascii', errors='replace')


def get_mppsolar_output():
    """Backward-compat shim. Returns QPIGS raw payload string."""
    return _query('QPIGS')


def get_device_mode():
    """QMOD -> single-letter mode (P/S/L/B/F/H/C/D) or None if unavailable."""
    try:
        payload = _query('QMOD', retries=2)
        letter = parse_qmod(payload.encode('ascii'))
        if letter in MODE_LABELS:
            return letter
    except Exception as e:
        logger.debug(f"QMOD unavailable: {e}")
    return None


OUTPUT_PRIORITY_COMMANDS = {
    'UTI': ('POP00', 'Utility first', 'Grid powers the load; battery/solar stay as backup.'),
    'SOL': ('POP01', 'Solar first',   'Solar feeds load first, then grid; battery is last resort.'),
    'SBU': ('POP02', 'SBU',           'Solar → Battery → Utility. Typical off-grid profile.'),
}

CHARGER_PRIORITY_COMMANDS = {
    'UTI_SOL': ('PCP00', 'Utility + Solar',  'Grid and solar can both charge the battery.'),
    'SOL_FIRST': ('PCP01', 'Solar first',    'Solar charges first; grid tops up if needed.'),
    'SOL_UTI': ('PCP02', 'Solar + Utility',  'Both charge simultaneously when available.'),
    'SOL_ONLY': ('PCP03', 'Only solar',      'Only solar is allowed to charge; grid never does.'),
}


def _normalize_output_priority(raw):
    if not raw:
        return None
    r = raw.strip().lower()
    if 'sbu' in r:
        return 'SBU'
    if 'solar' in r or 'pv' in r:
        return 'SOL'
    if 'utility' in r or 'grid' in r:
        return 'UTI'
    return raw.strip()


def _normalize_charger_priority(raw):
    if not raw:
        return None
    r = raw.strip().lower()
    if 'only solar' in r or 'only' == r or r.startswith('only'):
        return 'SOL_ONLY'
    if 'solar first' in r:
        return 'SOL_FIRST'
    if 'solar and utility' in r or 'solar + utility' in r:
        return 'SOL_UTI'
    if 'utility' in r:
        return 'UTI_SOL'
    return raw.strip()


def _parse_qpiri_raw_lines(parsed):
    """Return QPIRI as an ordered list of (label, value, unit) for read-only display.
    `parsed` is the already-parsed dict from parse_qpiri."""
    pretty = {
        'ac_input_voltage': 'AC Input Voltage',
        'ac_input_current': 'AC Input Current',
        'ac_output_voltage': 'AC Output Voltage',
        'ac_output_frequency': 'AC Output Frequency',
        'ac_output_current': 'AC Output Current',
        'ac_output_apparent_power': 'AC Output Apparent Power',
        'ac_output_active_power': 'AC Output Active Power',
        'battery_voltage': 'Battery Nominal Voltage',
        'battery_recharge_voltage': 'Battery Recharge Voltage',
        'battery_under_voltage': 'Battery Under Voltage',
        'battery_bulk_charge_voltage': 'Bulk Charge Voltage',
        'battery_float_charge_voltage': 'Float Charge Voltage',
        'battery_type': 'Battery Type',
        'max_ac_charging_current': 'Max AC Charging Current',
        'max_charging_current': 'Max Charging Current',
        'input_voltage_range': 'Input Voltage Range',
        'output_source_priority': 'Output Source Priority',
        'charger_source_priority': 'Charger Source Priority',
        'max_parallel_units': 'Max Parallel Units',
        'machine_type': 'Machine Type',
        'topology': 'Topology',
        'output_mode': 'Output Mode',
        'battery_redischarge_voltage': 'Battery Redischarge Voltage',
    }
    rows = []
    for key in pretty:
        if key in parsed:
            entry = parsed[key]
            rows.append({
                'key': key,
                'label': pretty[key],
                'value': entry.get('value'),
                'unit': entry.get('unit') or '',
            })
    return rows


def get_inverter_config():
    """QPIRI → normalized config dict plus raw rows for display. Returns {} on failure."""
    try:
        payload = _query('QPIRI', retries=3)
        parsed = parse_qpiri(payload.encode('ascii'))
        op_raw = parsed.get('output_source_priority', {}).get('value')
        cp_raw = parsed.get('charger_source_priority', {}).get('value')
        return {
            'output_priority': _normalize_output_priority(op_raw),
            'output_priority_raw': op_raw,
            'charger_priority': _normalize_charger_priority(cp_raw),
            'charger_priority_raw': cp_raw,
            'battery_type': parsed.get('battery_type', {}).get('value'),
            'max_charging_current': parsed.get('max_charging_current', {}).get('value'),
            'max_ac_charging_current': parsed.get('max_ac_charging_current', {}).get('value'),
            'battery_under_voltage': parsed.get('battery_under_voltage', {}).get('value'),
            'battery_bulk_charge_voltage': parsed.get('battery_bulk_charge_voltage', {}).get('value'),
            'battery_float_charge_voltage': parsed.get('battery_float_charge_voltage', {}).get('value'),
            'ac_output_voltage': parsed.get('ac_output_voltage', {}).get('value'),
            'ac_output_frequency': parsed.get('ac_output_frequency', {}).get('value'),
            'rows': _parse_qpiri_raw_lines(parsed),
        }
    except Exception as e:
        logger.debug(f"QPIRI unavailable: {e}")
        return {}


def _run_write_command(command_code, label):
    logger.info(f"Sending write command {command_code} ({label})")
    payload = _query(command_code, retries=3)
    lower = (payload or '').lower()
    if 'nak' in lower or 'error' in lower:
        raise RuntimeError(f"Inverter rejected {command_code}: {payload.strip()[:160]}")
    return payload


def set_output_priority(mode):
    """Set output source priority via POP command. `mode` must be UTI, SOL, or SBU."""
    mode = (mode or '').strip().upper()
    if mode not in OUTPUT_PRIORITY_COMMANDS:
        raise ValueError(f"Invalid output priority '{mode}'. Must be one of {list(OUTPUT_PRIORITY_COMMANDS)}")
    cmd_code, label, _ = OUTPUT_PRIORITY_COMMANDS[mode]
    out = _run_write_command(cmd_code, label)
    return {'mode': mode, 'label': label, 'command': cmd_code, 'response': out.strip()[:200]}


def set_charger_priority(mode):
    """Set charger source priority via PCP command."""
    mode = (mode or '').strip().upper()
    if mode not in CHARGER_PRIORITY_COMMANDS:
        raise ValueError(f"Invalid charger priority '{mode}'. Must be one of {list(CHARGER_PRIORITY_COMMANDS)}")
    cmd_code, label, _ = CHARGER_PRIORITY_COMMANDS[mode]
    out = _run_write_command(cmd_code, label)
    return {'mode': mode, 'label': label, 'command': cmd_code, 'response': out.strip()[:200]}


def get_warning_status():
    """QPIWS -> list of active warnings [{key,label,severity}]. Empty if not parseable."""
    try:
        payload = _query('QPIWS', retries=2)
        bits = parse_qpiws(payload.encode('ascii'))
        m = re.search(r'([01]{32})', bits)
        if not m:
            return []
        bits = m.group(1)
        active = []
        for idx, key, label, sev in WARNING_MAP:
            if idx < len(bits) and bits[idx] == '1':
                active.append({'key': key, 'label': label, 'severity': sev})
        return active
    except Exception as e:
        logger.debug(f"QPIWS unavailable: {e}")
        return []


def _derive_grid_power(parsed, metrics):
    """Energy balance estimate. Off-grid inverters can't export → clamp ≥ 0.
    Gated on grid voltage being present (not on mode, which may be derived
    incorrectly when QMOD is unavailable)."""
    load_p = metrics['load']['active_power']
    solar_p = metrics['solar']['power']
    batt_charge_w = metrics['battery']['charging_current'] * metrics['battery']['voltage']
    batt_discharge_w = metrics['battery']['discharge_current'] * metrics['battery']['voltage']

    estimate = load_p + (batt_charge_w / INVERTER_EFFICIENCY) - solar_p - (batt_discharge_w * INVERTER_EFFICIENCY)

    grid_voltage = metrics['grid']['voltage']
    is_ac_charging = metrics['system']['is_ac_charging_on']

    if grid_voltage < GRID_PRESENT_MIN_VOLTAGE:
        return 0.0

    if estimate < GRID_ESTIMATE_TOLERANCE_W and not is_ac_charging:
        return 0.0
    return max(0.0, round(estimate, 1))


def _derive_charge_stage(metrics):
    s = metrics['system']
    b = metrics['battery']
    if not (s['is_charging_on'] or s['is_scc_charging_on'] or s['is_ac_charging_on']):
        return 'idle'
    if s.get('is_charging_to_float'):
        return 'float'
    if b['percentage'] >= 95:
        return 'absorption'
    return 'bulk'


def _derive_mode_from_flags(metrics):
    """Fallback when QMOD unavailable."""
    s = metrics['system']
    if not s['is_switched_on']:
        return 'D'
    if s['is_ac_charging_on']:
        return 'L'
    batt_discharging = metrics['battery']['discharge_current'] > 0.5
    grid_present = metrics['grid']['voltage'] >= GRID_PRESENT_MIN_VOLTAGE
    load_p = metrics['load']['active_power']
    solar_p = metrics['solar']['power']

    if batt_discharging:
        return 'B'
    # Grid is present and carrying load without battery discharge → Line mode
    # (e.g. battery full / float, solar insufficient, grid feeds the load).
    if grid_present and load_p > solar_p + GRID_ESTIMATE_TOLERANCE_W:
        return 'L'
    if solar_p > 5:
        return 'B'
    return 'S'


def extract_system_metrics(parsed_data, mode=None, warnings=None):
    """Build enriched metrics dict from QPIGS parsed output + optional QMOD/QPIWS."""

    def v(key, default=0):
        return parsed_data.get(key, {}).get('value', default) or default

    charging_current = v('battery_charging_current')
    discharge_current = v('battery_discharge_current')
    battery_voltage = v('battery_voltage')
    net_battery_current = charging_current - discharge_current
    battery_power_w = round(net_battery_current * battery_voltage, 1)

    if charging_current > 0.1:
        battery_direction = 'charging'
    elif discharge_current > 0.1:
        battery_direction = 'discharging'
    else:
        battery_direction = 'idle'

    pv_voltage = v('pv_input_voltage')
    pv_power = v('pv_input_power')
    pv_current_true = round(pv_power / pv_voltage, 2) if pv_voltage > 0 else 0
    pv_to_battery_current = v('pv_input_current_for_battery')

    active_p = v('ac_output_active_power')
    apparent_p = v('ac_output_apparent_power')
    output_voltage = v('ac_output_voltage')
    power_factor = round(active_p / apparent_p, 3) if apparent_p > 0 else 0
    load_current = round(apparent_p / output_voltage, 2) if output_voltage > 0 else 0

    system = {
        'bus_voltage': v('bus_voltage'),
        'temperature': v('inverter_heat_sink_temperature'),
        'is_load_on': bool(v('is_load_on', False)),
        'is_charging_on': bool(v('is_charging_on', False)),
        'is_scc_charging_on': bool(v('is_scc_charging_on', False)),
        'is_ac_charging_on': bool(v('is_ac_charging_on', False)),
        'is_switched_on': bool(v('is_switched_on', False)),
        'is_charging_to_float': bool(v('is_charging_to_float', False)),
    }

    metrics = {
        'grid': {
            'voltage': v('ac_input_voltage'),
            'frequency': v('ac_input_frequency'),
            'power': 0,
            'in_use': False,
            'estimated': True,
        },
        'solar': {
            'voltage': pv_voltage,
            'current': pv_current_true,
            'pv_to_battery_current': pv_to_battery_current,
            'power': pv_power,
        },
        'battery': {
            'voltage': battery_voltage,
            'current': net_battery_current,
            'charging_current': charging_current,
            'discharge_current': discharge_current,
            'percentage': v('battery_capacity'),
            'power': battery_power_w,
            'direction': battery_direction,
        },
        'load': {
            'voltage': output_voltage,
            'frequency': v('ac_output_frequency'),
            'current': load_current,
            'active_power': active_p,
            'apparent_power': apparent_p,
            'power_factor': power_factor,
            'power': active_p,
            'percentage': v('ac_output_load'),
        },
        'system': system,
    }

    metrics['system']['mode'] = mode or _derive_mode_from_flags(metrics)
    metrics['system']['mode_label'] = MODE_LABELS.get(metrics['system']['mode'], 'Unknown')
    metrics['system']['mode_source'] = 'qmod' if mode else 'derived'
    metrics['system']['charge_stage'] = _derive_charge_stage(metrics)

    grid_power = _derive_grid_power(parsed_data, metrics)
    metrics['grid']['power'] = grid_power
    metrics['grid']['in_use'] = grid_power > 0 or system['is_ac_charging_on']

    metrics['system']['warnings'] = warnings or []
    metrics['system']['has_fault'] = any(w['severity'] == 'fault' for w in metrics['system']['warnings'])

    return metrics


def extract_dashboard_metrics(parsed_data, mode=None, warnings=None):
    """Compatibility wrapper — returns enriched metrics."""
    sm = extract_system_metrics(parsed_data, mode=mode, warnings=warnings)
    return {
        'grid': sm['grid'],
        'solar': sm['solar'],
        'battery': sm['battery'],
        'load': sm['load'],
    }


def get_inverter_status(mode=None, warnings=None):
    """Read QPIGS and assemble the full status payload. `mode`/`warnings` may be supplied
    by a slow-poll caller to avoid blocking every 3s on extra commands."""
    start_time = time.time()

    try:
        raw_payload = _query('QPIGS')
        end_time = time.time()

        parsed_data = parse_qpigs(raw_payload.encode('ascii'))

        expected_keys = ['ac_input_voltage', 'pv_input_voltage', 'battery_voltage']
        if not any(k in parsed_data for k in expected_keys):
            raise RuntimeError("No valid inverter data received")

        sm = extract_system_metrics(parsed_data, mode=mode, warnings=warnings)
        dashboard_metrics = {
            'grid': sm['grid'],
            'solar': sm['solar'],
            'battery': sm['battery'],
            'load': sm['load'],
        }

        return {
            'success': True,
            'metrics': dashboard_metrics,
            'system': sm['system'],
            'raw_data': parsed_data,
            'timing': {
                'start_time': start_time,
                'end_time': end_time,
                'duration_ms': (end_time - start_time) * 1000,
            },
        }
    except Exception as e:
        end_time = time.time()
        logger.error(f"Failed to get inverter status: {e}")
        return {
            'success': False,
            'error': str(e),
            'metrics': {
                'grid': {'voltage': 0, 'frequency': 0, 'power': 0, 'in_use': False, 'estimated': True},
                'solar': {'voltage': 0, 'current': 0, 'pv_to_battery_current': 0, 'power': 0},
                'battery': {'voltage': 0, 'current': 0, 'charging_current': 0, 'discharge_current': 0,
                            'percentage': 0, 'power': 0, 'direction': 'idle'},
                'load': {'voltage': 0, 'frequency': 0, 'current': 0, 'active_power': 0,
                         'apparent_power': 0, 'power_factor': 0, 'power': 0, 'percentage': 0},
            },
            'system': {
                'bus_voltage': 0,
                'temperature': 0,
                'is_load_on': False,
                'is_charging_on': False,
                'is_scc_charging_on': False,
                'is_ac_charging_on': False,
                'is_switched_on': False,
                'is_charging_to_float': False,
                'mode': 'F',
                'mode_label': MODE_LABELS['F'],
                'mode_source': 'derived',
                'charge_stage': 'idle',
                'warnings': [],
                'has_fault': True,
            },
            'timing': {
                'start_time': start_time,
                'end_time': end_time,
                'duration_ms': (end_time - start_time) * 1000,
            },
        }


if __name__ == "__main__":
    status = get_inverter_status()
    print(json.dumps(status, indent=4))
