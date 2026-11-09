"""Unit tests for the AWS relay: Lambda handler helpers/routes that need no AWS calls, and
the Pi-side framing (path allow-list, gzip + chunked replies)."""
from __future__ import annotations

import base64
import gzip
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("AWS_DEFAULT_REGION", "ap-south-1")
os.environ.setdefault("TABLE_NAME", "test-table")
os.environ.setdefault("WS_URL", "wss://wsid.execute-api.ap-south-1.amazonaws.com/prod")
os.environ.setdefault("WS_MANAGEMENT_ENDPOINT", "https://wsid.execute-api.ap-south-1.amazonaws.com/prod")
os.environ.setdefault("HTTP_ORIGIN", "https://httpid.execute-api.ap-south-1.amazonaws.com")


@pytest.fixture(scope="module")
def handler():
    spec = importlib.util.spec_from_file_location("relay_handler", ROOT / "aws" / "lambda" / "handler.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def secret_param(handler, monkeypatch):
    values = {"token_secret": "unit-test-secret", "admin_username": "admin",
              "admin_password_hash": handler.hash_password("correct horse battery", iterations=1000),
              "device_secret": "device-secret-value"}
    monkeypatch.setattr(handler, "param", lambda name, ttl=300.0: values[name])
    return values


# ---- tokens and passwords ----------------------------------------------------------------

def test_token_roundtrip_and_tamper(handler):
    tok = handler.sign_token({"kind": "session", "u": "admin", "exp": int(time.time()) + 60}, "s3cret")
    assert handler.verify_token(tok, "s3cret", "session")["u"] == "admin"
    assert handler.verify_token(tok, "s3cret", "ws") is None                 # wrong kind
    assert handler.verify_token(tok, "other", "session") is None             # wrong secret
    body, sig = tok.split(".")
    assert handler.verify_token(body + "." + sig[:-2] + "xx", "s3cret", "session") is None
    assert handler.verify_token("garbage", "s3cret", "session") is None


def test_token_expiry(handler):
    tok = handler.sign_token({"kind": "ws", "exp": int(time.time()) - 1}, "s3cret")
    assert handler.verify_token(tok, "s3cret", "ws") is None


def test_password_hash_and_verify(handler):
    stored = handler.hash_password("hunter22", iterations=1000)
    assert stored.startswith("pbkdf2_sha256$1000$")
    assert handler.verify_password("hunter22", stored)
    assert not handler.verify_password("hunter23", stored)
    assert not handler.verify_password("hunter22", "not-a-hash")


# ---- HTTP routes that touch no AWS service -------------------------------------------------

def _http_event(method, path, cookies=None, query=None, body=None, headers=None):
    return {"requestContext": {"http": {"method": method, "sourceIp": "1.2.3.4"}},
            "rawPath": path, "queryStringParameters": query or {}, "cookies": cookies or [],
            "headers": headers or {}, "body": body}


def test_healthz(handler):
    r = handler.handle_http(_http_event("GET", "/healthz"))
    assert r["statusCode"] == 200
    assert json.loads(r["body"])["relay"] is True
    assert "Content-Security-Policy" in r["headers"]
    assert "wss://wsid.execute-api.ap-south-1.amazonaws.com" in r["headers"]["Content-Security-Policy"]


def test_pages_redirect_to_login_without_session(handler):
    r = handler.handle_http(_http_event("GET", "/savings"))
    assert r["statusCode"] == 302
    assert r["headers"]["Location"] == "/login?next=/savings"


def test_data_paths_are_not_served_over_http(handler, secret_param):
    tok = handler.sign_token({"kind": "session", "u": "admin", "exp": int(time.time()) + 60}, "unit-test-secret")
    r = handler.handle_http(_http_event("GET", "/summary", cookies=[f"session={tok}"]))
    assert r["statusCode"] == 404
    assert "WebSocket" in json.loads(r["body"])["hint"]


def test_relay_token_requires_session_and_mints_ws_token(handler, secret_param):
    assert handler.handle_http(_http_event("GET", "/relay/token"))["statusCode"] == 401
    tok = handler.sign_token({"kind": "session", "u": "admin", "exp": int(time.time()) + 60}, "unit-test-secret")
    r = handler.handle_http(_http_event("GET", "/relay/token", cookies=[f"session={tok}"]))
    assert r["statusCode"] == 200
    body = json.loads(r["body"])
    assert body["ws_url"].startswith("wss://")
    assert handler.verify_token(body["token"], "unit-test-secret", "ws")["u"] == "admin"
    assert handler.verify_token(body["token"], "unit-test-secret", "session") is None   # not usable as a cookie


def test_login_page_has_no_relay_bootstrap(handler, monkeypatch, tmp_path):
    # Regression: the bootstrap on /login made relay.js fetch a token, get 401 and reload /login forever.
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "login.html").write_text("<html><head>\n<!--RELAY--></head><body><!--LOGIN_ERROR--><form></form></body></html>")
    (tmp_path / "pages" / "solar_flow.html").write_text("<html><head>\n<!--RELAY--></head><body></body></html>")
    monkeypatch.setattr(handler, "HERE", tmp_path)
    monkeypatch.setattr(handler, "param", lambda name, ttl=300.0: "unit-test-secret")
    login = handler.handle_http(_http_event("GET", "/login"))
    assert login["statusCode"] == 200
    assert "window.RELAY" not in login["body"] and "relay.js" not in login["body"] and "<!--RELAY-->" not in login["body"]
    err = handler.handle_http(_http_event("GET", "/login", query={"e": "1"}))
    assert "Invalid username or password" in err["body"]
    tok = handler.sign_token({"kind": "session", "u": "admin", "exp": int(time.time()) + 60}, "unit-test-secret")
    page = handler.handle_http(_http_event("GET", "/", cookies=[f"session={tok}"]))
    assert page["statusCode"] == 200 and "window.RELAY=" in page["body"] and "/static/js/relay.js" in page["body"]


def test_static_is_confined_to_package(handler, monkeypatch, tmp_path):
    (tmp_path / "static" / "js").mkdir(parents=True)
    (tmp_path / "static" / "js" / "relay.js").write_text("// ok")
    (tmp_path / "secret.txt").write_text("nope")
    monkeypatch.setattr(handler, "HERE", tmp_path)
    ok = handler.handle_http(_http_event("GET", "/static/js/relay.js"))
    assert ok["statusCode"] == 200 and ok["isBase64Encoded"]
    assert base64.b64decode(ok["body"]) == b"// ok"
    assert handler.handle_http(_http_event("GET", "/static/../secret.txt"))["statusCode"] == 404


def test_login_post_rejects_foreign_origin_and_bad_password(handler, secret_param, monkeypatch):
    monkeypatch.setattr(handler, "_rate_limited", lambda ip: False)
    ev = _http_event("POST", "/login", body="username=admin&password=wrong",
                     headers={"origin": "https://evil.example"})
    assert handler.handle_http(ev)["statusCode"] == 403
    ev = _http_event("POST", "/login", body="username=admin&password=wrong")
    r = handler.handle_http(ev)
    assert r["statusCode"] == 302 and r["headers"]["Location"].startswith("/login?e=1")
    ev = _http_event("POST", "/login", body="username=admin&password=correct+horse+battery",
                     query={"next": "/reports"})
    r = handler.handle_http(ev)
    assert r["statusCode"] == 302 and r["headers"]["Location"] == "/reports"
    cookie = r["cookies"][0]
    assert "HttpOnly" in cookie and "Secure" in cookie
    tok = cookie.split(";")[0][len("session="):]
    assert handler.verify_token(tok, "unit-test-secret", "session")["u"] == "admin"


def test_login_open_redirect_is_blocked(handler, secret_param, monkeypatch):
    monkeypatch.setattr(handler, "_rate_limited", lambda ip: False)
    ev = _http_event("POST", "/login", body="username=admin&password=correct+horse+battery",
                     query={"next": "//evil.example/x"})
    assert handler.handle_http(ev)["headers"]["Location"] == "/"


# ---- WebSocket connect authorisation (rejected before any DynamoDB write) ---------------

def _ws_connect(role, **q):
    return {"requestContext": {"connectionId": "abc=", "eventType": "CONNECT"},
            "queryStringParameters": {"role": role, **q}, "headers": {}}


def test_ws_connect_rejects_bad_credentials(handler, secret_param):
    assert handler.handle_ws(_ws_connect("device", secret="wrong"))["statusCode"] == 401
    assert handler.handle_ws(_ws_connect("viewer", t="garbage"))["statusCode"] == 401
    expired = handler.sign_token({"kind": "ws", "exp": int(time.time()) - 5}, "unit-test-secret")
    assert handler.handle_ws(_ws_connect("viewer", t=expired))["statusCode"] == 401
    session_tok = handler.sign_token({"kind": "session", "exp": int(time.time()) + 60}, "unit-test-secret")
    assert handler.handle_ws(_ws_connect("viewer", t=session_tok))["statusCode"] == 401  # cookie token is not a ws token
    assert handler.handle_ws(_ws_connect("nobody"))["statusCode"] == 400


def test_ws_viewer_connect_checks_origin(handler, secret_param):
    tok = handler.sign_token({"kind": "ws", "exp": int(time.time()) + 60}, "unit-test-secret")
    ev = _ws_connect("viewer", t=tok)
    ev["headers"] = {"Origin": "https://evil.example"}
    assert handler.handle_ws(ev)["statusCode"] == 403


# ---- Pi-side framing ---------------------------------------------------------------------------

def test_relay_path_allowlist():
    import aws_relay
    assert aws_relay.path_allowed("/status")
    assert aws_relay.path_allowed("/fesco/cycle/Aug26/actual")
    assert aws_relay.path_allowed("/savings/data")
    assert not aws_relay.path_allowed("/login")
    assert not aws_relay.path_allowed("/logout")
    assert not aws_relay.path_allowed("/statusx")
    assert not aws_relay.path_allowed("/static/../app.py")
    assert not aws_relay.path_allowed("//evil")
    assert not aws_relay.path_allowed("relative")


def test_relay_gzip_chunked_reply_roundtrip():
    import aws_relay
    body = json.dumps({"rows": [{"t": i, "v": i * 1.5} for i in range(40_000)]}).encode()   # ~1 MB
    frames = list(aws_relay.encode_reply(7, 200, "application/json", body, "gzip+b64",
                                         headers={"content-disposition": "attachment; filename=x.json"}))
    assert all(f["enc"] == "gzip+b64" and f["parts"] == len(frames) for f in frames)
    assert [f["part"] for f in frames] == list(range(len(frames)))
    assert "headers" in frames[0] and all("headers" not in f for f in frames[1:])
    assert all(len(json.dumps(f).encode()) < 128 * 1024 for f in frames)
    joined = "".join(f["data"] for f in frames)
    assert gzip.decompress(base64.b64decode(joined)) == body


def test_relay_small_or_identity_reply_is_single_plain_frame():
    import aws_relay
    frames = list(aws_relay.encode_reply(1, 503, "application/json", b'{"error":"x"}', "gzip+b64"))
    assert len(frames) == 1 and frames[0]["enc"] == "identity" and frames[0]["data"] == '{"error":"x"}'
    frames = list(aws_relay.encode_reply(2, 200, "text/csv", b"a,b\n" * 50_000, "identity"))
    assert len(frames) == 4 and "".join(f["data"] for f in frames) == "a,b\n" * 50_000


def test_local_app_refreshes_expired_csrf_token(monkeypatch):
    """A POST that Flask rejects with 'CSRF token has expired' is retried once with a token
    read fresh from the dashboard page (the relay used to keep the login-time token forever)."""
    import aws_relay
    app = aws_relay.LocalApp()
    app._cookie = "session=abc"
    app._csrf = "stale"
    app._csrf_at = time.monotonic()
    calls = []

    def fake_open(req, timeout=60):
        calls.append((req.get_method(), req.full_url, req.get_header("X-csrftoken")))
        if req.get_method() == "GET":
            return 200, _Headers(), b'<meta name="csrf-token" content="fresh">'
        if req.get_header("X-csrftoken") == "stale":
            return 400, _Headers(), b"<h1>Bad Request</h1><p>The CSRF token has expired.</p>"
        return 200, _Headers(), b'{"success": true}'

    monkeypatch.setattr(app, "_open", fake_open)
    status, ctype, payload, _ = app.request("POST", "/refresh-extras")
    assert status == 200 and json.loads(payload)["success"] is True
    assert [c[0] for c in calls] == ["POST", "GET", "POST"]
    assert calls[-1][2] == "fresh" and app._csrf == "fresh"


class _Headers(dict):
    def get_all(self, name):
        return []


# ---- MCP over the relay -----------------------------------------------------------------------

class _FakeTable:
    """Just the DynamoDB calls the MCP path makes, in a dict."""

    def __init__(self):
        self.items = {}

    def get_item(self, Key, **_):
        return {"Item": self.items[Key["pk"]]} if Key["pk"] in self.items else {}

    def put_item(self, Item):
        self.items[Item["pk"]] = Item

    def delete_item(self, Key):
        self.items.pop(Key["pk"], None)

    def update_item(self, **_):
        pass


@pytest.fixture
def mcp_relay(handler, monkeypatch):
    import aws_relay
    table = _FakeTable()
    table.items["device"] = {"pk": "device", "connection_id": "dev-conn"}
    monkeypatch.setattr(handler, "_ddb", table)
    monkeypatch.setattr(handler, "param", lambda name, ttl=300.0: {"mcp_token": "tok-123"}[name])
    monkeypatch.setattr(handler, "MCP_POLL_S", 0.0)
    posted = []

    def fake_post(conn_id, obj):
        posted.append((conn_id, obj))
        if obj.get("type") == "mcp":
            # The Pi answers through the WebSocket; emulate its frames arriving on the $default route.
            body = json.dumps({"jsonrpc": "2.0", "id": 1,
                               "result": {"echo": obj["body"], "auth": obj["headers"].get("authorization"),
                                          "pad": "x" * 200_000}}).encode()       # forces several parts
            for frame in aws_relay.encode_reply(obj["id"], 200, "application/json", body, "gzip+b64"):
                frame["action"] = "mcp_reply"
                frame.pop("type", None)
                r = handler.handle_ws({"requestContext": {"connectionId": "dev-conn", "eventType": "MESSAGE"},
                                       "body": json.dumps(frame)})
                assert r["statusCode"] == 200
        return True

    monkeypatch.setattr(handler, "_post", fake_post)
    return handler, table, posted


def test_mcp_requires_the_token(mcp_relay):
    handler, _table, posted = mcp_relay
    assert handler.handle_http(_http_event("POST", "/mcp", body="{}"))["statusCode"] == 401
    assert handler.handle_http(_http_event("POST", "/wrong/mcp", body="{}"))["statusCode"] == 401
    r = handler.handle_http(_http_event("POST", "/mcp", body="{}", headers={"authorization": "Bearer nope"}))
    assert r["statusCode"] == 401 and r["headers"]["WWW-Authenticate"].startswith("Bearer")
    assert posted == []


def test_mcp_roundtrip_in_header_and_path_forms(mcp_relay):
    handler, table, posted = mcp_relay
    msg = '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
    for ev in (_http_event("POST", "/mcp", body=msg, headers={"authorization": "Bearer tok-123",
                                                               "content-type": "application/json"}),
               _http_event("POST", "/tok-123/mcp", body=msg)):
        r = handler.handle_http(ev)
        assert r["statusCode"] == 200 and r["headers"]["Content-Type"] == "application/json"
        body = json.loads(base64.b64decode(r["body"]))
        assert body["result"]["echo"] == msg
        assert body["result"]["auth"] == "Bearer tok-123"          # the Pi's MCP server checks it again
    assert len(posted) == 2 and all(conn == "dev-conn" and obj["type"] == "mcp" for conn, obj in posted)
    assert posted[0][1]["headers"]["content-type"] == "application/json"
    assert not [k for k in table.items if k.startswith("mcp#")]    # reply rows are cleaned up


def test_mcp_other_methods_and_pi_offline(mcp_relay):
    handler, table, _posted = mcp_relay
    hdr = {"authorization": "Bearer tok-123"}
    assert handler.handle_http(_http_event("GET", "/mcp", headers=hdr))["statusCode"] == 405
    assert handler.handle_http(_http_event("DELETE", "/mcp", headers=hdr))["statusCode"] == 200
    table.items["device"] = {"pk": "device"}
    r = handler.handle_http(_http_event("POST", "/mcp", body="{}", headers=hdr))
    assert r["statusCode"] == 503 and "not connected" in json.loads(r["body"])["error"]["message"]


def test_mcp_times_out_when_the_pi_is_silent(mcp_relay, monkeypatch):
    handler, _table, _posted = mcp_relay
    monkeypatch.setattr(handler, "_post", lambda conn, obj: True)
    monkeypatch.setattr(handler, "MCP_WAIT_S", 0.05)
    r = handler.handle_http(_http_event("POST", "/mcp", body="{}", headers={"authorization": "Bearer tok-123"}))
    assert r["statusCode"] == 504


def test_mcp_without_a_configured_token_is_not_found(handler, monkeypatch):
    from botocore.exceptions import ClientError

    def missing(name, ttl=300.0):
        raise ClientError({"Error": {"Code": "ParameterNotFound", "Message": "x"}}, "GetParameter")

    monkeypatch.setattr(handler, "param", missing)
    assert handler.handle_http(_http_event("POST", "/mcp", body="{}"))["statusCode"] == 404


def test_relay_handle_mcp_replays_locally_and_frames_the_reply(monkeypatch):
    import asyncio
    import aws_relay
    relay = aws_relay.Relay.__new__(aws_relay.Relay)      # skip the boto3 client in __init__
    sent = []

    class _WS:
        async def send(self, text):
            sent.append(json.loads(text))

    relay.ws = _WS()
    seen = {}

    def fake_request(headers, body):
        seen["headers"], seen["body"] = headers, body
        return 200, "application/json", json.dumps({"ok": True, "n": list(range(40_000))}).encode()

    monkeypatch.setattr(aws_relay, "mcp_request", fake_request)
    asyncio.run(relay.handle_mcp({"id": "r1", "method": "POST", "body": '{"jsonrpc":"2.0"}',
                                  "headers": {"authorization": "Bearer t", "content-type": "application/json",
                                              "x-forwarded-for": "1.1.1.1"}}))
    assert seen["body"] == '{"jsonrpc":"2.0"}'
    assert seen["headers"] == {"authorization": "Bearer t", "content-type": "application/json"}
    assert len(sent) >= 2 and all(f["action"] == "mcp_reply" and f["id"] == "r1" and "type" not in f for f in sent)
    assert json.loads(gzip.decompress(base64.b64decode("".join(f["data"] for f in sent))))["ok"] is True
