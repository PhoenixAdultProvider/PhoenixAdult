from __future__ import annotations

import logging

from app.config.env import env
from app.utils.logging.context import LOG_FORMAT
from app.utils.logging.redaction import RedactionFilter


class StartupAddressFilter(logging.Filter):
    """Drops uvicorn's 'Uvicorn running on …' bind-address line in production."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not (env.is_production and isinstance(record.msg, str) and record.msg.startswith('Uvicorn running on'))


def configure_uvicorn_logging() -> None:
    """Make uvicorn's logs match the provider format, and silence its duplicate access log.

    Called from the app lifespan so it applies under any entrypoint, after uvicorn
    has configured its own logging. The per-request access line is emitted in-scope
    by RequestContextMiddleware instead (so it carries the request id); uvicorn's own
    access logger fires out-of-scope and would duplicate it, so it's disabled here.
    """
    for name in ('uvicorn', 'uvicorn.error'):
        lg = logging.getLogger(name)
        if not any(isinstance(f, RedactionFilter) for f in lg.filters):
            lg.addFilter(RedactionFilter())

    err = logging.getLogger('uvicorn.error')
    if not any(isinstance(f, StartupAddressFilter) for f in err.filters):
        err.addFilter(StartupAddressFilter())

    # uvicorn.error has no handlers and propagates to the 'uvicorn' logger.
    fmt = logging.Formatter(LOG_FORMAT)
    for handler in logging.getLogger('uvicorn').handlers:
        handler.setFormatter(fmt)

    # Silence uvicorn's own access log — RequestContextMiddleware emits the access
    # line in-scope (with the request id, redaction, and provider format) instead.
    access = logging.getLogger('uvicorn.access')
    access.handlers = []
    access.propagate = False
    access.disabled = True
