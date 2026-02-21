from __future__ import annotations

import logging
import threading
from collections import deque


class InMemoryLogBuffer(logging.Handler):
    def __init__(self, max_lines: int = 400) -> None:
        super().__init__()
        self._lines: deque[str] = deque(maxlen=max_lines)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        message = self.format(record)
        with self._lock:
            self._lines.append(message)

    def snapshot(self) -> list[str]:
        with self._lock:
            return list(self._lines)

    def clear(self) -> None:
        with self._lock:
            self._lines.clear()
