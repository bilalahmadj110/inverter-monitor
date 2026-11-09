# MCP server: control and read the inverter from Claude or a chatbot

`mcp_server.py` is a [Model Context Protocol](https://modelcontextprotocol.io) server. Any MCP host (Claude Code,
Claude Desktop, claude.ai custom connectors, or your own chatbot) can call it to read the live inverter state, the
energy history, the savings and the FESCO bill forecast, and to switch the output / charger source priority
(SBU, Solar first, Utility first).

It never opens `/dev/hidraw0`. It logs in to the Flask dashboard (`app.py`) over HTTP like a browser and uses its
JSON routes, so the half-duplex PI30 bus keeps exactly one owner. It can therefore run anywhere that can reach
the dashboard: on the Pi next to the app, or on a laptop on the LAN.

```
Claude / chatbot  ──MCP (stdio or HTTP)──►  mcp_server.py  ──HTTP, logged in──►  app.py  ──PI30──►  inverter
```

## Tools

| Tool | What it returns | Changes anything? |
|---|---|---|
| `get_live_status` | mode (Line / Battery), solar / load / grid / battery W, battery V and %, temperature, warnings, configured priorities, reading age | no |
| `get_inverter_settings` (`refresh`) | output + charger priority, battery type and voltage set-points, charge-current limits, full QPIRI table, valid option keys | no (`refresh=true` re-reads QPIRI) |
| `get_warnings` (`refresh`) | active warnings / faults with severity, current mode | no |
| `get_energy_summary` (`date`) | one day's kWh by source, peaks, self-sufficiency, solar fraction | no |
| `get_daily_history` (`days`) | per-day kWh for the last N days, totals and averages | no |
| `get_recent_trend` (`minutes`, `bucket_seconds`) | bucketed power trend, battery % and grid voltage over the last N minutes | no |
| `get_grid_outages` (`from_date`, `to_date`) | load-shedding events, total downtime, availability | no |
| `get_savings` | today / cycle / lifetime savings in PKR, payback, cycle-end projection and slab-cliff alert | no |
| `get_bill_forecast` | open FESCO cycle: units so far, projected units and bill, slab, due dates, protected status, meter calibration, last cycles | no |
| `get_system_health` | dashboard version, reader thread state, error rate, reading freshness | no |
| `set_output_priority` (`SBU` / `SOL` / `UTI`) | sends POP00-02, re-reads QPIRI, reports previous → now | **yes** |
| `set_charger_priority` (`UTI_SOL` / `SOL_FIRST` / `SOL_UTI` / `SOL_ONLY`) | sends PCP00-03, re-reads QPIRI, reports previous → now | **yes** |
| `set_inverter_parameter` (`param`, `value`) | battery voltages, charge currents, battery type, output frequency; only registered with `INVERTER_MCP_ALLOW_PARAM_WRITES=1` | **yes** |

Every tool returns a one-line `summary` the model can quote plus the structured fields. Grid power and grid
kWh are the dashboard's energy-balance estimate, never a measurement; the tools say so and
`get_bill_forecast` carries the meter calibration factor.

Resources `inverter://status` and `inverter://settings` expose the same data as JSON. Two prompts,
`inverter_briefing` and `priority_advice`, give the model a ready-made plan for a status briefing and for a
"which priority should I use" question.

## Safety switches

| Variable | Effect |
|---|---|
| `INVERTER_MCP_READ_ONLY=1` | no write tool is registered at all; the model cannot see one |
| `INVERTER_MCP_ALLOW_PARAM_WRITES=1` | adds `set_inverter_parameter`; off by default because wrong voltages can damage the battery bank |
| `INVERTER_MCP_TOKEN` | token required on every HTTP request, as a bearer header or as the `/<token>/mcp` URL prefix (HTTP transport only); the server refuses to bind to a non-loopback address without one |

The dashboard's own validation and rate limits still apply (10 priority writes per minute, selectable-current
and plausible-voltage checks, NAK from the inverter surfaces as a tool error). Tool annotations mark the three
write tools as non-read-only so hosts that ask before side effects will ask.

## Configuration

The server reads the environment, then `~/.config/inverter-mcp.env` (or `INVERTER_MCP_ENV_FILE`) for anything
not set. `deploy/inverter-mcp.env.example` lists every key; the three that matter:

```
INVERTER_URL=http://192.168.18.130:5000    # the dashboard; http://127.0.0.1:5000 on the Pi itself
INVERTER_USERNAME=admin
INVERTER_PASSWORD=...                       # the dashboard password
```

Keep the file mode 600. `python mcp_server.py --check` logs in, reads once and prints a summary; run it first
whenever a host says the server is not responding.

## Install

The `mcp` SDK needs pydantic ≥ 2.12 while the dashboard pins 2.11.5 for mppsolar, so the MCP server gets its
own venv and its own requirements file:

```bash
uv venv --python 3.12 .venv-mcp                      # 3.11 on the Pi
uv pip install --python .venv-mcp/bin/python -r requirements-mcp.txt
.venv-mcp/bin/python mcp_server.py --check
```

## Claude Code (this laptop, stdio)

```bash
claude mcp add --scope user inverter -- /Users/bilalahmad/Documents/inverter/.venv-mcp/bin/python /Users/bilalahmad/Documents/inverter/mcp_server.py
```

Then `/mcp` inside a session shows `inverter` connected with its tools. Try: "what is the inverter doing right
now?", "switch output priority to SBU", "how is this month's FESCO bill looking?".

## Claude Desktop (this laptop, stdio)

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (keep the other keys) and fully quit
and reopen Claude Desktop:

```json
{
  "mcpServers": {
    "inverter": {
      "command": "/Users/bilalahmad/Documents/inverter/.venv-mcp/bin/python",
      "args": ["/Users/bilalahmad/Documents/inverter/mcp_server.py"]
    }
  }
}
```

Its stderr lands in `~/Library/Logs/Claude/mcp-server-inverter.log`.

## Chatbots and remote hosts (Streamable HTTP on the Pi)

Run the server as a service on the Pi, bound to the LAN with a bearer token:

```bash
# on the Pi
cd /home/bilal/Desktop/Inverter
uv venv --python 3.11 .venv-mcp && uv pip install --python .venv-mcp/bin/python -r requirements-mcp.txt
install -m 600 deploy/inverter-mcp.env.example ~/.config/inverter-mcp.env   # set INVERTER_PASSWORD and INVERTER_MCP_TOKEN
sudo cp deploy/inverter-mcp.service /etc/systemd/system/
sudo systemctl enable --now inverter-mcp
curl http://127.0.0.1:8765/healthz                                           # {"ok": true, ...}
```

The endpoint is `http://192.168.18.130:8765/mcp`; every request needs `Authorization: Bearer <INVERTER_MCP_TOKEN>`.
Hosts that cannot send a header (claude.ai custom connectors) can use the secret-URL form instead:
`http://192.168.18.130:8765/<INVERTER_MCP_TOKEN>/mcp`. Treat that URL like a password.
From Claude Code on any machine on the LAN:

```bash
claude mcp add --scope user --transport http inverter-pi http://192.168.18.130:8765/mcp \
  --header "Authorization: Bearer <INVERTER_MCP_TOKEN>"
```

Your own chatbot connects with any MCP client library, for example the Python SDK:

```python
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

async with httpx2.AsyncClient(headers={"Authorization": "Bearer <token>"},
                              timeout=httpx2.Timeout(30, read=300)) as http:
    async with Client(streamable_http_client("http://192.168.18.130:8765/mcp", http_client=http)) as client:
        print((await client.call_tool("get_live_status")).structured_content["summary"])
```

## claude.ai and other hosts away from the LAN (the AWS relay URL)

The dashboard's permanent address, `https://sve57w70a8.execute-api.ap-south-1.amazonaws.com`, also serves
MCP. The Lambda accepts `POST /mcp` and `POST /<token>/mcp`, checks the token against the `mcp_token`
parameter in SSM, forwards the request to the Pi over the WebSocket the Pi already keeps open
(`aws_relay.py` replays it against the local MCP server), and waits for the reply through the DynamoDB
table. Nothing new listens anywhere; the Pi still only dials out.

```
claude.ai ──POST /<token>/mcp──► Lambda ──ws frame──► aws_relay.py ──► mcp_server.py :8765 ──► app.py
          ◄────── JSON reply ─── (table) ◄── mcp_reply ◄──┘
```

One-time setup:

```bash
export AWS_PROFILE=nursepal AWS_REGION=ap-south-1
PYTHON=.venv-mcp/bin/python aws/deploy.sh                      # Lambda with the /mcp route, 29 s timeout
python3 aws/set_secrets.py mcp-setup --pi bilal@192.168.18.130  # mcp_token in SSM and on the Pi, restart, prints the URL
```

`mcp-setup` creates `/inverter-relay/mcp_token` if missing, writes the same value plus
`INVERTER_MCP_JSON_RESPONSE=1` and `INVERTER_MCP_STATELESS=1` into the Pi's `~/.config/inverter-mcp.env`,
restarts `inverter-mcp.service`, and prints the connector URL. It is safe to re-run.

Then print the URL and paste it into claude.ai under Settings → Connectors → Add custom connector, leaving
the OAuth fields empty:

```bash
python3 aws/set_secrets.py mcp-url
# https://sve57w70a8.execute-api.ap-south-1.amazonaws.com/<token>/mcp
```

Treat that URL like a password. Hosts that can send headers (Claude Code, Claude Desktop, SDK clients) use
`https://sve57w70a8.execute-api.ap-south-1.amazonaws.com/mcp` with `Authorization: Bearer <token>`:

```bash
claude mcp add --scope user --transport http inverter-aws \
  https://sve57w70a8.execute-api.ap-south-1.amazonaws.com/mcp --header "Authorization: Bearer <token>"
```

Each call costs one Lambda invocation that waits for the Pi (under a second of overhead; a priority change
takes about 6 s end to end). The relay serves only POST: it answers GET with 405 and DELETE with 200, which
is what a stateless MCP server expects. CI restarts `inverter-mcp.service` and `inverter-relay.service` on
every deploy and refreshes the MCP venv from `requirements-mcp.txt`.

An ngrok unit (`deploy/ngrok-mcp.service`, reserved domain `unmangled-apollo-baculine.ngrok-free.dev`) is kept
as a fallback for a direct tunnel to port 8765; it is not enabled.

## Tests

```bash
.venv-mcp/bin/python -m pytest tests/test_app_client.py tests/test_mcp_server.py
```

`test_app_client.py` runs the login / CSRF / re-login flow against a fake dashboard; `test_mcp_server.py` drives
the server through the SDK's in-memory client with the dashboard faked out, and checks that the priority tables
match `inverter_status.py`. Both are skipped automatically where the `mcp` package is not installed.
