from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit, disconnect
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import threading
import time
import os
import subprocess
import logging
import power_stats
from continuous_reader import ContinuousReader
from inverter_status import (
    set_output_priority, set_charger_priority,
    OUTPUT_PRIORITY_COMMANDS, CHARGER_PRIORITY_COMMANDS,
)
from auth import init_auth, login_required, is_logged_in, audit


def _resolve_version():
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        sha = subprocess.check_output(
            ['git', '-C', here, 'rev-parse', '--short', 'HEAD'],
            stderr=subprocess.DEVNULL, text=True, timeout=2,
        ).strip()
        return sha or 'dev'
    except Exception:
        return 'dev'


APP_VERSION = _resolve_version()

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Auth bootstraps SECRET_KEY, session cookie config, and the /login + /logout routes.
# Refuses to start if INVERTER_ADMIN_PASSWORD or INVERTER_SECRET_KEY isn't set.
init_auth(app)

# CSRF on all state-changing routes.
csrf = CSRFProtect(app)

# Per-IP rate limiting. Lenient defaults for reads, strict overrides on auth and writes.
def _client_key():
    cf = request.headers.get('CF-Connecting-IP')
    if cf:
        return cf
    return get_remote_address()

limiter = Limiter(app=app, key_func=_client_key, default_limits=['120 per minute', '2000 per hour'])

# Restrict CORS to the same origin (no third-party WebSocket clients).
ALLOWED_ORIGINS = os.environ.get('ALLOWED_ORIGINS', '').strip()
allowed = [o.strip() for o in ALLOWED_ORIGINS.split(',') if o.strip()] if ALLOWED_ORIGINS else None
socketio = SocketIO(
    app,
    cors_allowed_origins=allowed if allowed else [],  # empty list = same-origin only
    async_mode='threading',
    manage_session=False,  # use Flask's secure cookie session
)

background_thread = None
thread_lock = threading.Lock()

stats_manager = power_stats.get_instance()
continuous_reader = ContinuousReader(stats_manager)


@app.context_processor
def _inject_template_globals():
    return {'app_version': APP_VERSION, 'csrf_token': generate_csrf}


@app.after_request
def _security_headers(resp):
    # CSP: allow our specific CDNs (tailwind, font-awesome, chart.js, socket.io). Inline scripts
    # are needed for the page-level <script> blocks; we use a nonce-free policy because there's
    # only one origin and no user-generated HTML in scope.
    resp.headers.setdefault(
        'Content-Security-Policy',
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "img-src 'self' data:; "
        "font-src 'self' https://cdnjs.cloudflare.com data:; "
        "connect-src 'self' ws: wss:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    resp.headers.setdefault('X-Frame-Options', 'DENY')
    resp.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    resp.headers.setdefault('Permissions-Policy', 'geolocation=(), microphone=(), camera=()')
    if request.is_secure or request.headers.get('X-Forwarded-Proto') == 'https':
        resp.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
    return resp


def _build_stats_payload():
    all_stats = stats_manager.get_all_stats()
    reading_stats = stats_manager.get_reading_statistics()
    reader_stats = continuous_reader.get_statistics()
    reading_stats.update(reader_stats)
    all_stats['reading_stats'] = reading_stats
    all_stats['summary'] = stats_manager.get_summary()
    latest = continuous_reader.get_latest_data()
    all_stats['system'] = latest.get('system') if latest else None
    all_stats['config'] = continuous_reader.get_config()
    return all_stats


def background_data_update():
    logger.info("Starting background WebSocket update thread")
    stats_update_counter = 0
    while True:
        try:
            if not continuous_reader.running:
                continuous_reader.start()
            status = continuous_reader.get_latest_data()
            if status:
                socketio.emit('inverter_update', status)
                stats_update_counter += 1
                if stats_update_counter >= 20:
                    socketio.emit('stats_update', _build_stats_payload())
                    stats_update_counter = 0
        except Exception as e:
            logger.error(f"Error in background update: {e}")
        time.sleep(3)


# Stricter limit for the login route — protects against credential stuffing.
limiter.limit('5 per minute; 30 per hour')(app.view_functions['auth.login'])


@app.route('/healthz')
@limiter.exempt
def healthz():
    return jsonify({'ok': True, 'version': APP_VERSION})


@app.route('/')
@login_required
def dashboard():
    return render_template('solar_flow.html')


@app.route('/classic')
@login_required
def classic_dashboard():
    return render_template('dashboard.html')


@app.route('/reports')
@login_required
def reports():
    return render_template('history.html')


# ---- Read-only JSON endpoints (login required, generous rate limit) -----------------------

@app.route('/stats')
@login_required
def get_stats():
    period = request.args.get('period', 'all')
    if period == 'day':
        return jsonify(stats_manager.get_daily_stats(request.args.get('day')))
    if period == 'month':
        return jsonify(stats_manager.get_monthly_stats(request.args.get('month')))
    if period == 'year':
        return jsonify(stats_manager.get_yearly_stats(request.args.get('year')))
    return jsonify(stats_manager.get_all_stats())


@app.route('/summary')
@login_required
def get_summary():
    return jsonify(stats_manager.get_summary(request.args.get('date')))


@app.route('/status')
@login_required
def get_status():
    latest = continuous_reader.get_latest_data()
    if not latest:
        return jsonify({'success': False, 'error': 'No reading available yet'}), 503
    return jsonify(latest)


@app.route('/warnings')
@login_required
def get_warnings():
    latest = continuous_reader.get_latest_data()
    system = latest.get('system') if latest else {}
    return jsonify({
        'warnings': (system or {}).get('warnings', []),
        'has_fault': (system or {}).get('has_fault', False),
        'mode': (system or {}).get('mode'),
        'mode_label': (system or {}).get('mode_label'),
    })


@app.route('/history')
@login_required
def get_history():
    try:
        days = int(request.args.get('days', 30))
    except (TypeError, ValueError):
        days = 30
    days = max(1, min(days, 365))
    return jsonify(stats_manager.get_history(days))


@app.route('/recent-readings')
@login_required
def get_recent_readings():
    try:
        minutes = int(request.args.get('minutes', 30))
    except (TypeError, ValueError):
        minutes = 30
    minutes = max(1, min(minutes, 720))
    bucket_arg = request.args.get('bucket')
    try:
        bucket_seconds = int(bucket_arg) if bucket_arg else None
    except (TypeError, ValueError):
        bucket_seconds = None
    return jsonify(stats_manager.get_recent_readings(minutes, bucket_seconds))


@app.route('/day-readings')
@login_required
def get_day_readings():
    date = request.args.get('date') or None
    try:
        bucket = int(request.args.get('bucket', 60))
    except (TypeError, ValueError):
        bucket = 60
    bucket = max(10, min(bucket, 600))
    return jsonify(stats_manager.get_day_readings(date, bucket))


@app.route('/outages')
@login_required
def get_outages():
    from_date = request.args.get('from')
    to_date = request.args.get('to')
    return jsonify(stats_manager.get_outages(from_date, to_date))


@app.route('/raw-data')
@login_required
def get_raw_data():
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 25))
    try:
        data, total_count = stats_manager.get_raw_readings(page, page_size)
        return jsonify({
            'data': data,
            'total_count': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size,
        })
    except Exception as e:
        logger.error(f"Error fetching raw data: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/export-readings')
@login_required
@limiter.limit('20 per minute')
def export_readings():
    """Export raw or bucketed readings between two dates as CSV or JSON.
    Query params: from=YYYY-MM-DD, to=YYYY-MM-DD, format=csv|json, bucket=seconds (optional)."""
    from_date = request.args.get('from')
    to_date = request.args.get('to') or from_date
    fmt = (request.args.get('format') or 'csv').lower()
    bucket_arg = request.args.get('bucket')
    try:
        bucket = int(bucket_arg) if bucket_arg else None
    except (TypeError, ValueError):
        bucket = None
    data = stats_manager.get_readings_range(from_date, to_date, bucket)
    label = f"{data.get('from', 'unknown')}_to_{data.get('to', 'unknown')}"
    if fmt == 'json':
        from flask import Response
        import json as _json
        return Response(
            _json.dumps(data, indent=2),
            mimetype='application/json',
            headers={'Content-Disposition': f'attachment; filename=inverter_{label}.json'},
        )
    # CSV
    import csv
    import io
    from flask import Response
    output = io.StringIO()
    writer = csv.writer(output)
    rows = data.get('rows', [])
    if rows:
        cols = list(rows[0].keys())
        writer.writerow(['timestamp_iso'] + cols)
        from datetime import datetime as _dt
        for r in rows:
            iso = _dt.fromtimestamp(r['timestamp']).isoformat() if r.get('timestamp') else ''
            writer.writerow([iso] + [r.get(c, '') for c in cols])
    else:
        writer.writerow(['timestamp_iso', 'note'])
        writer.writerow(['', 'no readings in range'])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=inverter_{label}.csv'},
    )


@app.route('/config')
@login_required
def get_config():
    return jsonify({
        'config': continuous_reader.get_config(),
        'output_priority_options': [{'key': k, 'label': v[1]} for k, v in OUTPUT_PRIORITY_COMMANDS.items()],
        'charger_priority_options': [{'key': k, 'label': v[1]} for k, v in CHARGER_PRIORITY_COMMANDS.items()],
    })


# ---- Write endpoints (login required, CSRF, strict rate limit, audit log) ----------------

@app.route('/refresh-extras', methods=['POST'])
@login_required
@limiter.limit('20 per minute')
def refresh_extras():
    return jsonify(continuous_reader.refresh_extras())


@app.route('/recompute-daily', methods=['POST'])
@login_required
@limiter.limit('5 per minute')
def recompute_daily():
    day = request.args.get('day')
    audit('recompute_daily', day=day)
    return jsonify(stats_manager.recompute_daily_stats(day))


def _apply_config_change(setter, label_key):
    body = request.get_json(silent=True) or {}
    mode = (body.get('mode') or request.args.get('mode') or '').upper()
    try:
        before = continuous_reader.get_config().get(label_key)
        result = setter(mode)
        audit('set_' + label_key, before=before, after=mode, command=result['command'])
        time.sleep(1.5)
        fresh = continuous_reader.refresh_config()
        return jsonify({'success': True, 'previous': before, 'applied': result, 'config': fresh})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error(f"{label_key} change failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/set-output-priority', methods=['POST'])
@login_required
@limiter.limit('10 per minute')
def set_output_priority_route():
    return _apply_config_change(set_output_priority, 'output_priority')


@app.route('/set-charger-priority', methods=['POST'])
@login_required
@limiter.limit('10 per minute')
def set_charger_priority_route():
    return _apply_config_change(set_charger_priority, 'charger_priority')


# ---- WebSocket: reject unauthenticated connections ----------------------------------------

@socketio.on('connect')
def handle_connect():
    if not is_logged_in():
        logger.warning("WS connect rejected: unauthenticated")
        return False  # disconnect
    global background_thread
    with thread_lock:
        if background_thread is None:
            background_thread = threading.Thread(target=background_data_update)
            background_thread.daemon = True
            background_thread.start()
    logger.info(f"WS connect: user={session.get('user')}")
    status = continuous_reader.get_latest_data()
    if status:
        emit('inverter_update', status)
    emit('stats_update', _build_stats_payload())


@socketio.on('disconnect')
def handle_disconnect():
    logger.info("WS disconnect")


@socketio.on('request_update')
def handle_request_update():
    if not is_logged_in():
        disconnect()
        return
    status = continuous_reader.get_latest_data()
    if status:
        emit('inverter_update', status)
    emit('stats_update', _build_stats_payload())


@socketio.on('request_stats')
def handle_request_stats():
    if not is_logged_in():
        disconnect()
        return
    emit('stats_update', _build_stats_payload())


if __name__ == '__main__':
    try:
        continuous_reader.start()
        bind_host = os.environ.get('BIND_HOST', '0.0.0.0')
        socketio.run(app, host=bind_host, port=5000, allow_unsafe_werkzeug=True)
    finally:
        continuous_reader.stop()
        stats_manager.cleanup()
