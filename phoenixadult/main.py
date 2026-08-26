from __future__ import annotations

import uvicorn

from phoenixadult.app_factory import app
from phoenixadult.config import config
from phoenixadult.config.env import env
from phoenixadult.utils.logging.uvicorn_logging import UVICORN_LOG_CONFIG


def main() -> None:
    log_level = config.log_level if config.log_level in {'critical', 'error', 'warning', 'info', 'debug', 'trace'} else 'info'
    reload = not env.is_production
    uvicorn.run(
        'phoenixadult.main:app' if reload else app,
        host='',
        port=config.port,
        reload=reload,
        log_config=UVICORN_LOG_CONFIG,
        log_level=log_level,
        proxy_headers=True,
        forwarded_allow_ips='127.0.0.1',
    )


if __name__ == '__main__':
    main()


__all__ = ['app', 'main']
