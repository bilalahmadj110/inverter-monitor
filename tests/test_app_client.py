"""lib.app_client against a fake dashboard: the browser-style login, the CSRF header on POST,
re-login when the session is gone, the login rate guard, and error mapping. Standard library
only (http.server); no Flask, no inverter."""
from __future__ import annotations

import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lib.app_client import AppError, InverterAppClient

CSRF_FORM = "form-token"
CSRF_META = "meta-token"
PASSWORD = "secret-pass"


class FakeDashboard(BaseHTTPRequestHandler):
    """Just enough of app.py + auth.py: /login form + redirect-on-success, Secure session cookie,
    302-to-login for anonymous reads, CSRF meta tag on /, X-CSRFToken required on POST."""

    def log_message(self, *args):  # keep pytest output clean
        pass

    @property
    def st(self):
        return self.server.state

    def _cookie(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            part = part.strip()
            if part.startswith("session="):
                return part[len("session="):]
        return None

    def _authed(self):
        return self._cookie() in self.st["valid"]

    def _send(self, status, body=b"", ctype="application/json", headers=()):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, obj):
        self._send(status, json.dumps(obj).encode())

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        self.st["requests"].append(("GET", self.path, {k.lower(): v for k, v in self.headers.items()}))
        if url.path == "/login":
            return self._send(200, f'<form><input name="csrf_token" value="{CSRF_FORM}"></form>'.encode(),
                              "text/html", [("Set-Cookie", "session=pre; Secure; HttpOnly; Path=/")])
        if not self._authed():
            return self._send(302, b"", "text/html", [("Location", "/login?next=" + url.path)])
        if url.path == "/":
            return self._send(200, f'<meta name="csrf-token" content="{CSRF_META}">'.encode(), "text/html",
                              [("Set-Cookie", f"session={self._cookie()}; Secure; HttpOnly; Path=/")])
        if url.path == "/status":
            return self._json(200, {"success": True, "metrics": {}})
        if url.path == "/summary":
            return self._json(200, {"date": urllib.parse.parse_qs(url.query).get("date", [None])[0],
                                    "query": url.query})
        if url.path == "/no-reading":
            return self._json(503, {"success": False, "error": "No reading available yet"})
        if url.path == "/boom":
            return self._send(500, b"<html>Internal Server Error</html>", "text/html")
        if url.path == "/text":
            return self._send(200, b"plain text", "text/plain")
        return self._json(404, {"error": "nope"})

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        url = urllib.parse.urlparse(self.path)
        self.st["requests"].append(("POST", self.path, {k.lower(): v for k, v in self.headers.items()}, raw))
        if url.path == "/login":
            form = urllib.parse.parse_qs(raw.decode())
            if form.get("csrf_token") != [CSRF_FORM] or self._cookie() != "pre":
                return self._send(400, b"The CSRF token is missing.", "text/html")
            if form.get("password") != [PASSWORD]:
                return self._send(401, b"<form>Invalid username or password.</form>", "text/html")
            self.st["logins"] += 1
            token = f"auth{self.st['logins']}"
            self.st["valid"].add(token)
            return self._send(302, b"", "text/html", [("Location", "/"), ("Set-Cookie", f"session={token}; Secure; Path=/")])
        if not self._authed():
            return self._json(401, {"error": "Unauthorized"})
        if self.headers.get("X-CSRFToken") != CSRF_META:
            return self._send(400, b"<p>The CSRF token is missing.</p>", "text/html")
        if url.path == "/set-output-priority":
            body = json.loads(raw or b"{}")
            if body.get("mode") not in ("SBU", "SOL", "UTI"):
                return self._json(400, {"success": False, "error": f"Invalid output priority '{body.get('mode')}'"})
            return self._json(200, {"success": True, "previous": "SOL",
                                    "applied": {"mode": body["mode"], "command": "POP02"},
                                    "config": {"output_priority": body["mode"]}})
        return self._json(404, {"error": "nope"})


@pytest.fixture
def dashboard():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeDashboard)
    srv.state = {"valid": set(), "logins": 0, "requests": []}
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.fixture
def client(dashboard):
    return InverterAppClient(f"http://127.0.0.1:{dashboard.server_address[1]}", "admin", PASSWORD, timeout=5)


def _posts(dashboard, path):
    return [r for r in dashboard.state["requests"] if r[0] == "POST" and r[1].startswith(path)]


def test_logs_in_once_and_sends_the_session_cookie(client, dashboard):
    assert client.get("/status") == {"success": True, "metrics": {}}
    assert client.get("/status")["success"] is True
    assert dashboard.state["logins"] == 1
    status_reads = [r for r in dashboard.state["requests"] if r[1] == "/status"]
    assert len(status_reads) == 2
    assert all(r[2].get("cookie") == "session=auth1" for r in status_reads)


def test_query_params_skip_none(client):
    out = client.get("/summary", date="2026-11-01", bucket=None)
    assert out["date"] == "2026-11-01"
    assert "bucket" not in out["query"]


def test_post_carries_csrf_token_and_json(client, dashboard):
    out = client.post("/set-output-priority", {"mode": "SBU"})
    assert out["success"] is True and out["config"]["output_priority"] == "SBU"
    (post,) = _posts(dashboard, "/set-output-priority")
    # urllib sends header names capitalised ("X-csrftoken"); Flask reads them case-insensitively, and so
    # does the fake, so the recorder lower-cases every name.
    assert post[2].get("x-csrftoken") == CSRF_META
    assert post[2].get("content-type") == "application/json"
    assert json.loads(post[3]) == {"mode": "SBU"}


def test_relogin_when_the_session_is_gone(client, dashboard):
    client.get("/status")
    dashboard.state["valid"].clear()          # the app restarted / the session expired
    client._last_login_attempt = -1e9         # skip the login rate guard for the test
    assert client.get("/status")["success"] is True
    assert dashboard.state["logins"] == 2


def test_wrong_password_is_a_clear_error(dashboard):
    bad = InverterAppClient(f"http://127.0.0.1:{dashboard.server_address[1]}", "admin", "wrong", timeout=5)
    with pytest.raises(AppError) as info:
        bad.get("/status")
    assert info.value.status == 401
    assert "password" in info.value.message
    # A second attempt right away is held back instead of burning the dashboard's 5/min login limit.
    with pytest.raises(AppError) as info2:
        bad.get("/status")
    assert info2.value.status == 429
    assert dashboard.state["logins"] == 0


def test_error_mapping(client):
    with pytest.raises(AppError) as e503:
        client.get("/no-reading")
    assert (e503.value.status, e503.value.message) == (503, "No reading available yet")
    with pytest.raises(AppError) as e500:
        client.get("/boom")
    assert e500.value.status == 500 and e500.value.message == "dashboard error"
    with pytest.raises(AppError) as e404:
        client.get("/missing")
    assert e404.value.status == 404 and e404.value.message == "nope"
    with pytest.raises(AppError) as e400:
        client.post("/set-output-priority", {"mode": "XYZ"})
    assert e400.value.status == 400 and "Invalid output priority" in e400.value.message


def test_non_json_reply_is_returned_as_text(client):
    assert client.get("/text") == "plain text"
