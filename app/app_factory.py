from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response

from app.config import config
from app.config.env import env
from app.registry import (
    get_all_providers,
    get_sites_for_provider,
    provider_mount_path,
)
from app.routes import actor_cache_routes, dev_routes, env_routes, image_routes, metadata_cache_routes
from app.routes.provider_router import create_provider_router
from app.utils.logging.logger import logger


def create_app() -> FastAPI:
    app = FastAPI(title='PhoenixAdult Provider', version='1.0.0')

    @app.middleware('http')
    async def request_logging(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        # Don't log /config bodies — they can carry secret values being saved.
        logger.http(
            f'{request.method} {request.url.path}',
            language=request.headers.get('x-plex-language'),
            country=request.headers.get('x-plex-country'),
        )
        return await call_next(request)

    # ── Dynamic provider routes ──────────────────────────────────────────────
    for provider in get_all_providers():
        mount = provider_mount_path(provider)
        app.include_router(create_provider_router(provider), prefix=mount)
        logger.info(f'Registered provider "{provider.title}" at {mount}')

    # ── Image serving ────────────────────────────────────────────────────────
    app.include_router(image_routes.router, prefix='/images')
    app.include_router(image_routes.cache_router)  # snapshot images at /cache/...

    # ── Runtime config UI ────────────────────────────────────────────────────
    app.include_router(env_routes.router, prefix='/config')
    logger.info(f'Config UI available at {config.base_url}/config')

    # ── Actor image cache review UI (admin-guarded) ───────────────────────────
    app.include_router(actor_cache_routes.router, prefix='/actor-cache')
    logger.info(f'Actor image cache review at {config.base_url}/actor-cache')

    # ── Snapshot metadata cache review UI (admin-guarded) ─────────────────────
    app.include_router(metadata_cache_routes.router, prefix='/metadata-cache')
    logger.info(f'Metadata cache review at {config.base_url}/metadata-cache')

    # ── Dev / test UI (non-production only, admin-guarded) ────────────────────
    if not env.is_production:
        app.include_router(dev_routes.router, prefix='/dev')
        logger.info(f'Dev UI available at {config.base_url}/dev')

    # ── Health / diagnostics ─────────────────────────────────────────────────
    @app.get('/health')
    async def health() -> dict[str, str]:
        return {'status': 'ok'}

    @app.get('/providers')
    async def providers() -> list[dict[str, Any]]:
        return [
            {
                'id': p.id,
                'title': p.title,
                'mediaType': p.media_type,
                'plexIdentifier': p.plex_identifier,
                'url': provider_mount_path(p),
                'sites': [{'name': s.name, 'aliases': s.aliases, 'contentType': s.content_type} for s in get_sites_for_provider(p.id)],
            }
            for p in get_all_providers()
        ]

    return app


app = create_app()
