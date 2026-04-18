import threading
import time
import logging
from inverter_status import get_inverter_status, get_device_mode, get_warning_status

logger = logging.getLogger(__name__)

CYCLE_SECONDS = 3.0
EXTRAS_INTERVAL_SECONDS = 30.0


class ContinuousReader:
    """
    Continuously reads the inverter (QPIGS every cycle) and records to database.
    Runs QMOD + QPIWS on a slower cadence in a side thread so the fast loop
    isn't blocked by extra serial commands. Latest mode/warnings are merged
    into every QPIGS reading before it's cached + recorded.
    """
    def __init__(self, stats_manager):
        self.stats_manager = stats_manager
        self.running = False
        self.reader_thread = None
        self.extras_thread = None
        self.latest_data = None
        self.data_lock = threading.Lock()

        self._mode = None
        self._warnings = []
        self._extras_lock = threading.Lock()
        self._last_extras_time = 0.0

        self.total_readings = 0
        self.error_count = 0
        self.last_reading_time = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self.reader_thread.start()
        self.extras_thread = threading.Thread(target=self._extras_loop, daemon=True)
        self.extras_thread.start()
        logger.info("Continuous reader started (QPIGS every %.1fs, extras every %.0fs)",
                    CYCLE_SECONDS, EXTRAS_INTERVAL_SECONDS)

    def stop(self):
        self.running = False
        for t in (self.reader_thread, self.extras_thread):
            if t and t.is_alive():
                t.join(timeout=5)
        logger.info("Continuous reader stopped")

    def get_latest_data(self):
        with self.data_lock:
            return self.latest_data

    def _get_extras(self):
        with self._extras_lock:
            return self._mode, list(self._warnings)

    def _set_extras(self, mode, warnings):
        with self._extras_lock:
            self._mode = mode
            self._warnings = warnings
            self._last_extras_time = time.time()

    def _extras_loop(self):
        """Slow poll for QMOD + QPIWS. Non-fatal on failure."""
        logger.info("Extras poller started")
        while self.running:
            try:
                mode = get_device_mode()
                warnings = get_warning_status()
                self._set_extras(mode, warnings)
                if mode:
                    logger.debug(f"Extras: mode={mode}, warnings={len(warnings)}")
            except Exception as e:
                logger.warning(f"Extras poll failed: {e}")
            for _ in range(int(EXTRAS_INTERVAL_SECONDS)):
                if not self.running:
                    return
                time.sleep(1)

    def _read_loop(self):
        logger.info("Starting continuous reading loop")
        while self.running:
            cycle_start = time.monotonic()
            try:
                mode, warnings = self._get_extras()
                status = get_inverter_status(mode=mode, warnings=warnings)
                self.total_readings += 1
                self.last_reading_time = time.time()

                with self.data_lock:
                    self.latest_data = status

                if status['success'] and 'timing' in status:
                    self.stats_manager.record_reading(
                        status['metrics'],
                        status['timing']['start_time'],
                        status['timing']['end_time'],
                    )
                    if self.total_readings % 20 == 0:
                        d_ms = status['timing']['duration_ms']
                        logger.info(f"Reading #{self.total_readings}: {d_ms:.1f}ms - "
                                    f"Solar: {status['metrics']['solar']['power']}W, "
                                    f"Grid: {status['metrics']['grid']['power']}W, "
                                    f"Load: {status['metrics']['load']['power']}W")
                else:
                    self.error_count += 1
                    logger.warning(f"Failed reading #{self.total_readings}: "
                                   f"{status.get('error', 'Unknown error')}")

                if self.total_readings % 100 == 0:
                    err_rate = (self.error_count / self.total_readings) * 100
                    logger.info(f"Reader @ #{self.total_readings}: error rate {err_rate:.1f}%")

            except Exception as e:
                self.error_count += 1
                logger.error(f"Error in reading loop: {e}")
                time.sleep(1)

            elapsed = time.monotonic() - cycle_start
            sleep_for = CYCLE_SECONDS - elapsed
            if sleep_for < 0.1:
                sleep_for = 0.1
            end_at = time.monotonic() + sleep_for
            while self.running and time.monotonic() < end_at:
                time.sleep(min(0.5, end_at - time.monotonic()))

    def get_statistics(self):
        error_rate = (self.error_count / max(1, self.total_readings))
        mode, warnings = self._get_extras()
        return {
            'total_readings': self.total_readings,
            'error_count': self.error_count,
            'error_rate': error_rate,
            'running': self.running,
            'last_reading_time': self.last_reading_time,
            'extras_last_poll': self._last_extras_time,
            'extras_mode': mode,
            'extras_warning_count': len(warnings),
        }
