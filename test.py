import json
import re
import subprocess

def parse_value(val_str, unit_str):
    val_str = val_str.strip()
    if unit_str == 'bool':
        if val_str in ['0', '1']:
            return bool(int(val_str))
        return val_str
    if val_str.startswith("b'") and val_str.endswith("'"):
        return val_str
    try:
        if '.' in val_str:
            return float(val_str)
        else:
            return int(val_str)
    except ValueError:
        return val_str

def parse_icon(icon_str):
    match = re.search(r"{'icon': '([^']+)'}", icon_str)
    if match:
        return match.group(1)
    return None

def parse_mppsolar_output(raw_text):
    lines = raw_text.strip().splitlines()
    data = {}
    # Skip the first 3 lines (command line, separator, header)
    for line in lines[3:]:
        if line.startswith('---'):
            break
        parts = line.rstrip().split()
        if len(parts) < 2:
            continue
        icon = None
        if parts[-1].startswith('{'):
            icon = parse_icon(' '.join(parts[-1:]))
            unit = parts[-2]
            value = parts[-3]
            parameter = ' '.join(parts[:-3])
        else:
            unit = parts[-1]
            value = parts[-2]
            parameter = ' '.join(parts[:-2])

        val = parse_value(value, unit)
        entry = {'value': val}
        if unit != 'bool' and unit != '':
            entry['unit'] = unit
        if icon:
            entry['icon'] = icon

        data[parameter.strip()] = entry
    return data

def get_mppsolar_output():
    # Run the mpp-solar command with your parameters and capture output
    # Replace /dev/hidraw1 and PI30 with your actual port and protocol
    cmd = ['mpp-solar', '-p', '/dev/hidraw0', '-P', 'PI30', '-c', 'QPIGS']
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {result.stderr}")
    return result.stdout

if __name__ == "__main__":
    raw_output = get_mppsolar_output()
    parsed_data = parse_mppsolar_output(raw_output)
    print(json.dumps(parsed_data, indent=4))
