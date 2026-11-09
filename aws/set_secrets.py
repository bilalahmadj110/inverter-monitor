#!/usr/bin/env python3
"""Manage the relay's secrets in SSM Parameter Store and emit the Pi's environment file.

Uses the AWS CLI (no boto3 needed locally). Secrets are read from stdin, never from
argv, so they do not land in shell history or process listings.

  # admin login for the AWS-hosted pages (password on stdin)
  echo -n 'the-password' | python3 aws/set_secrets.py set-password --username admin

  # create token_secret / device_secret / mcp_token if they do not exist yet
  python3 aws/set_secrets.py ensure

  # MCP over the relay: token in SSM + on the Pi, service restart, and the claude.ai URL in one go
  python3 aws/set_secrets.py mcp-setup --pi bilal@192.168.18.130
  python3 aws/set_secrets.py mcp-url          # print the URL again later

  # print the Pi's env file (local app password on stdin). --create-key mints the
  # access key for the inverter-pi-relay IAM user; pipe the output straight to the Pi.
  echo -n 'local-app-password' | python3 aws/set_secrets.py pi-env --create-key \
      | ssh pi 'install -m 600 /dev/stdin ~/.config/inverter-relay.env'
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys


def aws(args: list[str], profile: str, region: str, input_text: str | None = None) -> str:
    cmd = ["aws", "--profile", profile, "--region", region, "--output", "json", *args]
    r = subprocess.run(cmd, capture_output=True, text=True, input=input_text)
    if r.returncode != 0:
        raise SystemExit(f"aws {' '.join(args[:3])} failed: {r.stderr.strip()[:300]}")
    return r.stdout


def hash_password(password: str, iterations: int = 600_000) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def put(name: str, value: str, secure: bool, a) -> None:
    aws(["ssm", "put-parameter", "--name", f"{a.prefix}/{name}", "--value", value,
         "--type", "SecureString" if secure else "String", "--overwrite"], a.profile, a.region)


def get(name: str, a) -> str | None:
    r = subprocess.run(["aws", "--profile", a.profile, "--region", a.region, "ssm", "get-parameter",
                        "--name", f"{a.prefix}/{name}", "--with-decryption", "--query", "Parameter.Value",
                        "--output", "text"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def stack_output(key: str, a) -> str:
    out = aws(["cloudformation", "describe-stacks", "--stack-name", a.stack,
               "--query", f"Stacks[0].Outputs[?OutputKey=='{key}'].OutputValue"], a.profile, a.region)
    vals = json.loads(out)
    if not vals:
        raise SystemExit(f"stack output {key} not found")
    return vals[0]


def cmd_set_password(a) -> None:
    password = sys.stdin.read().strip("\r\n")
    if len(password) < 8:
        raise SystemExit("password must be at least 8 characters (read from stdin)")
    put("admin_username", a.username, False, a)
    put("admin_password_hash", hash_password(password), True, a)
    print(f"stored admin_username={a.username} and a PBKDF2 hash under {a.prefix}/")


def cmd_ensure(a) -> None:
    # mcp_token is shorter because it also travels inside a URL (/<token>/mcp).
    for name, length in (("token_secret", 48), ("device_secret", 48), ("mcp_token", 24)):
        if get(name, a) is None:
            put(name, secrets.token_urlsafe(length), True, a)
            print(f"created {a.prefix}/{name}")
        else:
            print(f"{a.prefix}/{name} already exists")


def cmd_rotate(a) -> None:
    put(a.name, secrets.token_urlsafe(24 if a.name == "mcp_token" else 48), True, a)
    print(f"rotated {a.prefix}/{a.name}")


def cmd_pi_mcp_env(a) -> None:
    """Print the INVERTER_MCP_TOKEN line for the Pi's ~/.config/inverter-mcp.env; pipe it, don't paste it."""
    token = get("mcp_token", a)
    if not token:
        raise SystemExit("mcp_token missing; run `ensure` first")
    sys.stdout.write(f"INVERTER_MCP_TOKEN={token}\n")


def cmd_mcp_setup(a) -> None:
    """Everything the relay's /mcp route needs in one go: an mcp_token in SSM (created if missing), the same
    token plus the relay flags in the Pi's ~/.config/inverter-mcp.env, a restart of inverter-mcp.service,
    and the URL to paste into claude.ai. The token reaches the Pi only inside the SSH stdin stream."""
    if get("mcp_token", a) is None:
        put("mcp_token", secrets.token_urlsafe(24), True, a)
        print(f"created {a.prefix}/mcp_token")
    token = get("mcp_token", a)
    remote = f"""
import os, re, subprocess
line = "INVERTER_MCP_TOKEN=" + {token!r}
p = os.path.expanduser("~/.config/inverter-mcp.env")
s = open(p).read() if os.path.exists(p) else ""
if re.search(r"^INVERTER_MCP_TOKEN=", s, flags=re.M):
    s = re.sub(r"^INVERTER_MCP_TOKEN=.*$", line, s, flags=re.M)
else:
    s = s.rstrip("\n") + "\n" + line + "\n"
for extra in ("INVERTER_MCP_JSON_RESPONSE=1", "INVERTER_MCP_STATELESS=1"):
    if not re.search("^" + extra.split("=")[0] + "=", s, flags=re.M):
        s = s.rstrip("\n") + "\n" + extra + "\n"
open(p, "w").write(s)
os.chmod(p, 0o600)
r = subprocess.run(["sudo", "systemctl", "restart", "inverter-mcp.service"])
print("pi: env updated; inverter-mcp restart", "ok" if r.returncode == 0 else f"failed ({{r.returncode}})")
"""
    cmd = ["ssh", "-o", "BatchMode=yes", *(["-i", os.path.expanduser(a.key)] if a.key else []), a.pi, "python3", "-"]
    r = subprocess.run(cmd, input=remote, text=True)
    if r.returncode != 0:
        raise SystemExit(f"ssh to {a.pi} failed ({r.returncode}); the SSM token is in place, re-run to retry the Pi step")
    print(f"claude.ai connector URL: {stack_output('HttpUrl', a)}/{token}/mcp")


def cmd_mcp_url(a) -> None:
    """Print the URL to paste into claude.ai (Settings > Connectors > Add custom connector)."""
    token = get("mcp_token", a)
    if not token:
        raise SystemExit("mcp_token missing; run `ensure` first")
    print(f"{stack_output('HttpUrl', a)}/{token}/mcp")


def cmd_pi_env(a) -> None:
    local_password = sys.stdin.read().strip("\r\n")
    if not local_password:
        raise SystemExit("local app password expected on stdin")
    device_secret = get("device_secret", a)
    if not device_secret:
        raise SystemExit("device_secret missing; run `ensure` first")
    ws_url = stack_output("WsUrl", a)
    mgmt = stack_output("WsManagementEndpoint", a)
    user = stack_output("PiUserName", a)
    lines = [
        "# Inverter Monitor AWS relay (device side). Keep mode 600.",
        f"RELAY_WS_URL={ws_url}",
        f"RELAY_MGMT_ENDPOINT={mgmt}",
        f"RELAY_DEVICE_SECRET={device_secret}",
        f"AWS_REGION={a.region}",
        "LOCAL_APP_URL=http://127.0.0.1:5000",
        f"LOCAL_APP_USERNAME={a.username}",
        f"LOCAL_APP_PASSWORD={local_password}",
        "PUSH_INTERVAL_S=1.0",
    ]
    if a.create_key:
        key = json.loads(aws(["iam", "create-access-key", "--user-name", user], a.profile, a.region))["AccessKey"]
        lines += [f"AWS_ACCESS_KEY_ID={key['AccessKeyId']}", f"AWS_SECRET_ACCESS_KEY={key['SecretAccessKey']}"]
    else:
        lines += ["# AWS_ACCESS_KEY_ID=...", "# AWS_SECRET_ACCESS_KEY=..."]
    sys.stdout.write("\n".join(lines) + "\n")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--profile", default="nursepal")
    p.add_argument("--region", default="ap-south-1")
    p.add_argument("--prefix", default="/inverter-relay")
    p.add_argument("--stack", default="inverter-relay")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set-password"); s.add_argument("--username", default="admin"); s.set_defaults(fn=cmd_set_password)
    s = sub.add_parser("ensure"); s.set_defaults(fn=cmd_ensure)
    s = sub.add_parser("rotate"); s.add_argument("name", choices=["token_secret", "device_secret", "mcp_token"]); s.set_defaults(fn=cmd_rotate)
    s = sub.add_parser("pi-mcp-env"); s.set_defaults(fn=cmd_pi_mcp_env)
    s = sub.add_parser("mcp-url"); s.set_defaults(fn=cmd_mcp_url)
    s = sub.add_parser("mcp-setup"); s.add_argument("--pi", default="bilal@192.168.18.130"); s.add_argument("--key", default="~/.ssh/id_ed25519"); s.set_defaults(fn=cmd_mcp_setup)
    s = sub.add_parser("pi-env"); s.add_argument("--username", default="admin"); s.add_argument("--create-key", action="store_true"); s.set_defaults(fn=cmd_pi_env)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
