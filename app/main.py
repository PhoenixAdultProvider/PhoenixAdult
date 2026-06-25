from __future__ import annotations

import uvicorn

from app.app_factory import app
from app.config import config
from app.config.env import env
from app.utils.logging.uvicorn_logging import UVICORN_LOG_CONFIG


def main() -> None:
    log_level = config.log_level if config.log_level in {'critical', 'error', 'warning', 'info', 'debug', 'trace'} else 'info'
    # Outside production, run with --reload. Reload needs an import string (not the
    # app object) so uvicorn can re-import on change.
    reload = not env.is_production
    uvicorn.run(
        'app.main:app' if reload else app,
        host='0.0.0.0',
        port=config.port,
        reload=reload,
        log_config=UVICORN_LOG_CONFIG,
        log_level=log_level,
    )


if __name__ == '__main__':
    main()


__all__ = ['app', 'main']
