from __future__ import annotations

import uvicorn

from app.app_factory import app
from app.config import config


def main() -> None:
    uvicorn.run(
        app,
        host='0.0.0.0',
        port=config.port,
        log_level=config.log_level if config.log_level in {'critical', 'error', 'warning', 'info', 'debug', 'trace'} else 'info',
    )


if __name__ == '__main__':
    main()


__all__ = ['app', 'main']
