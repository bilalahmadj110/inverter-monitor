"""PI30 wire-format parsers.

Produces dicts matching the shape of the legacy `parse_mppsolar_output` output,
so downstream consumers (extract_system_metrics, _parse_qpiri_raw_lines, etc.)
work unchanged: {param: {'value': x[, 'unit': 'V']}}.
"""


def _num(s: str):
    try:
        return float(s) if '.' in s else int(s)
    except ValueError:
        return 0


# (field_name, unit_or_empty, parser) — order matches PI30 QPIGS wire format.
_QPIGS_FIELDS = [
    ('ac_input_voltage', 'V', float),
    ('ac_input_frequency', 'Hz', float),
    ('ac_output_voltage', 'V', float),
    ('ac_output_frequency', 'Hz', float),
    ('ac_output_apparent_power', 'VA', int),
    ('ac_output_active_power', 'W', int),
    ('ac_output_load', '%', int),
    ('bus_voltage', 'V', int),
    ('battery_voltage', 'V', float),
    ('battery_charging_current', 'A', int),
    ('battery_capacity', '%', int),
    ('inverter_heat_sink_temperature', '°C', int),
    ('pv_input_current_for_battery', 'A', float),
    ('pv_input_voltage', 'V', float),
    ('battery_voltage_from_scc', 'V', float),
    ('battery_discharge_current', 'A', int),
]

# QPIGS byte 17 (8-bit flags, MSB→LSB): b7 b6 b5 b4 b3 b2 b1 b0
_QPIGS_FLAGS_A = [
    'is_sbu_priority_version_added',
    'is_configuration_changed',
    'is_scc_firmware_updated',
    'is_load_on',
    'is_battery_voltage_to_steady_while_charging',
    'is_charging_on',
    'is_scc_charging_on',
    'is_ac_charging_on',
]

# QPIGS byte 21 (3-bit flags): b10 b9 b8
_QPIGS_FLAGS_B = [
    'is_charging_to_float',
    'is_switched_on',
    'is_reserved',
]


def parse_qpigs(payload: bytes) -> dict:
    """Parse QPIGS payload into {param: {'value': x, 'unit': ...}} dict."""
    parts = payload.decode('ascii', errors='replace').split()
    out = {}
    for i, (name, unit, cast) in enumerate(_QPIGS_FIELDS):
        if i >= len(parts):
            break
        try:
            val = cast(parts[i])
        except (ValueError, TypeError):
            val = 0
        entry = {'value': val}
        if unit:
            entry['unit'] = unit
        out[name] = entry

    flags_a = parts[16] if len(parts) > 16 else ''
    for i, name in enumerate(_QPIGS_FLAGS_A):
        bit = flags_a[i] if i < len(flags_a) else '0'
        out[name] = {'value': bit == '1'}

    if len(parts) > 19:
        try:
            out['pv_input_power'] = {'value': int(parts[19]), 'unit': 'W'}
        except ValueError:
            out['pv_input_power'] = {'value': 0, 'unit': 'W'}

    flags_b = parts[20] if len(parts) > 20 else ''
    for i, name in enumerate(_QPIGS_FLAGS_B):
        bit = flags_b[i] if i < len(flags_b) else '0'
        out[name] = {'value': bit == '1'}

    return out


# Code tables used by QPIRI. Strings chosen to match what mpp-solar emits,
# so existing regex-based normalizers (_normalize_output_priority etc.) work.
_BATTERY_TYPE = {0: 'AGM', 1: 'Flooded', 2: 'User', 3: 'Pylontech'}
_INPUT_VOLTAGE_RANGE = {0: 'Appliance', 1: 'UPS'}
_OUTPUT_SOURCE_PRIORITY = {0: 'Utility first', 1: 'Solar first', 2: 'SBU'}
_CHARGER_SOURCE_PRIORITY = {
    0: 'Utility first',
    1: 'Solar first',
    2: 'Solar and Utility',
    3: 'Only solar',
}
_MACHINE_TYPE = {0: 'Grid tie', 1: 'Off Grid', 10: 'Hybrid'}
_TOPOLOGY = {0: 'transformerless', 1: 'transformer'}
_OUTPUT_MODE = {
    0: 'single machine output',
    1: 'parallel output',
    2: 'Phase 1 of 3 Phase output',
    3: 'Phase 2 of 3 Phase output',
    4: 'Phase 3 of 3 Phase output',
}


def _coded(parts, idx, table, unit=''):
    if idx >= len(parts):
        return {'value': ''}
    raw = parts[idx]
    try:
        v = table.get(int(raw), raw)
    except ValueError:
        v = raw
    entry = {'value': v}
    if unit:
        entry['unit'] = unit
    return entry


def _float_entry(parts, idx, unit):
    if idx >= len(parts):
        return {'value': 0.0, 'unit': unit}
    try:
        return {'value': float(parts[idx]), 'unit': unit}
    except ValueError:
        return {'value': 0.0, 'unit': unit}


def _int_entry(parts, idx, unit):
    if idx >= len(parts):
        return {'value': 0, 'unit': unit}
    try:
        return {'value': int(parts[idx]), 'unit': unit}
    except ValueError:
        return {'value': 0, 'unit': unit}


def parse_qpiri(payload: bytes) -> dict:
    """Parse QPIRI payload. Handles the 21- and 25-field variants."""
    parts = payload.decode('ascii', errors='replace').split()
    out = {
        'ac_input_voltage': _float_entry(parts, 0, 'V'),
        'ac_input_current': _float_entry(parts, 1, 'A'),
        'ac_output_voltage': _float_entry(parts, 2, 'V'),
        'ac_output_frequency': _float_entry(parts, 3, 'Hz'),
        'ac_output_current': _float_entry(parts, 4, 'A'),
        'ac_output_apparent_power': _int_entry(parts, 5, 'VA'),
        'ac_output_active_power': _int_entry(parts, 6, 'W'),
        'battery_voltage': _float_entry(parts, 7, 'V'),
        'battery_recharge_voltage': _float_entry(parts, 8, 'V'),
        'battery_under_voltage': _float_entry(parts, 9, 'V'),
        'battery_bulk_charge_voltage': _float_entry(parts, 10, 'V'),
        'battery_float_charge_voltage': _float_entry(parts, 11, 'V'),
        'battery_type': _coded(parts, 12, _BATTERY_TYPE),
        'max_ac_charging_current': _int_entry(parts, 13, 'A'),
        'max_charging_current': _int_entry(parts, 14, 'A'),
        'input_voltage_range': _coded(parts, 15, _INPUT_VOLTAGE_RANGE),
        'output_source_priority': _coded(parts, 16, _OUTPUT_SOURCE_PRIORITY),
        'charger_source_priority': _coded(parts, 17, _CHARGER_SOURCE_PRIORITY),
        'max_parallel_units': _int_entry(parts, 18, ''),
        'machine_type': _coded(parts, 19, _MACHINE_TYPE),
        'topology': _coded(parts, 20, _TOPOLOGY),
        'output_mode': _coded(parts, 21, _OUTPUT_MODE),
        'battery_redischarge_voltage': _float_entry(parts, 22, 'V'),
    }
    return out


def parse_qmod(payload: bytes) -> str:
    """QMOD returns a single ASCII letter (P/S/L/B/F/H/C/D)."""
    s = payload.decode('ascii', errors='replace').strip()
    return s[0] if s else ''


def parse_qpiws(payload: bytes) -> str:
    """QPIWS returns a 32-char binary string of warning bits."""
    return payload.decode('ascii', errors='replace').strip()
