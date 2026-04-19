"""Single-user authentication and route protection."""
import os
import secrets
from functools import wraps
from datetime import timedelta

from flask import (
    Blueprint, request, session, redirect, url_for, render_template,
    abort, current_app, jsonify, g,
)
from werkzeug.security import generate_password_hash, check_password_hash


auth_bp = Blueprint('auth', __name__)


def _config():
    """Read auth config from env (validated at app startup)."""
    return {
        'username': os.environ.get('INVERTER_ADMIN_USERNAME', 'admin').strip(),
        'password_hash': current_app.config.get('ADMIN_PASSWORD_HASH'),
        'session_lifetime_minutes': int(os.environ.get('INVERTER_SESSION_MINUTES', '60')),
    }


def is_logged_in():
    return bool(session.get('uid'))


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not is_logged_in():
            if request.path.startswith('/api/') or request.is_json or _wants_json():
                return jsonify({'error': 'Unauthorized', 'login_url': url_for('auth.login')}), 401
            return redirect(url_for('auth.login', next=request.path))
        # Touch session to extend on activity.
        session.permanent = True
        return view(*args, **kwargs)
    return wrapper


def _wants_json():
    accept = request.headers.get('Accept', '')
    return 'application/json' in accept and 'text/html' not in accept


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    cfg = _config()
    error = None
    if request.method == 'POST':
        # Rate limiting is applied by the limiter on this route in app.py.
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        if (
            username == cfg['username']
            and cfg['password_hash']
            and check_password_hash(cfg['password_hash'], password)
        ):
            session.clear()
            session['uid'] = secrets.token_hex(16)
            session['user'] = username
            session.permanent = True
            current_app.logger.info(f"AUTH login OK user={username} ip={_client_ip()}")
            nxt = request.args.get('next') or url_for('dashboard')
            if not nxt.startswith('/'):
                nxt = url_for('dashboard')
            return redirect(nxt)
        current_app.logger.warning(f"AUTH login FAIL user={username!r} ip={_client_ip()}")
        error = 'Invalid username or password.'
    return render_template('login.html', error=error), (401 if error else 200)


@auth_bp.route('/logout', methods=['POST'])
def logout():
    user = session.get('user')
    session.clear()
    current_app.logger.info(f"AUTH logout user={user} ip={_client_ip()}")
    return redirect(url_for('auth.login'))


def _client_ip():
    # Prefer Cloudflare's connecting IP if present; fall back to remote_addr.
    return (
        request.headers.get('CF-Connecting-IP')
        or request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
        or request.remote_addr
        or 'unknown'
    )


def init_auth(app):
    """Validate that auth is configured properly. Refuses to start if a password
    isn't set — public exposure without a password would be catastrophic."""
    raw_password = os.environ.get('INVERTER_ADMIN_PASSWORD', '').strip()
    if not raw_password:
        raise RuntimeError(
            "INVERTER_ADMIN_PASSWORD env var is required. "
            "Set it on the systemd unit before starting the app."
        )
    if len(raw_password) < 8:
        raise RuntimeError("INVERTER_ADMIN_PASSWORD must be at least 8 characters.")
    app.config['ADMIN_PASSWORD_HASH'] = generate_password_hash(raw_password, method='pbkdf2:sha256:600000')

    secret_key = os.environ.get('INVERTER_SECRET_KEY', '').strip()
    if not secret_key:
        raise RuntimeError(
            "INVERTER_SECRET_KEY env var is required (used for session signing). "
            "Generate with: python -c 'import secrets; print(secrets.token_hex(32))'"
        )
    if len(secret_key) < 32:
        raise RuntimeError("INVERTER_SECRET_KEY must be at least 32 chars (use a 64-hex string).")
    app.config['SECRET_KEY'] = secret_key

    behind_proxy = os.environ.get('BEHIND_PROXY', '1') == '1'
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=behind_proxy,  # true when fronted by Cloudflare (HTTPS)
        SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=int(os.environ.get('INVERTER_SESSION_MINUTES', '60'))),
    )
    app.register_blueprint(auth_bp)


def get_current_user():
    return session.get('user')


def audit(action, **details):
    """Structured audit log for write operations."""
    payload = ' '.join(f'{k}={v!r}' for k, v in details.items())
    current_app.logger.info(f"AUDIT action={action} user={get_current_user()} ip={_client_ip()} {payload}")
