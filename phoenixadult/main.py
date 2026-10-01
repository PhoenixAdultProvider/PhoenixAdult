from __future__ import annotations

import uvicorn

from phoenixadult.app_factory import app
from phoenixadult.config import config
from phoenixadult.config.env import env
from phoenixadult.utils.logging.uvicorn_logging import UVICORN_LOG_CONFIG, uvicorn_level


def main() -> None:
    reload = not env.is_production
    uvicorn.run(
        'phoenixadult.main:app' if reload else app,
        host='',
        port=config.port,
        reload=reload,
        log_config=UVICORN_LOG_CONFIG,
        log_level=uvicorn_level().lower(),
        proxy_headers=True,
        forwarded_allow_ips='127.0.0.1',
    )


if __name__ == '__main__':
    main()


__all__ = ['app', 'main']
