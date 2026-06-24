from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from app.config import config
from app.config.env import env
from app.utils.logging.context import LOG_FORMAT, current_request_id

# Stamp the current per-request id onto every log record so the formatter can show it.
_old_factory = logging.getLogRecordFactory()


def _record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
    record = _old_factory(*args, **kwargs)
    record.request_id = current_request_id()
    return record


logging.setLogRecordFactory(_record_factory)

# Map the legacy winston levels onto stdlib logging.
_LEVEL_MAP = {
    'error': logging.ERROR,
    'warn': logging.WARNING,
    'info': logging.INFO,
    'http': logging.INFO,
    'verbose': logging.DEBUG,
    'debug': logging.DEBUG,
    'silly': logging.DEBUG,
}

_LOG_DIR = Path(env.log_dir)
_LOG_FILE = _LOG_DIR / 'agent.log'
try:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass

_base = logging.getLogger('phoenixadult')
_base.setLevel(_LEVEL_MAP.get(config.log_level, logging.INFO))
_base.propagate = False

if not _base.handlers:
    from app.utils.logging.redaction import RedactionFilter

    _base.addFilter(RedactionFilter())
    _fmt = logging.Formatter(LOG_FORMAT)
    _console = logging.StreamHandler()
    _console.setFormatter(_fmt)
    _base.addHandler(_console)
    try:
        _file = RotatingFileHandler(_LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8')
        _file.setFormatter(_fmt)
        _base.addHandler(_file)
    except OSError:
        pass


class _Logger:
    """Thin shim exposing winston-style level methods with tagged-form support."""

    def _emit(self, level: int, a: Any, b: Any = None, **meta: Any) -> None:
        if isinstance(a, str) and isinstance(b, str):
            message = f'[{a}] {b}'
        elif b is None:
            message = str(a)
        else:
            message = str(a)
            if isinstance(b, dict):
                meta = {**b, **meta}
        if meta:
            message = f'{message} {json.dumps(meta, default=str)}'
        # stacklevel=3 skips _emit + the level method so module/lineno resolve to the real caller.
        _base.log(level, message, stacklevel=3)

    def error(self, a: Any, b: Any = None, **meta: Any) -> None:
        self._emit(logging.ERROR, a, b, **meta)

    def warn(self, a: Any, b: Any = None, **meta: Any) -> None:
        self._emit(logging.WARNING, a, b, **meta)

    def info(self, a: Any, b: Any = None, **meta: Any) -> None:
        self._emit(logging.INFO, a, b, **meta)

    def http(self, a: Any, b: Any = None, **meta: Any) -> None:
        self._emit(logging.INFO, a, b, **meta)

    def verbose(self, a: Any, b: Any = None, **meta: Any) -> None:
        self._emit(logging.DEBUG, a, b, **meta)

    def debug(self, a: Any, b: Any = None, **meta: Any) -> None:
        self._emit(logging.DEBUG, a, b, **meta)


logger = _Logger()
logger.info(f'Logging to console (LOG_LEVEL={config.log_level}) and {_LOG_FILE}')
