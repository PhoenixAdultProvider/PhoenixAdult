from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from starlette.middleware.gzip import GZipMiddleware

from phoenixadult.config import base_url_config_warning, config
from phoenixadult.config.env import env
from phoenixadult.registry import get_all_providers
from phoenixadult.routes import dev_routes, env_routes, image_routes, logo_routes, metadata_cache_routes, people_cache_routes, plex_routes, queue_routes
from phoenixadult.routes.provider_router import create_provider_router
from phoenixadult.utils.concurrency import pools
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.logging.request_context import RequestContextMiddleware
from phoenixadult.utils.logging.uvicorn_logging import configure_uvicorn_logging
from phoenixadult.utils.plex.media_type import provider_mount_path


def _log_startup_banner() -> None:
    logger.info(f'Plex Metadata Provider running on port {config.port}')
    for p in get_all_providers():
        logger.info(f'  Register in Plex → Settings > Metadata Agents > Add Provider: {config.base_url}{provider_mount_path(p)}   ({p.title})')

    qs = f'?token={env.admin_token}' if env.admin_token else ''
    logger.info(f'  Config UI:      {config.base_url}/config{qs}')
    logger.info(f'  People cache:   {config.base_url}/people{qs}')
    logger.info(f'  Metadata cache: {config.base_url}/metadata{qs}')
    if not env.is_production:
        logger.info(f'  Dev UI:         {config.base_url}/dev{qs}')
    if not env.admin_token:
        logger.warn('Admin auth DISABLED (ADMIN_TOKEN is blank) — /config and /dev are open to anyone who can reach this server')
    base_url_warning = base_url_config_warning()
    if base_url_warning:
        logger.warn(base_url_warning)


async def _try_startup(label: str, fn: Callable[[], object]) -> None:
    try:
        await asyncio.to_thread(fn)
    except Exception as err:  # noqa: BLE001 - startup must survive a broken derived store
        logger.error(f'startup step "{label}" failed (continuing): {err!r}')


async def _backup_task() -> None:
    from phoenixadult.utils.db import maintenance

    hours = env.db_backup_interval_hours
    if hours <= 0:
        return
    if maintenance.backup_age_hours() >= hours:
        await _try_startup('db startup backup', maintenance.backup_once)
    while True:
        await asyncio.sleep(hours * 3600)
        await _try_startup('db backup', maintenance.backup_once)


def _warn_on_legacy_snapshots() -> None:
    from phoenixadult.utils.cache import BUNDLE_ROOT, scene_store

    stale = scene_store.legacy_count(f'{BUNDLE_ROOT}/%')
    if stale:
        logger.warn(f'{stale} snapshot(s) still use the pre-{BUNDLE_ROOT} folder layout — run scripts/migrate_snapshot_layout.py --apply')


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_uvicorn_logging()
    _log_startup_banner()
    from phoenixadult.routes.provider_router import restore_queue
    from phoenixadult.utils.db import maintenance
    from phoenixadult.utils.images import logo_cache
    from phoenixadult.utils.people import cache as people_cache

    await _try_startup('db integrity check', maintenance.startup_recover_if_corrupt)
    await _try_startup('snapshot layout check', _warn_on_legacy_snapshots)
    if people_cache.cache_enabled():
        await _try_startup('people-cache reconcile', people_cache.reconcile)
    await _try_startup('logo-cache reconcile', logo_cache.reconcile)
    try:
        await restore_queue()
    except Exception as err:  # noqa: BLE001 - a broken queue replay must not block serving
        logger.error(f'startup step "restore-queue" failed (continuing): {err!r}')

    backup = asyncio.create_task(_backup_task())
    try:
        yield
    finally:
        backup.cancel()
        pools.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(title='PhoenixAdult Provider', version='1.0.0', lifespan=_lifespan)

    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(RequestContextMiddleware)

    # ── Dynamic Provider Routes ──────────────────────────────────────────────
    for provider in get_all_providers():
        mount = provider_mount_path(provider)
        app.include_router(create_provider_router(provider), prefix=mount)

    # ── Image Serving ────────────────────────────────────────────────────────
    app.include_router(image_routes.router, prefix='/images')
    app.include_router(image_routes.cache_router)

    # ── Runtime Config UI ────────────────────────────────────────────────────
    app.include_router(env_routes.router, prefix='/config')

    # ── People Cache Review UI (admin-guarded) ─────────────────────────
    app.include_router(people_cache_routes.router, prefix='/people')

    # ── Snapshot Metadata Cache Review UI (admin-guarded) ────────────────────
    app.include_router(metadata_cache_routes.router, prefix='/metadata')

    # ── ClearLogo Cache Review UI (admin-guarded) ────────────────────────────
    app.include_router(logo_routes.router, prefix='/logos')

    # ── Background Scrape Queue UI (admin-guarded) ───────────────────────────
    app.include_router(queue_routes.router, prefix='/queue')

    # ── Plex Server Reconciliation (admin-guarded; no-op until PLEX_* are set) ─
    app.include_router(plex_routes.router, prefix='/plex')

    # ── Dev / Test UI (non-production only, admin-guarded) ───────────────────
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
