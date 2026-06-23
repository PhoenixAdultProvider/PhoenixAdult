from __future__ import annotations

import uvicorn

from app.app_factory import app
from app.config import config
from app.config.env import env
from app.registry import get_all_providers, provider_mount_path
from app.utils.logging.logger import logger


def _log_startup_banner() -> None:
    logger.info(f'Plex Metadata Provider running on port {config.port}')
    logger.info(f'Diagnostics: {config.base_url}/providers')
    for p in get_all_providers():
        logger.info(f'  Register in Plex → Settings > Metadata Agents > Add Provider: {config.base_url}{provider_mount_path(p)}   ({p.title})')

    # Admin surfaces — include the token in the link so it works through a tunnel.
    qs = f'?token={env.admin_token}' if env.admin_token else ''
    logger.info(f'  Config UI:      {config.base_url}/config{qs}')
    logger.info(f'  Actor cache:    {config.base_url}/actor-cache{qs}')
    logger.info(f'  Metadata cache: {config.base_url}/metadata-cache{qs}')
    if not env.is_production:
        logger.info(f'  Dev UI:         {config.base_url}/dev{qs}')
    if not env.admin_token:
        logger.warn('Admin auth DISABLED (ADMIN_TOKEN is blank) — /config and /dev are open to anyone who can reach this server')


def main() -> None:
    _log_startup_banner()
    uvicorn.run(
        app,
        host='0.0.0.0',
        port=config.port,
        log_level=config.log_level if config.log_level in {'critical', 'error', 'warning', 'info', 'debug', 'trace'} else 'info',
    )


if __name__ == '__main__':
    main()


__all__ = ['app', 'main']
