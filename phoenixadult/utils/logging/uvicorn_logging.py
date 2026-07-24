from __future__ import annotations

import logging
from typing import Any

from phoenixadult.config import config
from phoenixadult.config.env import env
from phoenixadult.utils.logging.context import AlignedFormatter
from phoenixadult.utils.logging.redaction import RedactionFilter


def uvicorn_level() -> str:
    """The stdlib level name uvicorn's own loggers run at for the configured LOG_LEVEL;
    levels below DEBUG (http, verbose, silly) map to DEBUG — uvicorn has nothing quieter."""
    return {'error': 'ERROR', 'warn': 'WARNING', 'info': 'INFO'}.get(config.log_level, 'DEBUG')


class StartupAddressFilter(logging.Filter):
    """Drops uvicorn's 'Uvicorn running on …' bind-address line in production."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not (env.is_production and isinstance(record.msg, str) and record.msg.startswith('Uvicorn running on'))


UVICORN_LOG_CONFIG: dict[str, Any] = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'redaction': {'()': 'phoenixadult.utils.logging.redaction.RedactionFilter'},
        'startup_address': {'()': 'phoenixadult.utils.logging.uvicorn_logging.StartupAddressFilter'},
    },
    'formatters': {
        'provider': {'()': 'phoenixadult.utils.logging.context.AlignedFormatter'},
    },
    'handlers': {
        'default': {
            'class': 'logging.StreamHandler',
            'formatter': 'provider',
            'filters': ['startup_address', 'redaction'],
            'stream': 'ext://sys.stderr',
        },
    },
    'loggers': {
        'uvicorn': {'handlers': ['default'], 'level': uvicorn_level(), 'propagate': False},
        'uvicorn.error': {'level': uvicorn_level(), 'propagate': True},
        'uvicorn.access': {'handlers': [], 'level': 'CRITICAL', 'propagate': False},
    },
}


def configure_uvicorn_logging() -> None:
    """Lifespan-time counterpart of UVICORN_LOG_CONFIG (which covers the reloader and pre-startup lines):
    provider format on uvicorn's loggers; its access log is silenced — RequestContextMiddleware emits it in-scope."""
    for name in ('uvicorn', 'uvicorn.error'):
        lg = logging.getLogger(name)
        lg.setLevel(uvicorn_level())
        if not any(isinstance(f, RedactionFilter) for f in lg.filters):
            lg.addFilter(RedactionFilter())

    err = logging.getLogger('uvicorn.error')
    if not any(isinstance(f, StartupAddressFilter) for f in err.filters):
        err.addFilter(StartupAddressFilter())

    fmt = AlignedFormatter()
    for handler in logging.getLogger('uvicorn').handlers:
        handler.setFormatter(fmt)

    access = logging.getLogger('uvicorn.access')
    access.handlers = []
    access.propagate = False
    access.disabled = True
