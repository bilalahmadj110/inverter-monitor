"""Direct PI30 HID reader — replaces the mpp-solar CLI subprocess.

Bypasses mpp-solar's hidrawio driver (which has ~2.5s of hardcoded time.sleep per
transaction). Uses non-blocking os.read + select.select with a 10ms poll budget,
so wall-clock is bounded by actual wire time, not library sleeps.

Wire protocol: `<CMD><CRC_HI><CRC_LO>\r` written as 8-byte HID reports;
response `(<payload><CRC_HI><CRC_LO>\r` read in 8-byte chunks.
"""
import errno
import logging
import os
import select
import threading
import time

logger = logging.getLogger(__name__)

# Bytes that must be bumped +1 to avoid collision with framing chars.
_CRC_ESCAPE = {0x28, 0x0D, 0x0A}


def crc16_xmodem(data: bytes) -> bytes:
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    hi, lo = (crc >> 8) & 0xFF, crc & 0xFF
    if hi in _CRC_ESCAPE:
        hi = (hi + 1) & 0xFF
    if lo in _CRC_ESCAPE:
        lo = (lo + 1) & 0xFF
    return bytes([hi, lo])


class PI30Error(RuntimeError):
    pass


class PI30Reader:
    def __init__(self, device_path='/dev/hidraw0', read_timeout=1.5, poll_interval=0.01):
        self.device_path = device_path
        self.read_timeout = read_timeout
        self.poll_interval = poll_interval
        self._lock = threading.Lock()

    def query(self, command: str, retries: int = 3) -> bytes:
        """Send `command` (e.g. 'QPIGS') and return the payload bytes
        (framing stripped, CRC stripped). Raises PI30Error on total failure."""
        cmd_bytes = command.encode('ascii')
        frame = cmd_bytes + crc16_xmodem(cmd_bytes) + b'\r'
        last_err = None
        for attempt in range(retries):
            try:
                with self._lock:
                    return self._transact(frame)
            except (OSError, PI30Error) as e:
                last_err = e
                logger.debug(f"{command} attempt {attempt + 1}/{retries} failed: {e}")
        raise PI30Error(f"{command} failed after {retries} attempts: {last_err}")

    def _transact(self, frame: bytes) -> bytes:
        fd = os.open(self.device_path, os.O_RDWR | os.O_NONBLOCK)
        try:
            self._drain(fd)
            self._write(fd, frame)
            raw = self._read_until_cr(fd)
            return self._unwrap(raw)
        finally:
            os.close(fd)

    def _drain(self, fd):
        """Discard any stale data left in the device buffer from a previous read."""
        while True:
            r, _, _ = select.select([fd], [], [], 0)
            if fd not in r:
                return
            try:
                if not os.read(fd, 256):
                    return
            except OSError as e:
                if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    return
                raise

    def _write(self, fd, frame: bytes):
        pos = 0
        while pos < len(frame):
            chunk = frame[pos:pos + 8]
            if len(chunk) < 8:
                chunk = chunk + b'\x00' * (8 - len(chunk))
            os.write(fd, chunk)
            pos += 8

    def _read_until_cr(self, fd) -> bytes:
        buf = bytearray()
        deadline = time.monotonic() + self.read_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PI30Error(f"read timeout ({self.read_timeout}s); got {bytes(buf)[:80]!r}")
            r, _, _ = select.select([fd], [], [], min(self.poll_interval, remaining))
            if fd not in r:
                continue
            try:
                data = os.read(fd, 256)
            except OSError as e:
                if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    continue
                raise
            if not data:
                continue
            buf.extend(data)
            cr = buf.find(b'\r')
            if cr != -1:
                return bytes(buf[:cr + 1])

    def _unwrap(self, raw: bytes) -> bytes:
        if len(raw) < 5 or raw[0:1] != b'(' or raw[-1:] != b'\r':
            raise PI30Error(f"malformed response: {raw[:80]!r}")
        payload = raw[1:-3]
        if payload.startswith(b'NAK'):
            raise PI30Error("inverter replied NAK")
        return payload


_default_reader = None
_default_lock = threading.Lock()


def get_default_reader(device_path='/dev/hidraw0') -> PI30Reader:
    global _default_reader
    with _default_lock:
        if _default_reader is None or _default_reader.device_path != device_path:
            _default_reader = PI30Reader(device_path=device_path)
        return _default_reader
