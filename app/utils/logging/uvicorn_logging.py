from __future__ import annotations

import logging

from uvicorn.logging import AccessFormatter, DefaultFormatter

from app.config.env import env
from app.utils.logging.redaction import RedactionFilter

_DEFAULT_FMT = '%(asctime)s %(levelprefix)s %(message)s'
_ACCESS_FMT = '%(asctime)s %(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s'


class StartupAddressFilter(logging.Filter):
    """Drops uvicorn's 'Uvicorn running on …' bind-address line in production."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not (env.is_production and isinstance(record.msg, str) and record.msg.startswith('Uvicorn running on'))


def configure_uvicorn_logging() -> None:
    """Attach redaction + startup-address filters and add timestamps to uvicorn's loggers.

    Called from the app lifespan so it applies under any entrypoint, after uvicorn
    has configured its own logging.
    """
    for name in ('uvicorn', 'uvicorn.error', 'uvicorn.access'):
        lg = logging.getLogger(name)
        if not any(isinstance(f, RedactionFilter) for f in lg.filters):
            lg.addFilter(RedactionFilter())

    err = logging.getLogger('uvicorn.error')
    if not any(isinstance(f, StartupAddressFilter) for f in err.filters):
        err.addFilter(StartupAddressFilter())

    # uvicorn.error has no handlers and propagates to the 'uvicorn' logger.
    for handler in logging.getLogger('uvicorn').handlers:
        handler.setFormatter(DefaultFormatter(_DEFAULT_FMT))
    for handler in logging.getLogger('uvicorn.access').handlers:
        handler.setFormatter(AccessFormatter(_ACCESS_FMT))
