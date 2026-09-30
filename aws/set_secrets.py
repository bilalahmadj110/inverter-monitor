#!/usr/bin/env python3
"""Manage the relay's secrets in SSM Parameter Store and emit the Pi's environment file.

Uses the AWS CLI (no boto3 needed locally). Secrets are read from stdin, never from
argv, so they do not land in shell history or process listings.

  # admin login for the AWS-hosted pages (password on stdin)
  echo -n 'the-password' | python3 aws/set_secrets.py set-password --username admin

  # create token_secret / device_secret if they do not exist yet
  python3 aws/set_secrets.py ensure

  # print the Pi's env file (local app password on stdin). --create-key mints the
  # access key for the inverter-pi-relay IAM user; pipe the output straight to the Pi.
  echo -n 'local-app-password' | python3 aws/set_secrets.py pi-env --create-key \
      | ssh pi 'install -m 600 /dev/stdin ~/.config/inverter-relay.env'
"""
from __future__ import annotations

import argparse
import hashlib
import json
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
    for name in ("token_secret", "device_secret"):
        if get(name, a) is None:
            put(name, secrets.token_urlsafe(48), True, a)
            print(f"created {a.prefix}/{name}")
        else:
            print(f"{a.prefix}/{name} already exists")


def cmd_rotate(a) -> None:
    put(a.name, secrets.token_urlsafe(48), True, a)
    print(f"rotated {a.prefix}/{a.name}")


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
    s = sub.add_parser("rotate"); s.add_argument("name", choices=["token_secret", "device_secret"]); s.set_defaults(fn=cmd_rotate)
    s = sub.add_parser("pi-env"); s.add_argument("--username", default="admin"); s.add_argument("--create-key", action="store_true"); s.set_defaults(fn=cmd_pi_env)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
