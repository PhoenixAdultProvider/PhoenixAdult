from __future__ import annotations

import logging
import threading
from collections import deque

LINE_CHOICES = (50, 100, 200, 500, 1000)
DEFAULT_LINES = 200
CAPACITY = max(LINE_CHOICES)


class SessionLogHandler(logging.Handler):
    def __init__(self, capacity: int = CAPACITY) -> None:
        super().__init__()
        self._lines: deque[tuple[int, str]] = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._seq = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            text = self.format(record)
        except Exception:  # noqa: BLE001 - a broken format string must never break logging
            self.handleError(record)
            return
        with self._lock:
            for line in text.splitlines() or ['']:
                self._seq += 1
                self._lines.append((self._seq, line))

    def tail(self, since: int = 0, limit: int = DEFAULT_LINES) -> tuple[int, list[str], bool]:
        limit = max(1, min(limit, CAPACITY))
        with self._lock:
            if not self._lines:
                return self._seq, [], True
            oldest = self._lines[0][0]
            if since <= 0 or since < oldest - 1:
                return self._seq, [line for _seq, line in self._lines][-limit:], True
            return self._seq, [line for seq, line in self._lines if seq > since][-limit:], False


session_log = SessionLogHandler()
