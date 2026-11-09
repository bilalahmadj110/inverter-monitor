"""HTTP client for the Flask dashboard, for processes that must never open the inverter's HID
device themselves (the MCP server; anything else that wants readings or wants to change a
setting). PI30 is half-duplex over one /dev/hidraw0 and the Flask app is its only owner.

The dashboard has exactly one way in, the browser login form, so this client logs in like a
browser: it fetches the form, posts the credentials with the CSRF field, keeps the session
cookie by hand (the cookie is flagged Secure, which cookie jars refuse to send over plain http
to a LAN address) and sends the X-CSRFToken header Flask-WTF expects on every POST / DELETE.
Standard library only, so it runs from any Python without the app's dependencies installed.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

CSRF_REFRESH_S = 1800        # Flask-WTF tokens last 3600 s; renew well inside that
LOGIN_MIN_INTERVAL_S = 15    # the app allows 5 logins per minute per IP

_STATUS_TEXT = {
    400: 'bad request',
    401: 'unauthorized',
    403: 'forbidden',
    404: 'not found',
    429: 'rate limited by the dashboard; try again in a minute',
    500: 'dashboard error',
    503: 'dashboard has no inverter reading yet',
}


class AppError(Exception):
    """A non-2xx reply from the dashboard. `status` is the HTTP code; `message` is the app's own
    error text when the body was JSON with an `error` key, else a short description."""

    def __init__(self, status: int, message: str, body=None):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.message = message
        self.body = body


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class InverterAppClient:
    """Synchronous, thread-safe client. One instance per process; requests are serialized by a
    lock, which is fine because the app serializes inverter access anyway."""

    def __init__(self, base_url: str, username: str, password: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.timeout = timeout
        self._opener = urllib.request.build_opener(_NoRedirect())
        self._cookie: str | None = None
        self._csrf: str | None = None
        self._csrf_at = 0.0
        self._last_login_attempt = 0.0
        self._lock = threading.RLock()

    # ---- low level -----------------------------------------------------------------------
    def _open(self, req, timeout=None):
        try:
            resp = self._opener.open(req, timeout=timeout or self.timeout)
            return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    @staticmethod
    def _session_cookie(headers):
        for h in headers.get_all('Set-Cookie') or []:
            if h.startswith('session='):
                return h.split(';', 1)[0]
        return None

    def _adopt_cookie(self, headers):
        """Flask refreshes permanent sessions on every response; keep the newest cookie."""
        new = self._session_cookie(headers)
        if new:
            self._cookie = new

    # ---- auth ----------------------------------------------------------------------------
    def login(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now - self._last_login_attempt < LOGIN_MIN_INTERVAL_S:
                raise AppError(429, 'a login was attempted moments ago; waiting for the dashboard login limit')
            self._last_login_attempt = now
            status, headers, body = self._open(urllib.request.Request(f"{self.base_url}/login"))
            pre_cookie = self._session_cookie(headers)
            m = re.search(rb'name="csrf_token" value="([^"]+)"', body)
            if status != 200 or not m or not pre_cookie:
                raise AppError(status, f"login page unavailable at {self.base_url}/login")
            form = urllib.parse.urlencode({
                'csrf_token': m.group(1).decode(), 'username': self.username, 'password': self.password,
            }).encode()
            req = urllib.request.Request(
                f"{self.base_url}/login", data=form, method='POST',
                headers={'Cookie': pre_cookie, 'Content-Type': 'application/x-www-form-urlencoded'})
            status, headers, _ = self._open(req)
            cookie = self._session_cookie(headers)
            if status != 302 or not cookie:
                if status == 401:
                    raise AppError(401, 'login rejected: check the dashboard username / password')
                raise AppError(status, f"login failed (status {status})")
            self._cookie = cookie
            self._refresh_csrf_locked()
            logger.info("logged in to %s as %s", self.base_url, self.username)

    def _refresh_csrf_locked(self) -> bool:
        """The dashboard page carries the CSRF token in a meta tag and, because rendering it
        stores the CSRF secret in the session, a refreshed cookie. Token and cookie belong together."""
        status, headers, body = self._open(
            urllib.request.Request(f"{self.base_url}/", headers={'Cookie': self._cookie or ''}))
        if status != 200:
            return False
        self._adopt_cookie(headers)
        m = re.search(rb'name="csrf-token" content="([^"]+)"', body)
        if not m:
            return False
        self._csrf = m.group(1).decode()
        self._csrf_at = time.monotonic()
        return True

    # ---- requests ------------------------------------------------------------------------
    def request(self, method: str, path: str, params: dict | None = None, json_body=None,
                timeout: float | None = None, _retry: bool = True):
        """Perform one request as the logged-in user. Returns the decoded JSON body (or text for
        non-JSON replies). Raises AppError for any non-2xx status."""
        method = method.upper()
        with self._lock:
            if self._cookie is None:
                self.login()
            url = f"{self.base_url}{path}"
            if params:
                query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
                if query:
                    url += ('&' if '?' in url else '?') + query
            headers = {'Cookie': self._cookie or '', 'Accept': 'application/json'}
            data = None
            if method not in ('GET', 'HEAD'):
                if not self._csrf or time.monotonic() - self._csrf_at > CSRF_REFRESH_S:
                    self._refresh_csrf_locked()
                headers['X-CSRFToken'] = self._csrf or ''
                headers['Content-Type'] = 'application/json'
                data = json.dumps(json_body if json_body is not None else {}).encode()
            status, resp_headers, payload = self._open(
                urllib.request.Request(url, data=data, method=method, headers=headers), timeout)
            self._adopt_cookie(resp_headers)
            if status in (401, 302) and _retry:
                # Session expired (or the app restarted with a new secret): log in again, once.
                self._cookie = None
                self.login()
                return self.request(method, path, params, json_body, timeout, _retry=False)
            if status == 400 and _retry and method not in ('GET', 'HEAD') and b'CSRF' in payload:
                if self._refresh_csrf_locked():
                    return self.request(method, path, params, json_body, timeout, _retry=False)
        return self._decode(status, resp_headers, payload)

    @staticmethod
    def _decode(status, headers, payload: bytes):
        body = None
        if 'json' in (headers.get('Content-Type') or '') or payload[:1] in (b'{', b'['):
            try:
                body = json.loads(payload)
            except ValueError:
                body = None
        if 200 <= status < 300:
            return body if body is not None else payload.decode('utf-8', 'replace')
        message = None
        if isinstance(body, dict):
            message = body.get('error') or body.get('message')
        if not message:
            message = _STATUS_TEXT.get(status) or (payload.decode('utf-8', 'replace').strip()[:200] or 'request failed')
        raise AppError(status, str(message), body)

    def get(self, path: str, **params):
        return self.request('GET', path, params=params or None)

    def post(self, path: str, json_body=None, **params):
        return self.request('POST', path, params=params or None, json_body=json_body)
