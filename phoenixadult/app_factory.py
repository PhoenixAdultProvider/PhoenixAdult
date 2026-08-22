from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.middleware.gzip import GZipMiddleware

from phoenixadult import __version__
from phoenixadult.config import base_url_config_warning, config
from phoenixadult.config.env import env
from phoenixadult.registry import get_all_providers
from phoenixadult.routes import (
    dev_routes,
    env_routes,
    image_routes,
    logo_routes,
    metadata_cache_routes,
    people_cache_routes,
    plex_routes,
    queue_routes,
    search_routes,
)
from phoenixadult.routes.provider_router import create_provider_router
from phoenixadult.utils.concurrency import pools
from phoenixadult.utils.logging.logger import configure_logging, logger
from phoenixadult.utils.logging.request_context import RequestContextMiddleware
from phoenixadult.utils.logging.uvicorn_logging import configure_uvicorn_logging
from phoenixadult.utils.plex.media_type import provider_mount_path


def _log_startup_banner() -> None:
    from phoenixadult import __version__

    logger.info(f'PhoenixAdult {__version__} — Plex Metadata Provider running on port {config.port}')
    for p in get_all_providers():
        logger.info(f'  Register in Plex → Settings > Metadata Agents > Add Provider: {config.base_url}{provider_mount_path(p)}   ({p.title})')

    logger.info('  The provider mount is open to any client; set LOG_LEVEL=verbose to dump the headers of every request it receives')

    import logging as _logging

    from phoenixadult.utils.logging.response_trace import dump_dir, why_armed

    armed = why_armed()
    level = _logging.getLogger('phoenixadult').getEffectiveLevel()
    if armed:
        logger.info(f'  Response body dumps: ON via {armed} (log level {level}) — raw pages land in {dump_dir()}')
    else:
        logger.info(f'  Response body dumps: OFF (log level {level}) — set HTTP_BODY_DUMP=true to write raw pages to {dump_dir()}')

    from phoenixadult.utils.auth import user_store

    if user_store.user_count() == 0:
        logger.info(f'  First run — create the admin account at {config.base_url}/setup')
    else:
        logger.info(f'  Config UI:      {config.base_url}/config')
        logger.info(f'  People cache:   {config.base_url}/people')
        logger.info(f'  Metadata cache: {config.base_url}/metadata')
        if not env.is_production:
            logger.info(f'  Dev UI:         {config.base_url}/dev')
    base_url_warning = base_url_config_warning()
    if base_url_warning:
        logger.warn(base_url_warning)


def _migrate_plex_env() -> None:
    from phoenixadult.services import plex_connections

    migrated = plex_connections.migrate_env_connection()
    if migrated:
        logger.info('plex-connections', f'migrated the PLEX_* settings into the "{migrated}" connection')


def _migrate_metadataapi_env() -> None:
    from phoenixadult.utils.auth import user_tokens

    if user_tokens.migrate_env_token():
        logger.info('config', 'migrated METADATAAPI_TOKEN into the first admin account')


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
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    configure_uvicorn_logging()
    _log_startup_banner()
    from phoenixadult.routes.provider_router import restore_queue
    from phoenixadult.utils.cache import bundle_sweep
    from phoenixadult.utils.db import maintenance
    from phoenixadult.utils.images import logo_cache
    from phoenixadult.utils.people import cache as people_cache

    await _try_startup('db integrity check', maintenance.startup_recover_if_corrupt)
    await _try_startup('snapshot layout check', _warn_on_legacy_snapshots)
    await _try_startup('bundle sweep', bundle_sweep.startup_sweep)
    await _try_startup('plex connection migration', _migrate_plex_env)
    await _try_startup('metadataapi token migration', _migrate_metadataapi_env)
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


def _install_middleware(app: FastAPI) -> None:
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(RequestContextMiddleware)

    # ── Plex Client Tracking (records hits; resolves the owner's enrichment token) ─
    from phoenixadult.services import plex_connections
    from phoenixadult.utils.auth import user_tokens
    from phoenixadult.utils.plex import client_hits

    @app.middleware('http')
    async def plex_client_middleware(request: Request, call_next: Callable) -> Response:  # type: ignore[type-arg]
        client_id = request.headers.get('x-plex-client-identifier')
        if client_id:
            await asyncio.to_thread(client_hits.record, client_id, request.headers, request.url.path)
            owner = await asyncio.to_thread(plex_connections.owner_for_client, client_id)
            if owner is not None:
                token = await asyncio.to_thread(user_tokens.token_for_user, owner)
                user_tokens.current_metadataapi_token.set(token)
        return await call_next(request)  # type: ignore[no-any-return]

    from phoenixadult.utils.auth.hook_middleware import HookPathMiddleware

    app.add_middleware(HookPathMiddleware)


def _mount_routers(app: FastAPI) -> None:
    # ── Authentication (login / setup / logout / account) ────────────────────
    from phoenixadult.routes import auth_routes

    app.include_router(auth_routes.public_router)
    app.include_router(auth_routes.router)

    # ── Dynamic Provider Routes ──────────────────────────────────────────────
    for provider in get_all_providers():
        mount = provider_mount_path(provider)
        app.include_router(create_provider_router(provider), prefix=mount)

    # ── Image Serving ────────────────────────────────────────────────────────
    app.include_router(image_routes.router, prefix='/images')
    app.include_router(image_routes.cache_router)

    # ── Runtime Config UI ────────────────────────────────────────────────────
    app.include_router(env_routes.router, prefix='/config')

    # ── User Accounts (admin only) ───────────────────────────────────────────
    from phoenixadult.routes import users_routes

    app.include_router(users_routes.router, prefix='/users')

    # ── People Cache Review UI (admin-guarded) ─────────────────────────
    app.include_router(people_cache_routes.router, prefix='/people')

    # ── Snapshot Metadata Cache Review UI (admin-guarded) ────────────────────
    app.include_router(metadata_cache_routes.router, prefix='/metadata')

    # ── ClearLogo Cache Review UI (admin-guarded) ────────────────────────────
    app.include_router(logo_routes.router, prefix='/logos')

    # ── Background Scrape Queue UI (admin-guarded) ───────────────────────────
    app.include_router(queue_routes.router, prefix='/queue')

    # ── Stored-Search Browser (admin only) ───────────────────────────────────
    app.include_router(search_routes.router, prefix='/searches')

    # ── Plex Server Reconciliation (admin-guarded; no-op until PLEX_* are set) ─
    app.include_router(plex_routes.router, prefix='/plex')

    # ── Dev / Test UI (off unless DEV_UI_ENABLE, admin-guarded) ──────────────
    app.include_router(dev_routes.router, prefix='/dev')


def _install_error_pages(app: FastAPI) -> None:
    # ── Image Guard 403 (HTML page for browsers, JSON for API callers) ───────
    from phoenixadult.utils.auth.image_guard import FORBIDDEN_PAGE, ImageAccessDenied

    @app.exception_handler(ImageAccessDenied)
    async def image_access_denied(request: Request, exc: ImageAccessDenied) -> Response:
        if 'text/html' in (request.headers.get('accept') or ''):
            return HTMLResponse(FORBIDDEN_PAGE, status_code=403)
        return JSONResponse({'error': 'Direct image access is not allowed'}, status_code=403)

    # ── Login Required (redirect browsers to /login, JSON 401 for API callers) ─
    from urllib.parse import quote

    from phoenixadult.utils.auth import user_store
    from phoenixadult.utils.auth.user_auth import LoginRequired

    @app.exception_handler(LoginRequired)
    async def login_required(request: Request, exc: LoginRequired) -> Response:
        wants_html = request.method in ('GET', 'HEAD') and 'text/html' in (request.headers.get('accept') or '')
        if not wants_html:
            return JSONResponse({'error': 'Unauthorized'}, status_code=401)
        if await asyncio.to_thread(user_store.user_count) == 0:
            return Response(status_code=302, headers={'Location': '/setup'})
        target = request.url.path + (f'?{request.url.query}' if request.url.query else '')
        return Response(status_code=302, headers={'Location': f'/login?next={quote(target)}'})


def _install_static_routes(app: FastAPI) -> None:
    # ── Health ───────────────────────────────────────────────────────────────
    @app.get('/health')
    async def health() -> dict[str, str]:
        return {'status': 'ok'}

    # ── Favicon (silences the browser's /favicon.ico request) ────────────────
    _html_dir = Path(__file__).parent / 'routes' / 'html'

    from phoenixadult.routes import assets

    @app.get('/favicon.ico', include_in_schema=False)
    async def favicon_ico(request: Request) -> Response:
        return assets.css_response(_html_dir / 'favicon.ico', request, '', media_type='image/x-icon')

    @app.get('/favicon.svg', include_in_schema=False)
    async def favicon_svg(request: Request) -> Response:
        return assets.css_response(_html_dir / 'favicon.svg', request, '', media_type='image/svg+xml')

    # ── Theme Stylesheets (public — colors only, needed before any auth) ─────
    from phoenixadult.routes import FONT_NAMES, THEME_NAMES

    @app.get('/themes/{name}.css', include_in_schema=False)
    async def theme_css(name: str, request: Request, v: str = '') -> Response:
        if name not in THEME_NAMES:
            raise HTTPException(status_code=404, detail='unknown theme')
        return assets.css_response(_html_dir / 'themes' / f'{name}.css', request, v)

    # ── Self-Hosted Fonts (public — the pages need them before any auth) ─────
    @app.get('/fonts/{name}.woff2', include_in_schema=False)
    async def font_file(name: str) -> FileResponse:
        if name not in FONT_NAMES:
            raise HTTPException(status_code=404, detail='unknown font')
        return FileResponse(_html_dir / 'fonts' / f'{name}.woff2', media_type='font/woff2', headers={'Cache-Control': 'public, max-age=31536000, immutable'})


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title='PhoenixAdult Provider', version=__version__, lifespan=_lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    _install_middleware(app)
    _mount_routers(app)
    _install_error_pages(app)
    _install_static_routes(app)
    return app


app = create_app()
