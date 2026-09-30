#!/usr/bin/env python3
"""Raspberry Pi side of the AWS relay.

Keeps one outbound WebSocket to the relay API as the "device". While at least one
browser ("viewer") is connected it posts a compact live status once a second straight
to each viewer connection through the API Gateway management endpoint. Viewers' data
requests arrive as RPC frames; each is replayed against the local Flask app on
localhost (as an ordinary logged-in client) and the reply is posted back to that viewer,
gzipped and chunked to stay under API Gateway's 128 KB frame limit.

Nothing about the readings leaves the Pi except what a connected viewer asked for, plus a
few-KB "last seen" snapshot every few minutes so the page can say when the Pi went dark.

Configuration comes from the environment (see aws/inverter-relay.service):
  RELAY_WS_URL, RELAY_DEVICE_SECRET, RELAY_MGMT_ENDPOINT, AWS_REGION,
  AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (execute-api:ManageConnections only),
  LOCAL_APP_URL (default http://127.0.0.1:5000), LOCAL_APP_USERNAME, LOCAL_APP_PASSWORD.
"""
from __future__ import annotations

import asyncio
import base64
import gzip
import json
import logging
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s relay %(message)s")
log = logging.getLogger("relay")

WS_URL = os.environ.get("RELAY_WS_URL", "")
DEVICE_SECRET = os.environ.get("RELAY_DEVICE_SECRET", "")
MGMT_ENDPOINT = os.environ.get("RELAY_MGMT_ENDPOINT", "")
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
LOCAL_APP_URL = os.environ.get("LOCAL_APP_URL", "http://127.0.0.1:5000").rstrip("/")
LOCAL_USER = os.environ.get("LOCAL_APP_USERNAME", "admin")
LOCAL_PASS = os.environ.get("LOCAL_APP_PASSWORD", "")

PUSH_INTERVAL_S = float(os.environ.get("PUSH_INTERVAL_S", "1.0"))
STATS_INTERVAL_S = float(os.environ.get("STATS_INTERVAL_S", "60"))
SNAPSHOT_INTERVAL_S = float(os.environ.get("SNAPSHOT_INTERVAL_S", "300"))
PING_INTERVAL_S = float(os.environ.get("PING_INTERVAL_S", "240"))

# Only these local paths may be reached through the relay. Mirrors static/js/relay.js.
ALLOWED_PREFIXES = (
    "/status", "/summary", "/stats", "/stats-payload", "/history", "/recent-readings",
    "/day-readings", "/outages", "/data-gaps", "/raw-data", "/export-readings", "/warnings",
    "/savings", "/fesco", "/ai", "/config", "/refresh-extras", "/recompute-daily",
    "/inverter", "/set-output-priority", "/set-charger-priority",
)
BLOCKED_PATHS = ("/login", "/logout")
CHUNK_CHARS_B64 = 90_000      # base64 text; well under the 128 KB frame after the JSON envelope
CHUNK_CHARS_TEXT = 60_000     # identity text may contain multi-byte characters
RPC_TIMEOUT_S = 170


def path_allowed(path: str) -> bool:
    if not path.startswith("/") or path.startswith("//") or ".." in path:
        return False
    if path in BLOCKED_PATHS:
        return False
    return any(path == p or path.startswith(p + "/") for p in ALLOWED_PREFIXES)


def encode_reply(rpc_id, status: int, ctype: str, body: bytes, accept_enc: str,
                 headers: dict | None = None):
    """Yield the frames that carry one HTTP reply back to a viewer."""
    if accept_enc == "gzip+b64" and len(body) > 512:
        data, enc, chunk = base64.b64encode(gzip.compress(body, 6)).decode("ascii"), "gzip+b64", CHUNK_CHARS_B64
    else:
        data, enc, chunk = body.decode("utf-8", "replace"), "identity", CHUNK_CHARS_TEXT
    parts = [data[i:i + chunk] for i in range(0, len(data), chunk)] or [""]
    for i, part in enumerate(parts):
        frame = {"type": "rpc", "id": rpc_id, "status": status, "ctype": ctype, "enc": enc,
                 "part": i, "parts": len(parts), "data": part}
        if i == 0 and headers:
            frame["headers"] = headers
        yield frame


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LocalApp:
    """Synchronous client for the Flask app on localhost. Logs in like a browser and keeps
    the session cookie by hand (it is flagged Secure, which cookie jars refuse to send over
    plain http to loopback). Used from worker threads."""

    def __init__(self):
        self._opener = urllib.request.build_opener(_NoRedirect())
        self._cookie: str | None = None
        self._csrf: str | None = None
        self._last_login_attempt = 0.0

    @staticmethod
    def _set_cookie(headers) -> str | None:
        for h in headers.get_all("Set-Cookie") or []:
            if h.startswith("session="):
                return h.split(";", 1)[0]
        return None

    def _open(self, req, timeout=60):
        try:
            resp = self._opener.open(req, timeout=timeout)
            return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def login(self) -> bool:
        now = time.monotonic()
        if now - self._last_login_attempt < 15:      # respect the app's 5/min login limit
            return False
        self._last_login_attempt = now
        status, headers, body = self._open(urllib.request.Request(f"{LOCAL_APP_URL}/login"))
        pre_cookie = self._set_cookie(headers)
        m = re.search(rb'name="csrf_token" value="([^"]+)"', body)
        if status != 200 or not m or not pre_cookie:
            log.warning("login page unavailable (status %s)", status)
            return False
        form = urllib.parse.urlencode({"csrf_token": m.group(1).decode(), "username": LOCAL_USER,
                                       "password": LOCAL_PASS}).encode()
        req = urllib.request.Request(f"{LOCAL_APP_URL}/login", data=form, method="POST",
                                     headers={"Cookie": pre_cookie, "Content-Type": "application/x-www-form-urlencoded"})
        status, headers, _ = self._open(req)
        cookie = self._set_cookie(headers)
        if status != 302 or not cookie:
            log.error("local login failed (status %s)", status)
            return False
        self._cookie = cookie
        status, headers, body = self._open(urllib.request.Request(f"{LOCAL_APP_URL}/", headers={"Cookie": cookie}))
        # Rendering the page stores the CSRF secret in the session, so Flask re-issues the
        # cookie here; the token in the meta tag is only valid together with that cookie.
        self._adopt_cookie(headers)
        m = re.search(rb'name="csrf-token" content="([^"]+)"', body)
        self._csrf = m.group(1).decode() if m else None
        log.info("logged in to local app")
        return True

    def _adopt_cookie(self, headers) -> None:
        """Flask refreshes permanent sessions on every response; keep the newest cookie."""
        new = self._set_cookie(headers)
        if new:
            self._cookie = new

    def request(self, method: str, path: str, query: str = "", body: str | None = None,
                ctype: str | None = None, timeout: int = 60, _retry: bool = True):
        if self._cookie is None and not self.login():
            return 503, "application/json", json.dumps({"error": "local app login failed"}).encode(), {}
        url = f"{LOCAL_APP_URL}{path}" + (f"?{query}" if query else "")
        headers = {"Cookie": self._cookie or "", "Accept": "application/json, text/csv;q=0.9, */*;q=0.5"}
        data = None
        if method not in ("GET", "HEAD"):
            headers["X-CSRFToken"] = self._csrf or ""
            if body is not None:
                data = body.encode() if isinstance(body, str) else body
                headers["Content-Type"] = ctype or "application/json"
        status, resp_headers, payload = self._open(
            urllib.request.Request(url, data=data, method=method, headers=headers), timeout)
        self._adopt_cookie(resp_headers)
        if status in (401, 302) and _retry:
            self._cookie = None
            if self.login():
                return self.request(method, path, query, body, ctype, timeout, _retry=False)
        out_headers = {}
        cd = resp_headers.get("Content-Disposition")
        if cd:
            out_headers["content-disposition"] = cd
        return status, resp_headers.get("Content-Type", "application/octet-stream"), payload, out_headers


def _strip(status: dict) -> dict:
    return {k: v for k, v in status.items() if k != "raw_data"}


class Relay:
    def __init__(self):
        import boto3
        self.local = LocalApp()
        self.mgmt = boto3.client("apigatewaymanagementapi", endpoint_url=MGMT_ENDPOINT, region_name=AWS_REGION)
        self.viewers: set[str] = set()
        self.gone: set[str] = set()
        self.ws = None
        self.stats_due = True
        self._last_stats = 0.0

    # ---- management-endpoint posts (device -> viewer), run in threads -----------------
    def _post_sync(self, vid: str, obj: dict) -> bool:
        try:
            self.mgmt.post_to_connection(ConnectionId=vid, Data=json.dumps(obj).encode())
            return True
        except self.mgmt.exceptions.GoneException:
            self.viewers.discard(vid)
            self.gone.add(vid)
            return False
        except Exception as e:  # throttling, transient network: skip this frame
            log.warning("post to %s failed: %s", vid, str(e)[:160])
            return False

    async def post(self, vid: str, obj: dict) -> bool:
        return await asyncio.to_thread(self._post_sync, vid, obj)

    async def broadcast(self, obj: dict):
        if not self.viewers:
            return
        await asyncio.gather(*(self.post(v, obj) for v in list(self.viewers)))
        await self._report_gone()

    async def _report_gone(self):
        if self.gone and self.ws is not None:
            ids = list(self.gone)
            self.gone.clear()
            await self.ws.send(json.dumps({"action": "gone", "ids": ids}))

    # ---- frames from the Lambda -----------------------------------------------------------
    async def handle(self, raw: str):
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        t = msg.get("type")
        if t == "viewers":
            new = set(msg.get("ids") or [])
            if new != self.viewers:
                log.info("viewers: %d -> %d", len(self.viewers), len(new))
                if new - self.viewers:
                    self.stats_due = True
                self.viewers = new
        elif t == "rpc":
            asyncio.create_task(self.handle_rpc(msg))
        elif t == "pong":
            pass

    async def handle_rpc(self, msg: dict):
        vid, rpc_id = msg.get("from"), msg.get("id")
        path = msg.get("path") or "/"
        method = (msg.get("method") or "GET").upper()
        accept = msg.get("accept_enc") or "identity"
        if not vid:
            return
        if not path_allowed(path) or method not in ("GET", "POST", "DELETE"):
            frames = encode_reply(rpc_id, 403, "application/json",
                                  json.dumps({"error": "path not allowed through relay"}).encode(), "identity")
        else:
            timeout = RPC_TIMEOUT_S if path.startswith(("/export-readings", "/recompute-daily")) else 45
            try:
                status, ctype, body, headers = await asyncio.to_thread(
                    self.local.request, method, path, msg.get("query") or "", msg.get("body"), msg.get("ctype"), timeout)
            except Exception as e:
                log.warning("rpc %s %s failed: %s", method, path, e)
                status, ctype, body, headers = 502, "application/json", json.dumps({"error": str(e)[:200]}).encode(), {}
            frames = encode_reply(rpc_id, status, ctype, body, accept, headers)
        for frame in frames:
            if not await self.post(vid, frame):
                break
        await self._report_gone()

    # ---- periodic tasks -----------------------------------------------------------------------
    async def pusher(self):
        while True:
            await asyncio.sleep(PUSH_INTERVAL_S)
            if not self.viewers:
                continue
            try:
                status, _, body, _ = await asyncio.to_thread(self.local.request, "GET", "/status", "", None, None, 10)
                if status == 200:
                    await self.broadcast({"type": "inverter_update", "data": _strip(json.loads(body))})
                now = time.monotonic()
                if self.stats_due or now - self._last_stats >= STATS_INTERVAL_S:
                    s, _, sbody, _ = await asyncio.to_thread(self.local.request, "GET", "/stats-payload", "", None, None, 20)
                    if s == 200:
                        await self.broadcast({"type": "stats_update", "data": json.loads(sbody)})
                        self._last_stats, self.stats_due = now, False
            except Exception as e:
                log.warning("push failed: %s", e)

    async def snapshotter(self):
        while True:
            ok = False
            try:
                status, _, body, _ = await asyncio.to_thread(self.local.request, "GET", "/status", "", None, None, 10)
                s, _, sbody, _ = await asyncio.to_thread(self.local.request, "GET", "/stats-payload", "", None, None, 20)
                if status == 200 and s == 200 and self.ws is not None:
                    snap = {"status": _strip(json.loads(body)), "stats": json.loads(sbody), "at": int(time.time())}
                    await self.ws.send(json.dumps({"action": "snapshot", "data": snap}))
                    ok = True
            except Exception as e:
                log.warning("snapshot failed: %s", e)
            # After a reboot this fires before Flask has bound its port; retry soon rather than
            # leaving the page without a last-seen snapshot for a whole interval.
            await asyncio.sleep(SNAPSHOT_INTERVAL_S if ok else 20)

    async def pinger(self):
        while True:
            await asyncio.sleep(PING_INTERVAL_S)
            if self.ws is not None:
                await self.ws.send(json.dumps({"action": "ping"}))

    # ---- connection loop ------------------------------------------------------------------------
    async def run(self):
        import websockets
        backoff = 1.0
        url = f"{WS_URL}?role=device&secret={urllib.parse.quote(DEVICE_SECRET)}"
        while True:
            try:
                async with websockets.connect(url, ping_interval=None, max_size=256_000, open_timeout=20) as ws:
                    self.ws = ws
                    backoff = 1.0
                    log.info("connected to relay")
                    await ws.send(json.dumps({"action": "viewers?"}))
                    tasks = [asyncio.create_task(c()) for c in (self.pusher, self.snapshotter, self.pinger)]
                    try:
                        async for raw in ws:
                            await self.handle(raw)
                    finally:
                        for t in tasks:
                            t.cancel()
                        self.ws = None
                log.info("relay connection closed; reconnecting")
            except Exception as e:
                log.warning("relay connection error: %s", str(e)[:200])
            await asyncio.sleep(backoff + random.uniform(0, 1))
            backoff = min(backoff * 2, 30.0)


def main():
    missing = [k for k, v in (("RELAY_WS_URL", WS_URL), ("RELAY_DEVICE_SECRET", DEVICE_SECRET),
                              ("RELAY_MGMT_ENDPOINT", MGMT_ENDPOINT), ("LOCAL_APP_PASSWORD", LOCAL_PASS)) if not v]
    if missing:
        raise SystemExit(f"missing environment: {', '.join(missing)}")
    asyncio.run(Relay().run())


if __name__ == "__main__":
    main()
