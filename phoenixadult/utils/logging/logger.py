from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from phoenixadult.config import config
from phoenixadult.config.env import env
from phoenixadult.utils.logging.context import HTTP, VERBOSE, AlignedFormatter, current_request_id

_old_factory = logging.getLogRecordFactory()


def _record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
    record = _old_factory(*args, **kwargs)
    record.request_id = current_request_id()
    return record


logging.setLogRecordFactory(_record_factory)

_LEVEL_MAP = {
    'error': logging.ERROR,
    'warn': logging.WARNING,
    'info': logging.INFO,
    'debug': logging.DEBUG,
    'http': HTTP,
    'verbose': VERBOSE,
    'silly': VERBOSE,
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
    from phoenixadult.utils.logging.redaction import RedactionFilter
    from phoenixadult.utils.logging.session_log import session_log

    _base.addFilter(RedactionFilter())
    _fmt = AlignedFormatter()
    _console = logging.StreamHandler()
    _console.setFormatter(_fmt)
    _base.addHandler(_console)
    session_log.setFormatter(_fmt)
    _base.addHandler(session_log)
    try:
        _file = RotatingFileHandler(_LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8')
        _file.setFormatter(_fmt)
        _base.addHandler(_file)
    except OSError:
        pass


class _Logger:
    def _emit(self, level: int, a: Any, b: Any = None, **meta: Any) -> None:
        if isinstance(a, str) and isinstance(b, str):
            message = f'[{a}] {b}'
        elif b is None:
            message = str(a)
        else:
            message = str(a)
            if isinstance(b, dict):
                meta = {**b, **meta}
        exc_info = meta.pop('exc_info', None)
        if meta:
            message = f'{message} {json.dumps(meta, default=str)}'
        _base.log(level, message, stacklevel=3, exc_info=exc_info)

    def error(self, a: Any, b: Any = None, **meta: Any) -> None:
        self._emit(logging.ERROR, a, b, **meta)

    def warn(self, a: Any, b: Any = None, **meta: Any) -> None:
        self._emit(logging.WARNING, a, b, **meta)

    def info(self, a: Any, b: Any = None, **meta: Any) -> None:
        self._emit(logging.INFO, a, b, **meta)

    def http(self, a: Any, b: Any = None, **meta: Any) -> None:
        self._emit(HTTP, a, b, **meta)

    def verbose(self, a: Any, b: Any = None, **meta: Any) -> None:
        self._emit(VERBOSE, a, b, **meta)

    def debug(self, a: Any, b: Any = None, **meta: Any) -> None:
        self._emit(logging.DEBUG, a, b, **meta)


logger = _Logger()
logger.info(f'Logging to console (LOG_LEVEL={config.log_level}) and {_LOG_FILE}')
