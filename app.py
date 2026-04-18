from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import threading
import time
import logging
import power_stats
from continuous_reader import ContinuousReader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

background_thread = None
thread_lock = threading.Lock()

stats_manager = power_stats.get_instance()
continuous_reader = ContinuousReader(stats_manager)


def _build_stats_payload():
    all_stats = stats_manager.get_all_stats()
    reading_stats = stats_manager.get_reading_statistics()
    reader_stats = continuous_reader.get_statistics()
    reading_stats.update(reader_stats)
    all_stats['reading_stats'] = reading_stats
    all_stats['summary'] = stats_manager.get_summary()
    latest = continuous_reader.get_latest_data()
    all_stats['system'] = latest.get('system') if latest else None
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


@app.route('/')
def dashboard():
    return render_template('solar_flow.html')


@app.route('/classic')
def classic_dashboard():
    return render_template('dashboard.html')


@app.route('/stats')
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
def get_summary():
    return jsonify(stats_manager.get_summary(request.args.get('date')))


@app.route('/status')
def get_status():
    """Snapshot of the most recent reading (mirror of the WebSocket frame)."""
    latest = continuous_reader.get_latest_data()
    if not latest:
        return jsonify({'success': False, 'error': 'No reading available yet'}), 503
    return jsonify(latest)


@app.route('/warnings')
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
def get_history():
    try:
        days = int(request.args.get('days', 30))
    except (TypeError, ValueError):
        days = 30
    days = max(1, min(days, 365))
    return jsonify(stats_manager.get_history(days))


@app.route('/recent-readings')
def get_recent_readings():
    try:
        minutes = int(request.args.get('minutes', 30))
    except (TypeError, ValueError):
        minutes = 30
    minutes = max(1, min(minutes, 720))
    return jsonify(stats_manager.get_recent_readings(minutes))


@app.route('/raw-data')
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


@app.route('/export-data')
def export_data():
    try:
        import csv
        import io
        from flask import Response

        data, _ = stats_manager.get_raw_readings(1, 10000)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Timestamp', 'Solar Power (W)', 'Grid Power (W)', 'Battery (%)',
                         'Battery Power (W)', 'Load Power (W)', 'Duration (ms)'])
        for row in data:
            writer.writerow([
                row['timestamp_formatted'],
                row['solar_power'],
                row.get('grid_power', 0),
                row['battery_percentage'],
                row.get('battery_power', 0),
                row['load_power'],
                row['duration_ms'],
            ])
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=inverter_data.csv'},
        )
    except Exception as e:
        logger.error(f"Error exporting data: {e}")
        return jsonify({'error': str(e)}), 500


@socketio.on('connect')
def handle_connect():
    global background_thread
    with thread_lock:
        if background_thread is None:
            background_thread = threading.Thread(target=background_data_update)
            background_thread.daemon = True
            background_thread.start()
    logger.info("Client connected")
    status = continuous_reader.get_latest_data()
    if status:
        emit('inverter_update', status)
    emit('stats_update', _build_stats_payload())


@socketio.on('disconnect')
def handle_disconnect():
    logger.info("Client disconnected")


@socketio.on('request_update')
def handle_request_update():
    status = continuous_reader.get_latest_data()
    if status:
        emit('inverter_update', status)
    emit('stats_update', _build_stats_payload())


@socketio.on('request_stats')
def handle_request_stats():
    emit('stats_update', _build_stats_payload())


if __name__ == '__main__':
    try:
        continuous_reader.start()
        socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
    finally:
        continuous_reader.stop()
        stats_manager.cleanup()
