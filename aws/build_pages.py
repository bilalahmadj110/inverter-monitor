#!/usr/bin/env python3
"""Pre-render the Flask templates into static HTML for the relay Lambda.

The Lambda serves these copies from its package; the Pi keeps serving the live Jinja
templates. Rendering happens here, at deploy time, with a stand-in context:
url_for() maps to fixed paths, csrf_token() is blank (the relay authenticates writes on
the WebSocket, not with form tokens) and a <!--RELAY--> marker is placed at the top of
<head> for the Lambda to swap for the relay bootstrap script. Socket.IO script tags are
dropped because relay.js provides io().
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "aws" / "lambda"
PAGES = ["solar_flow.html", "history.html", "savings.html", "fesco_bill.html", "dashboard.html", "login.html"]


def _url_for(endpoint: str, **kw) -> str:
    if endpoint == "static":
        return "/static/" + kw.get("filename", "")
    return {"auth.logout": "/logout", "auth.login": "/login", "dashboard": "/"}.get(endpoint, "/" + endpoint)


def main() -> int:
    try:
        sha = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        sha = "dev"
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=True)
    ctx = {"url_for": _url_for, "csrf_token": lambda: "", "app_version": sha, "error": None}

    pages_dir = OUT / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    for name in PAGES:
        html = env.get_template(name).render(**ctx)
        html = html.replace("<head>", "<head>\n<!--RELAY-->", 1)
        html = re.sub(r"<script[^>]+socket\.io[^>]*>\s*</script>\s*", "", html)
        if name == "login.html":
            html = html.replace("<form", "<!--LOGIN_ERROR-->\n        <form", 1)
        (pages_dir / name).write_text(html, encoding="utf-8")
        print(f"rendered {name} ({len(html)} bytes)")

    static_dst = OUT / "static"
    if static_dst.exists():
        shutil.rmtree(static_dst)
    shutil.copytree(ROOT / "static", static_dst, ignore=shutil.ignore_patterns(".DS_Store", "*.map"))
    if not (static_dst / "js" / "relay.js").exists():
        print("static/js/relay.js is missing", file=sys.stderr)
        return 1
    print(f"copied static -> {static_dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
