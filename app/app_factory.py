from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import config
from app.config.env import env
from app.registry import get_all_providers, provider_mount_path
from app.routes import actor_cache_routes, dev_routes, env_routes, image_routes, metadata_cache_routes
from app.routes.provider_router import create_provider_router
from app.utils.logging.logger import logger
from app.utils.logging.request_context import RequestContextMiddleware
from app.utils.logging.uvicorn_logging import configure_uvicorn_logging


def _log_startup_banner() -> None:
    logger.info(f'Plex Metadata Provider running on port {config.port}')
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


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_uvicorn_logging()
    _log_startup_banner()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title='PhoenixAdult Provider', version='1.0.0', lifespan=_lifespan)

    # Per-request id + access logging (don't log /config bodies — they carry secrets).
    app.add_middleware(RequestContextMiddleware)

    # ── Dynamic provider routes ──────────────────────────────────────────────
    for provider in get_all_providers():
        mount = provider_mount_path(provider)
        app.include_router(create_provider_router(provider), prefix=mount)

    # ── Image serving ────────────────────────────────────────────────────────
    app.include_router(image_routes.router, prefix='/images')
    app.include_router(image_routes.cache_router)  # snapshot images at /cache/...

    # ── Runtime config UI ────────────────────────────────────────────────────
    app.include_router(env_routes.router, prefix='/config')

    # ── Actor image cache review UI (admin-guarded) ──────────────────────────
    app.include_router(actor_cache_routes.router, prefix='/actor-cache')

    # ── Snapshot metadata cache review UI (admin-guarded) ────────────────────
    app.include_router(metadata_cache_routes.router, prefix='/metadata-cache')

    # ── Dev / test UI (non-production only, admin-guarded) ───────────────────
    if not env.is_production:
        app.include_router(dev_routes.router, prefix='/dev')

    # ── Health ───────────────────────────────────────────────────────────────
    @app.get('/health')
    async def health() -> dict[str, str]:
        return {'status': 'ok'}

    return app


app = create_app()
