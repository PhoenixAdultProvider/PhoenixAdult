from __future__ import annotations

from collections.abc import Awaitable, Callable
from inspect import isawaitable
from urllib.parse import urlparse

from fastapi import Request

from phoenixadult.config.env import env
from phoenixadult.utils.auth.url_signing import signed_request_ok
from phoenixadult.utils.auth.user_auth import is_loopback, resolve_user
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.logging.request_trace import trace_request

_PLEX_UA = 'plexmediaserver'

FORBIDDEN_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>403 Forbidden</title>
  <style>
    body { font-family: system-ui, sans-serif; display: flex; min-height: 100vh; margin: 0;
           align-items: center; justify-content: center; text-align: center; background: #fff; color: #000; }
    h1 { font-size: 64px; margin: 0; }
    p { font-size: 15px; margin: 8px 0 0; }
  </style>
</head>
<body>
  <div>
    <h1>403 Forbidden</h1>
    <p>You don’t have permission to access this resource.</p>
  </div>
</body>
</html>
"""


class ImageAccessDenied(Exception):
    pass


def _image_subresource(request: Request) -> bool:
    if (request.headers.get('sec-fetch-mode') or '').lower() == 'navigate':
        return False
    accept = (request.headers.get('accept') or '').lower()
    return 'image/' in accept and 'text/html' not in accept


def _same_origin_subresource(request: Request) -> bool:
    site = (request.headers.get('sec-fetch-site') or '').lower()
    mode = (request.headers.get('sec-fetch-mode') or '').lower()
    if site in ('same-origin', 'same-site'):
        return mode != 'navigate'
    if site:
        return False
    referer_host = urlparse(request.headers.get('referer') or '').hostname
    return bool(referer_host) and referer_host == request.url.hostname


def _plex_user_agent(request: Request) -> bool:
    return _PLEX_UA in (request.headers.get('user-agent') or '').lower()


def _loopback(request: Request) -> bool:
    return is_loopback(request.client.host if request.client else None)


async def _signed_in(request: Request) -> bool:
    return await resolve_user(request) is not None


_ADMISSIONS: tuple[tuple[str, Callable[[Request], bool | Awaitable[bool]]], ...] = (
    ('signature', signed_request_ok),
    ('plex user-agent', _plex_user_agent),
    ('loopback', _loopback),
    ('signed-in user', _signed_in),
    ('same-origin subresource', _same_origin_subresource),
    ('image subresource', _image_subresource),
)


async def _admitted_by(request: Request) -> str | None:
    for reason, admits in _ADMISSIONS:
        verdict = admits(request)
        if isawaitable(verdict):
            verdict = await verdict
        if verdict:
            return reason
    return None


async def image_guard(request: Request) -> None:
    enabled = env.image_guard_enabled
    if enabled:
        trace_request('image-guard', request)
    admitted = await _admitted_by(request)
    if not enabled:
        if admitted is None:
            logger.info('image-guard', f'would deny {request.url.path} (ua="{request.headers.get("user-agent") or ""}") — IMAGE_GUARD_ENABLE is off')
        elif admitted in ('plex user-agent', 'image subresource'):
            logger.debug('image-guard', f'{request.url.path} admitted only by {admitted}')
        return
    if admitted is not None:
        return
    logger.warn('image-guard', f'denied {request.url.path} (ua="{request.headers.get("user-agent") or ""}")')
    raise ImageAccessDenied
