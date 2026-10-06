from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.middleware.gzip import GZipMiddleware

from phoenixadult import __version__
from phoenixadult.clients import CLIENT_REGISTRY
from phoenixadult.config import base_url_config_warning, config
from phoenixadult.config.env import env
from phoenixadult.registry import get_all_providers
from phoenixadult.routes import (
    FONT_NAMES,
    THEME_NAMES,
    assets,
    auth_routes,
    dev_routes,
    env_routes,
    image_routes,
    logo_routes,
    metadata_cache_routes,
    people_cache_routes,
    plex_routes,
    queue_routes,
    search_routes,
    users_routes,
)
from phoenixadult.routes.provider_router import create_provider_router, restore_queue
from phoenixadult.services import plex_connections, snapshot_backfill
from phoenixadult.services.scrape_queue import lane_workers
from phoenixadult.utils.auth import user_store, user_tokens
from phoenixadult.utils.auth.hook_middleware import HookPathMiddleware
from phoenixadult.utils.auth.image_guard import FORBIDDEN_PAGE, ImageAccessDenied
from phoenixadult.utils.auth.user_auth import LoginRequired
from phoenixadult.utils.cache import bundle_sweep, scene_store
from phoenixadult.utils.cache.layout import BUNDLE_ROOT
from phoenixadult.utils.concurrency import pools
from phoenixadult.utils.concurrency.gate import limits
from phoenixadult.utils.concurrency.pools import sizes
from phoenixadult.utils.db import maintenance
from phoenixadult.utils.fs import atomic
from phoenixadult.utils.http import client as http_client
from phoenixadult.utils.http.security_headers import SecurityHeadersMiddleware
from phoenixadult.utils.images import face_crop, image_fetcher, logo_cache
from phoenixadult.utils.logging.logger import configure_logging, logger
from phoenixadult.utils.logging.request_context import RequestContextMiddleware
from phoenixadult.utils.logging.response_trace import dump_dir, tracing_wanted
from phoenixadult.utils.logging.uvicorn_logging import configure_uvicorn_logging
from phoenixadult.utils.people import cache as people_cache
from phoenixadult.utils.plex import client_hits
from phoenixadult.utils.plex.media_type import provider_mount_path


def _log_startup_banner() -> None:
    logger.info(f'PhoenixAdult {__version__} — Plex Metadata Provider running on port {config.port}')
    for p in get_all_providers():
        logger.info(f'  Register in Plex → Settings > Metadata Agents > Add Provider: {config.base_url}{provider_mount_path(p)}   ({p.title})')

    logger.info('  The provider mount is open to any client; set LOG_LEVEL=verbose to dump the headers of every request it receives')

    logger.info(f'  Thread pools: {", ".join(f"{n}={w}" for n, w in sizes().items())}')
    logger.info(f'  Queue lanes:  {", ".join(f"{n}={w}" for n, w in lane_workers().items())}')
    logger.info(f'  Fan-out caps: {", ".join(f"{n}={w}" for n, w in limits().items())} (process-wide, not per scene)')
    logger.info(f'  Bypass chain: {env.bypass_order_raw or "(default)"} · FlareSolverr {env.flaresolverr_url or "not configured"}')

    if tracing_wanted():
        logger.info(f'  Response body dumps: ON — raw pages land in {dump_dir()}')
    else:
        logger.info(f'  Response body dumps: OFF — set HTTP_BODY_DUMP=true to write raw pages to {dump_dir()}')

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
    migrated = plex_connections.migrate_env_connection()
    if migrated:
        logger.info('plex-connections', f'migrated the PLEX_* settings into the "{migrated}" connection')


def _migrate_metadataapi_env() -> None:
    if user_tokens.migrate_env_token():
        logger.info('config', 'migrated METADATAAPI_TOKEN into the first admin account')


async def _try_startup(label: str, fn: Callable[[], object]) -> None:
    try:
        await pools.run_in('store', fn)
    except Exception as err:  # noqa: BLE001 - startup must survive a broken derived store
        logger.error(f'startup step "{label}" failed (continuing): {err!r}')


async def _backup_task() -> None:
    hours = env.db_backup_interval_hours
    if hours <= 0:
        return
    if await pools.run_in('store', maintenance.backup_age_hours) >= hours:
        await _try_startup('db startup backup', maintenance.backup_once)
    while True:
        await asyncio.sleep(hours * 3600)
        await _try_startup('db backup', maintenance.backup_once)


def _warn_on_legacy_snapshots() -> None:
    stale = scene_store.legacy_count(f'{BUNDLE_ROOT}/%')
    if stale:
        logger.warn(f'{stale} snapshot(s) still use the pre-{BUNDLE_ROOT} folder layout — run scripts/migrate_snapshot_layout.py --apply')


def _sweep_partial_writes() -> None:
    removed = atomic.sweep_partials(env.people_cache_dir, logo_cache.cache_dir())
    if removed:
        logger.info('startup', f'removed {removed} partial image write(s) left by an interrupted run')


async def close_http_clients() -> None:
    await http_client.close_shared()
    await image_fetcher.close_shared()
    await snapshot_backfill.close_client()
    for client in CLIENT_REGISTRY.values():
        await client.aclose()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    configure_uvicorn_logging()
    await _try_startup('db integrity check', maintenance.startup_recover_if_corrupt)
    _log_startup_banner()

    await _try_startup('snapshot layout check', _warn_on_legacy_snapshots)
    await _try_startup('bundle sweep', bundle_sweep.startup_sweep)
    await _try_startup('plex connection migration', _migrate_plex_env)
    await _try_startup('metadataapi token migration', _migrate_metadataapi_env)
    if env.people_cache_enabled:
        await _try_startup('people-cache reconcile', people_cache.reconcile)
    await _try_startup('logo-cache reconcile', logo_cache.reconcile)
    try:
        await restore_queue()
    except Exception as err:  # noqa: BLE001 - a broken queue replay must not block serving
        logger.error(f'startup step "restore-queue" failed (continuing): {err!r}')

    backup = asyncio.create_task(_backup_task())
    warm = asyncio.create_task(pools.run_in('image', face_crop.available)) if env.people_cache_face_enabled else None
    sweep = asyncio.create_task(pools.run_in('fs', _sweep_partial_writes))
    try:
        yield
    finally:
        backup.cancel()
        sweep.cancel()
        if warm is not None:
            warm.cancel()
        await close_http_clients()
        pools.shutdown()


def _install_middleware(app: FastAPI) -> None:
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)

    # ── Plex Client Tracking (records hits; resolves the owner's enrichment token) ─

    mounts = tuple(provider_mount_path(p) for p in get_all_providers())

    @app.middleware('http')
    async def plex_client_middleware(request: Request, call_next: Callable) -> Response:  # type: ignore[type-arg]
        client_id = request.headers.get('x-plex-client-identifier')
        if client_id and request.url.path.startswith(mounts):
            await pools.run_in('store', client_hits.record, client_id, request.headers, request.url.path)
            owner = await pools.run_in('store', plex_connections.owner_for_client, client_id)
            if owner is not None:
                token = await pools.run_in('auth', user_tokens.token_for_user, owner)
                user_tokens.current_metadataapi_token.set(token)
        return await call_next(request)  # type: ignore[no-any-return]

    app.add_middleware(HookPathMiddleware)


def _mount_routers(app: FastAPI) -> None:
    # ── Authentication (login / setup / logout / account) ────────────────────
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

    # ── Plex Server Connections and Reconciliation (per-user connections) ─────
    app.include_router(plex_routes.router, prefix='/plex')

    # ── Dev / Test UI (off unless DEV_UI_ENABLE, admin-guarded) ──────────────
    app.include_router(dev_routes.router, prefix='/dev')


def _install_error_pages(app: FastAPI) -> None:
    # ── Image Guard 403 (HTML page for browsers, JSON for API callers) ───────

    @app.exception_handler(ImageAccessDenied)
    async def image_access_denied(request: Request, exc: ImageAccessDenied) -> Response:
        if 'text/html' in (request.headers.get('accept') or ''):
            return HTMLResponse(FORBIDDEN_PAGE, status_code=403)
        return JSONResponse({'error': 'Direct image access is not allowed'}, status_code=403)

    # ── Login Required (redirect browsers to /login, JSON 401 for API callers) ─

    @app.exception_handler(LoginRequired)
    async def login_required(request: Request, exc: LoginRequired) -> Response:
        wants_html = request.method in ('GET', 'HEAD') and 'text/html' in (request.headers.get('accept') or '')
        if not wants_html:
            return JSONResponse({'error': 'Unauthorized'}, status_code=401)
        if await pools.run_in('auth', user_store.user_count) == 0:
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

    @app.get('/favicon.ico', include_in_schema=False)
    async def favicon_ico(request: Request) -> Response:
        return assets.asset_response(_html_dir / 'favicon.ico', request, '', media_type='image/x-icon')

    @app.get('/favicon.svg', include_in_schema=False)
    async def favicon_svg(request: Request) -> Response:
        return assets.asset_response(_html_dir / 'favicon.svg', request, '', media_type='image/svg+xml')

    # ── Theme Stylesheets (public — colors only, needed before any auth) ─────

    @app.get('/themes/{name}.css', include_in_schema=False)
    async def theme_css(name: str, request: Request, v: str = '') -> Response:
        if name not in THEME_NAMES:
            raise HTTPException(status_code=404, detail='unknown theme')
        return assets.asset_response(_html_dir / 'themes' / f'{name}.css', request, v)

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
