# Inverter Monitor

Real-time monitoring dashboard for MPP Solar / Voltronic-style hybrid inverters (PI30 protocol) with a live WebSocket-driven UI, historical statistics, and CSV export.

The service talks to the inverter over USB HID using [`mpp-solar`](https://github.com/jblance/mpp-solar), continuously polls `QPIGS` (status), and polls `QMOD` / `QPIWS` (mode + warnings) on a slower cadence so the fast loop isn't blocked. Readings are cached, streamed to the browser via Socket.IO, and persisted for daily / monthly / yearly aggregates.

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
| `MPP_BIN` | `/home/<user>/.../.venv/bin/mpp-solar` | Path to the `mpp-solar` executable |
| `MPP_PORT` | `/dev/hidraw0` | HID device the inverter is exposed on |
| `MPP_PROTOCOL` | `PI30` | Inverter protocol |
| `INVERTER_EFFICIENCY` | `0.92` | Used to estimate grid / flow balance |

Poll cadences live in [`continuous_reader.py`](continuous_reader.py) (`CYCLE_SECONDS`, `EXTRAS_INTERVAL_SECONDS`).

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

## Contributing

Issues and PRs are welcome. If you're adding support for another protocol / inverter family, please keep the fast-loop / slow-loop split and the single serial lock around `mpp-solar` invocations — they exist specifically to keep the HID bus stable.

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgements

- [jblance/mpp-solar](https://github.com/jblance/mpp-solar) for the protocol implementation that does the heavy lifting.
