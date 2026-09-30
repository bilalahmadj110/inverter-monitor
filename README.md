# Inverter Monitor

Real-time monitoring dashboard for MPP Solar / Voltronic-style hybrid inverters (PI30 protocol) with a live WebSocket-driven UI, historical statistics, and CSV export.

The service talks to the inverter directly over USB HID (PI30 framing + CRC in `lib/pi30_hid.py`, no subprocess), continuously polls `QPIGS` (status), interleaves `QMOD` (mode) every ~20 s because the mode gates the grid-power estimate, and fetches `QPIWS` / `QPIRI` (warnings + config) on demand. Readings are cached, streamed to the browser via Socket.IO, and persisted for daily / monthly / yearly aggregates.

Grid power is **not** a PI30 measurement. It is derived from the energy balance (load + AC-charging − PV-to-load − battery discharge, with conversion efficiencies) and forced to zero in Battery mode. Treat monthly grid kWh as an estimate and record the units from the paper bill on the FESCO Bill page so the two can be compared.

## Features

- Live dashboard (solar flow + classic views) streaming every ~3s over WebSockets
- Continuous background reader with serialized half-duplex access to `/dev/hidraw0`
- Parsed mode + warning / fault decoding (full PI30 QPIWS bit map)
- Daily / monthly / yearly energy stats, recent-readings feed, CSV export
- REST endpoints: `/stats`, `/summary`, `/status`, `/warnings`, `/history`, `/recent-readings`, `/raw-data`, `/export-data`
- Socket.IO events: `inverter_update`, `stats_update`, `request_update`, `request_stats`

## Hardware

Tested against PI30-compatible inverters (e.g. MPP Solar / Voltronic Axpert family) connected via the inverter's USB port, which exposes a HID endpoint (typically `/dev/hidraw0` on Linux). Should work for any inverter supported by `mpp-solar`'s PI30 protocol driver.

## Requirements

- Linux host with access to the inverter's HID device (`/dev/hidraw0`)
- Python 3.10+
- `mpp-solar` CLI available in the Python venv (installed via `requirements.txt`)

## Quick start

```bash
git clone https://github.com/<your-user>/inverter-monitor.git
cd inverter-monitor

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Make sure your user can read /dev/hidraw0 (udev rule or group membership).
python app.py
```

The app listens on `http://0.0.0.0:5000/`.

### Configuration

Paths and tuning live at the top of [`inverter_status.py`](inverter_status.py):

| Setting | Default | Purpose |
|---|---|---|
| `MPP_PORT` | `/dev/hidraw0` | HID device the inverter is exposed on |
| `INVERTER_EFFICIENCY` | `0.92` | DC↔AC conversion factor in the grid-power energy balance |
| `SCC_EFFICIENCY` | `0.97` | PV→battery (MPPT) factor in the same balance |
| `GRID_MIN_REPORT_W` | `30` | Residuals below this are inside measurement resolution and read as 0 |

Poll cadences live in [`continuous_reader.py`](continuous_reader.py) (`MODE_POLL_INTERVAL_SECONDS`, `MODE_STALE_SECONDS`). The SQLite store runs in WAL mode; only the flush thread writes.

## Running as a service (systemd)

Example unit:

```ini
[Unit]
Description=Flask SocketIO App for Inverter
After=network.target

[Service]
User=bilal
WorkingDirectory=/home/bilal/Desktop/Inverter
ExecStartPre=/bin/sh -c 'fuser -k 5000/tcp || true'
ExecStart=/home/bilal/Desktop/Inverter/.venv/bin/python /home/bilal/Desktop/Inverter/app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

> Only run one instance at a time — PI30 is half-duplex over a single HID device and two processes polling `/dev/hidraw0` in parallel will produce NAK / CRC errors.

## Project layout

```
app.py                  # Flask + Socket.IO entrypoint, REST + WS routes
continuous_reader.py    # Background reader: QPIGS fast loop + QMOD/QPIWS slow loop
inverter_status.py      # mpp-solar subprocess wrapper, parsing, warning decoding
power_stats.py          # Persistence + daily/monthly/yearly aggregates
templates/              # Dashboard HTML (solar_flow, classic dashboard)
static/                 # CSS, JS, icons
requirements.txt
```

## Permanent URL through an AWS relay (optional)

The dashboard can be reached at a fixed HTTPS address with no domain and no inbound port:
an API Gateway WebSocket API plus one Lambda in front, and the Pi dialling *out* to it
(`aws_relay.py`). Nothing about the readings is stored in AWS; one DynamoDB table holds
connection ids and a few-KB last-seen snapshot. Live readings only flow while a logged-in
viewer is connected, so the running cost is well under a dollar a month. Everything lives
under `aws/`.

```bash
export AWS_PROFILE=nursepal AWS_REGION=ap-south-1
python3 aws/set_secrets.py ensure                                  # token + device secrets
echo -n '<dashboard password>' | python3 aws/set_secrets.py set-password --username admin
PYTHON=/path/to/python-with-jinja2 aws/deploy.sh                   # stack + Lambda code, prints the URL
echo -n '<pi app password>' | python3 aws/set_secrets.py pi-env --create-key \
  | ssh bilal@pi 'install -m 600 /dev/stdin ~/.config/inverter-relay.env'
# on the Pi
sudo cp aws/inverter-relay.service /etc/systemd/system/ && sudo systemctl enable --now inverter-relay
```

Re-run `aws/deploy.sh` after changing anything under `aws/`, `static/` or `templates/`; the
pages are pre-rendered into the Lambda package at deploy time. `aws/set_secrets.py rotate
device_secret` (then refresh the Pi's env file) or `rotate token_secret` (logs every
browser out) rotate the secrets.

## Contributing

Issues and PRs are welcome. If you're adding support for another protocol / inverter family, please keep the fast-loop / slow-loop split and the single serial lock around `mpp-solar` invocations — they exist specifically to keep the HID bus stable.

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgements

- [jblance/mpp-solar](https://github.com/jblance/mpp-solar) for the protocol implementation that does the heavy lifting.
