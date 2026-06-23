from __future__ import annotations

import logging
from contextvars import ContextVar, Token
from dataclasses import dataclass

_capture_var: ContextVar[list[dict[str, str]] | None] = ContextVar('log_capture', default=None)


class _CaptureHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        buf = _capture_var.get()
        if buf is None:
            return
        level = record.levelname.lower()
        if level == 'warning':
            level = 'warn'
        buf.append({'level': level, 'message': record.getMessage()})


_installed = False


def _ensure_installed() -> None:
    global _installed
    if _installed:
        return
    logging.getLogger('phoenixadult').addHandler(_CaptureHandler())
    _installed = True


@dataclass
class Capture:
    logs: list[dict[str, str]]
    _token: Token[list[dict[str, str]] | None]

    def end(self) -> list[dict[str, str]]:
        _capture_var.reset(self._token)
        return self.logs


def begin_capture() -> Capture:
    _ensure_installed()
    buf: list[dict[str, str]] = []
    token = _capture_var.set(buf)
    return Capture(logs=buf, _token=token)
