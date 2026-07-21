from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.config import base_url_config_warning, config
from app.config.env import env
from app.registry import get_all_providers
from app.routes import dev_routes, env_routes, image_routes, logo_routes, metadata_cache_routes, people_cache_routes, plex_routes
from app.routes.provider_router import create_provider_router
from app.utils.logging.logger import logger
from app.utils.logging.request_context import RequestContextMiddleware
from app.utils.logging.uvicorn_logging import configure_uvicorn_logging
from app.utils.plex.media_type import provider_mount_path


def _log_startup_banner() -> None:
    logger.info(f'Plex Metadata Provider running on port {config.port}')
    for p in get_all_providers():
        logger.info(f'  Register in Plex → Settings > Metadata Agents > Add Provider: {config.base_url}{provider_mount_path(p)}   ({p.title})')

    qs = f'?token={env.admin_token}' if env.admin_token else ''
    logger.info(f'  Config UI:      {config.base_url}/config{qs}')
    logger.info(f'  People cache:   {config.base_url}/people-cache{qs}')
    logger.info(f'  Metadata cache: {config.base_url}/metadata-cache{qs}')
    if not env.is_production:
        logger.info(f'  Dev UI:         {config.base_url}/dev{qs}')
    if not env.admin_token:
        logger.warn('Admin auth DISABLED (ADMIN_TOKEN is blank) — /config and /dev are open to anyone who can reach this server')
    base_url_warning = base_url_config_warning()
    if base_url_warning:
        logger.warn(base_url_warning)


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
    app.include_router(image_routes.cache_router)

    # ── Runtime config UI ────────────────────────────────────────────────────
    app.include_router(env_routes.router, prefix='/config')

    # ── People Image Cache review UI (admin-guarded) ─────────────────────────
    app.include_router(people_cache_routes.router, prefix='/people-cache')

    # ── Snapshot metadata cache review UI (admin-guarded) ────────────────────
    app.include_router(metadata_cache_routes.router, prefix='/metadata-cache')

    # ── ClearLogo cache review UI (admin-guarded) ────────────────────────────
    app.include_router(logo_routes.router, prefix='/logos')

    # ── Plex server reconciliation (admin-guarded; no-op until PLEX_* are set) ─
    app.include_router(plex_routes.router, prefix='/plex')

    # ── Dev / test UI (non-production only, admin-guarded) ───────────────────
    if not env.is_production:
        app.include_router(dev_routes.router, prefix='/dev')

    # ── Health ───────────────────────────────────────────────────────────────
    @app.get('/health')
    async def health() -> dict[str, str]:
        return {'status': 'ok'}

    # ── Favicon (silences the browser's /favicon.ico request) ────────────────
    _html_dir = Path(__file__).parent / 'routes' / 'html'

    @app.get('/favicon.ico', include_in_schema=False)
    async def favicon_ico() -> FileResponse:
        return FileResponse(_html_dir / 'favicon.ico', media_type='image/x-icon')

    @app.get('/favicon.svg', include_in_schema=False)
    async def favicon_svg() -> FileResponse:
        return FileResponse(_html_dir / 'favicon.svg', media_type='image/svg+xml')

    return app


app = create_app()
