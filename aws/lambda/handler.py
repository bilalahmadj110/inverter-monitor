"""Inverter Monitor relay Lambda.

One function behind two API Gateway v2 APIs:

  HTTP API   - login, the dashboard pages (pre-rendered copies of the Flask templates)
               and static assets. Session = signed cookie. Nothing else is served over
               HTTP: every data call the pages make is tunnelled over the WebSocket.
  WebSocket  - the Raspberry Pi connects once as the "device" (shared secret); browsers
               connect as "viewers" (short-lived token minted for a valid session).
               Viewer -> device: request/reply RPC frames that the Pi answers by calling
               its own Flask app on localhost and posting the reply straight back to the
               viewer connection. Device -> viewers: live readings, pushed by the Pi
               directly through the management endpoint while at least one viewer is
               connected, so this function is not invoked per reading.

State: one DynamoDB table with the device connection id, one row per viewer and an
optional last-known snapshot (a few KB) so the page can say when the Pi was last seen.
Secrets come from SSM Parameter Store and are cached for the life of the container.
"""
import base64
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import time
import urllib.parse
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

TABLE_NAME = os.environ["TABLE_NAME"]
WS_URL = os.environ["WS_URL"]
WS_MANAGEMENT_ENDPOINT = os.environ["WS_MANAGEMENT_ENDPOINT"]
HTTP_ORIGIN = os.environ.get("HTTP_ORIGIN", "").rstrip("/")
PARAM_PREFIX = os.environ.get("PARAM_PREFIX", "/inverter-relay").rstrip("/")
APP_VERSION = os.environ.get("APP_VERSION", "dev")

SESSION_TTL_S = 24 * 3600
WS_TOKEN_TTL_S = 10 * 60
ROW_TTL_S = 3 * 3600          # API Gateway closes sockets after 2 h; rows outlive that a little
LOGIN_MAX_PER_MINUTE = 5
LOGIN_MAX_PER_HOUR = 30
PAGES = {"/": "solar_flow.html", "/reports": "history.html", "/savings": "savings.html",
         "/fesco-bill": "fesco_bill.html", "/classic": "dashboard.html"}
HERE = Path(__file__).parent

_ddb = boto3.resource("dynamodb").Table(TABLE_NAME)
_ssm = boto3.client("ssm")
_mgmt = boto3.client("apigatewaymanagementapi", endpoint_url=WS_MANAGEMENT_ENDPOINT)
_param_cache: dict[str, tuple[float, str]] = {}


# ---- secrets -----------------------------------------------------------------------------

def param(name: str, ttl: float = 300.0) -> str:
    now = time.time()
    hit = _param_cache.get(name)
    if hit and now - hit[0] < ttl:
        return hit[1]
    value = _ssm.get_parameter(Name=f"{PARAM_PREFIX}/{name}", WithDecryption=True)["Parameter"]["Value"]
    _param_cache[name] = (now, value)
    return value


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64u_dec(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign_token(payload: dict, secret: str) -> str:
    body = _b64u(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    sig = _b64u(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_token(token: str, secret: str, kind: str) -> dict | None:
    try:
        body, sig = token.split(".", 1)
    except (ValueError, AttributeError):
        return None
    expected = _b64u(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(_b64u_dec(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if payload.get("kind") != kind or payload.get("exp", 0) < time.time():
        return None
    return payload


def hash_password(password: str, iterations: int = 600_000) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, digest = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations)).hex()
        return hmac.compare_digest(calc, digest)
    except (ValueError, AttributeError):
        return False


# ---- HTTP helpers ------------------------------------------------------------------------

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}


def _csp() -> str:
    ws_host = WS_URL.split("/")[2]
    return ("default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "img-src 'self' data:; font-src 'self' https://cdnjs.cloudflare.com data:; "
            f"connect-src 'self' wss://{ws_host}; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


def _resp(status: int, body: str | bytes = "", ctype: str = "text/plain; charset=utf-8",
          headers: dict | None = None, cookies: list[str] | None = None) -> dict:
    h = {"Content-Type": ctype, "Content-Security-Policy": _csp(), **SECURITY_HEADERS, **(headers or {})}
    out = {"statusCode": status, "headers": h}
    if isinstance(body, bytes):
        out["body"] = base64.b64encode(body).decode()
        out["isBase64Encoded"] = True
    else:
        out["body"] = body
    if cookies:
        out["cookies"] = cookies
    return out


def _json(status: int, obj) -> dict:
    return _resp(status, json.dumps(obj), "application/json")


def _redirect(location: str, cookies: list[str] | None = None) -> dict:
    return _resp(302, "", headers={"Location": location}, cookies=cookies)


def _cookie_session(event: dict) -> dict | None:
    for c in event.get("cookies") or []:
        if c.startswith("session="):
            return verify_token(c[len("session="):], param("token_secret"), "session")
    return None


def _client_ip(event: dict) -> str:
    return (event.get("requestContext", {}).get("http", {}) or {}).get("sourceIp", "?")


def _form(event: dict) -> dict:
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8", "replace")
    return {k: v[0] for k, v in urllib.parse.parse_qs(body, keep_blank_values=True).items()}


def _rate_limited(ip: str) -> bool:
    """Sliding counters in DynamoDB: 5/min and 30/hour per source IP on POST /login."""
    now = int(time.time())
    for window, limit in ((60, LOGIN_MAX_PER_MINUTE), (3600, LOGIN_MAX_PER_HOUR)):
        pk = f"login#{ip}#{window}#{now // window}"
        try:
            r = _ddb.update_item(Key={"pk": pk},
                                 UpdateExpression="ADD #n :one SET #t = if_not_exists(#t, :ttl)",
                                 ExpressionAttributeNames={"#n": "n", "#t": "ttl"},
                                 ExpressionAttributeValues={":one": 1, ":ttl": now + window + 60},
                                 ReturnValues="UPDATED_NEW")
            if int(r["Attributes"]["n"]) > limit:
                return True
        except ClientError:
            return False
    return False


def _page(name: str, error: str | None = None) -> str:
    html = (HERE / "pages" / name).read_text(encoding="utf-8")
    relay_boot = (f'<script>window.RELAY={json.dumps({"ws": WS_URL, "version": APP_VERSION})};</script>'
                  f'<script src="/static/js/relay.js?v={APP_VERSION}"></script>')
    html = html.replace("<!--RELAY-->", relay_boot, 1)
    if error:
        html = html.replace("<!--LOGIN_ERROR-->",
                            '<div class="mb-4 px-3 py-2 rounded-lg bg-red-500/15 border border-red-400/40 '
                            f'text-red-100 text-sm">{error}</div>', 1)
    return html


def handle_http(event: dict) -> dict:
    method = event["requestContext"]["http"]["method"]
    path = event.get("rawPath") or "/"
    query = event.get("queryStringParameters") or {}

    if path == "/healthz":
        return _json(200, {"ok": True, "version": APP_VERSION, "relay": True})

    if path.startswith("/static/"):
        rel = urllib.parse.unquote(path[len("/static/"):])
        target = (HERE / "static" / rel).resolve()
        if not str(target).startswith(str((HERE / "static").resolve())) or not target.is_file():
            return _resp(404, "not found")
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        return _resp(200, target.read_bytes(), ctype, headers={"Cache-Control": "public, max-age=3600"})

    if path == "/login":
        if method == "GET":
            return _resp(200, _page("login.html", error="Invalid username or password." if query.get("e") else None),
                         "text/html; charset=utf-8")
        if method == "POST":
            origin = (event.get("headers") or {}).get("origin")
            if HTTP_ORIGIN and origin and origin.rstrip("/") != HTTP_ORIGIN:
                return _resp(403, "bad origin")
            ip = _client_ip(event)
            if _rate_limited(ip):
                return _resp(429, "Too many attempts. Try again in a minute.")
            form = _form(event)
            ok = (hmac.compare_digest(form.get("username", ""), param("admin_username"))
                  and verify_password(form.get("password", ""), param("admin_password_hash")))
            nxt = query.get("next") or "/"
            if not nxt.startswith("/") or nxt.startswith("//"):
                nxt = "/"
            if not ok:
                print(json.dumps({"event": "login_fail", "ip": ip}))
                return _redirect(f"/login?e=1&next={urllib.parse.quote(nxt)}")
            token = sign_token({"kind": "session", "u": form["username"], "exp": int(time.time()) + SESSION_TTL_S,
                                "n": secrets.token_hex(8)}, param("token_secret"))
            print(json.dumps({"event": "login_ok", "ip": ip}))
            return _redirect(nxt, cookies=[f"session={token}; Path=/; Max-Age={SESSION_TTL_S}; HttpOnly; Secure; SameSite=Lax"])
        return _resp(405, "method not allowed")

    if path == "/logout":
        return _redirect("/login", cookies=["session=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax"])

    session = _cookie_session(event)
    if session is None:
        if path in PAGES:
            return _redirect(f"/login?next={urllib.parse.quote(path)}")
        return _json(401, {"error": "Unauthorized", "login_url": "/login"})

    if path == "/relay/token":
        token = sign_token({"kind": "ws", "u": session.get("u"), "exp": int(time.time()) + WS_TOKEN_TTL_S,
                            "n": secrets.token_hex(6)}, param("token_secret"))
        return _json(200, {"ws_url": WS_URL, "token": token, "version": APP_VERSION})

    if path in PAGES and method == "GET":
        return _resp(200, _page(PAGES[path]), "text/html; charset=utf-8",
                     headers={"Cache-Control": "no-store"})

    return _json(404, {"error": "not found", "hint": "data endpoints are served over the WebSocket relay"})


# ---- WebSocket side ----------------------------------------------------------------------

def _post(conn_id: str, obj: dict) -> bool:
    try:
        _mgmt.post_to_connection(ConnectionId=conn_id, Data=json.dumps(obj).encode())
        return True
    except _mgmt.exceptions.GoneException:
        _forget(conn_id)
        return False
    except ClientError as e:
        print(json.dumps({"event": "post_failed", "conn": conn_id, "error": str(e)[:200]}))
        return False


def _device() -> dict | None:
    return _ddb.get_item(Key={"pk": "device"}).get("Item")


def _viewer_ids() -> list[str]:
    ids = []
    kwargs = {"FilterExpression": "begins_with(pk, :p)", "ExpressionAttributeValues": {":p": "viewer#"},
              "ProjectionExpression": "pk"}
    while True:
        page = _ddb.scan(**kwargs)
        ids.extend(item["pk"].split("#", 1)[1] for item in page.get("Items", []))
        if "LastEvaluatedKey" not in page:
            return ids
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def _forget(conn_id: str) -> None:
    _ddb.delete_item(Key={"pk": f"viewer#{conn_id}"})
    dev = _device()
    if dev and dev.get("connection_id") == conn_id:
        _ddb.update_item(Key={"pk": "device"}, UpdateExpression="REMOVE connection_id SET last_seen = :t",
                         ExpressionAttributeValues={":t": int(time.time())})


def _notify_device(dev: dict | None = None) -> None:
    dev = dev or _device()
    if not dev or not dev.get("connection_id"):
        return
    ids = _viewer_ids()
    _post(dev["connection_id"], {"type": "viewers", "count": len(ids), "ids": ids})


def handle_ws(event: dict) -> dict:
    ctx = event["requestContext"]
    conn_id = ctx["connectionId"]
    etype = ctx["eventType"]
    now = int(time.time())

    if etype == "CONNECT":
        q = event.get("queryStringParameters") or {}
        role = q.get("role")
        if role == "device":
            if not hmac.compare_digest(q.get("secret", ""), param("device_secret")):
                return {"statusCode": 401}
            _ddb.update_item(Key={"pk": "device"},
                             UpdateExpression="SET connection_id = :c, connected_at = :t, last_seen = :t, #ttl = :ttl",
                             ExpressionAttributeNames={"#ttl": "ttl"},
                             ExpressionAttributeValues={":c": conn_id, ":t": now, ":ttl": now + ROW_TTL_S})
            print(json.dumps({"event": "device_connect", "conn": conn_id}))
            return {"statusCode": 200}
        if role == "viewer":
            origin = (event.get("headers") or {}).get("Origin") or (event.get("headers") or {}).get("origin")
            if HTTP_ORIGIN and origin and origin.rstrip("/") != HTTP_ORIGIN:
                return {"statusCode": 403}
            if verify_token(q.get("t", ""), param("token_secret"), "ws") is None:
                return {"statusCode": 401}
            _ddb.put_item(Item={"pk": f"viewer#{conn_id}", "connected_at": now, "ttl": now + ROW_TTL_S})
            # Do not notify the device here: the socket is not usable until $connect returns.
            # The viewer's first "hello" frame triggers the notification instead.
            return {"statusCode": 200}
        return {"statusCode": 400}

    if etype == "DISCONNECT":
        was_viewer = bool(_ddb.get_item(Key={"pk": f"viewer#{conn_id}"}).get("Item"))
        _forget(conn_id)
        if was_viewer:
            _notify_device()
        else:
            print(json.dumps({"event": "device_disconnect", "conn": conn_id}))
        return {"statusCode": 200}

    # MESSAGE
    try:
        msg = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return {"statusCode": 400}
    action = msg.get("action")
    dev = _device()
    is_device = bool(dev and dev.get("connection_id") == conn_id)
    is_viewer = (not is_device) and bool(_ddb.get_item(Key={"pk": f"viewer#{conn_id}"}).get("Item"))
    if not (is_device or is_viewer):
        return {"statusCode": 403}

    if action == "ping":
        _post(conn_id, {"type": "pong", "t": now})
        if is_device:
            _ddb.update_item(Key={"pk": "device"}, UpdateExpression="SET last_seen = :t, #ttl = :ttl",
                             ExpressionAttributeNames={"#ttl": "ttl"},
                             ExpressionAttributeValues={":t": now, ":ttl": now + ROW_TTL_S})
        else:
            _ddb.update_item(Key={"pk": f"viewer#{conn_id}"}, UpdateExpression="SET #ttl = :ttl",
                             ExpressionAttributeNames={"#ttl": "ttl"}, ExpressionAttributeValues={":ttl": now + ROW_TTL_S})
        return {"statusCode": 200}

    if is_viewer:
        if action == "hello":
            online = bool(dev and dev.get("connection_id"))
            snap = dev.get("snapshot") if dev else None
            _post(conn_id, {"type": "hello", "device_online": online,
                            "last_seen": int(dev.get("last_seen", 0)) if dev else None,
                            "snapshot": json.loads(snap) if snap else None,
                            "viewer_count": len(_viewer_ids()), "version": APP_VERSION})
            _notify_device(dev)
            return {"statusCode": 200}
        if action == "rpc":
            if not (dev and dev.get("connection_id")):
                _post(conn_id, {"type": "rpc", "id": msg.get("id"), "status": 503, "parts": 1, "part": 0,
                                "enc": "identity", "ctype": "application/json",
                                "data": json.dumps({"error": "pi_offline", "message": "Raspberry Pi is not connected"})})
                return {"statusCode": 200}
            fwd = {"type": "rpc", "from": conn_id, "id": msg.get("id"), "method": msg.get("method", "GET"),
                   "path": msg.get("path", "/"), "query": msg.get("query", ""), "body": msg.get("body"),
                   "ctype": msg.get("ctype"), "accept_enc": msg.get("accept_enc", "identity")}
            if not _post(dev["connection_id"], fwd):
                _post(conn_id, {"type": "rpc", "id": msg.get("id"), "status": 503, "parts": 1, "part": 0,
                                "enc": "identity", "ctype": "application/json",
                                "data": json.dumps({"error": "pi_offline", "message": "Raspberry Pi dropped"})})
            return {"statusCode": 200}
        return {"statusCode": 400}

    # device-originated frames
    if action == "snapshot":
        snap = json.dumps(msg.get("data") or {})[:64_000]
        # `snapshot` is a DynamoDB reserved word; it must go through an attribute-name alias.
        _ddb.update_item(Key={"pk": "device"},
                         UpdateExpression="SET #snap = :s, snapshot_at = :t, last_seen = :t",
                         ExpressionAttributeNames={"#snap": "snapshot"},
                         ExpressionAttributeValues={":s": snap, ":t": now})
        return {"statusCode": 200}
    if action == "gone":
        for vid in msg.get("ids") or []:
            _ddb.delete_item(Key={"pk": f"viewer#{vid}"})
        return {"statusCode": 200}
    if action == "viewers?":
        _notify_device(dev)
        return {"statusCode": 200}
    if action == "rpc_reply":          # fallback path if the Pi cannot post directly
        _post(msg.get("to", ""), {k: v for k, v in msg.items() if k not in ("action", "to")} | {"type": "rpc"})
        return {"statusCode": 200}
    if action == "push":               # fallback fan-out if the Pi cannot post directly
        for vid in _viewer_ids():
            _post(vid, {"type": msg.get("event", "inverter_update"), "data": msg.get("data")})
        return {"statusCode": 200}
    return {"statusCode": 400}


def lambda_handler(event, context):
    ctx = event.get("requestContext", {})
    if "connectionId" in ctx:
        return handle_ws(event)
    return handle_http(event)
