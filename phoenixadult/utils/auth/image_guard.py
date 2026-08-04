from __future__ import annotations

import json
from urllib.parse import urlparse

from fastapi import Request

from phoenixadult.config.env import env
from phoenixadult.utils.auth.url_signing import signed_request_ok
from phoenixadult.utils.auth.user_auth import _is_loopback, resolve_user
from phoenixadult.utils.logging.logger import logger

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


async def image_guard(request: Request) -> None:
    if not env.image_guard_enabled:
        return
    logger.verbose('image-guard', f'{request.method} {request.url.path} headers:\n' + json.dumps(dict(request.headers), indent=2, sort_keys=True))
    if signed_request_ok(request):
        return
    if _PLEX_UA in (request.headers.get('user-agent') or '').lower():
        return
    if _is_loopback(request.client.host if request.client else None):
        return
    if await resolve_user(request) is not None:
        return
    if _same_origin_subresource(request):
        return
    if _image_subresource(request):
        return
    logger.warn('image-guard', f'denied {request.url.path} (ua="{request.headers.get("user-agent") or ""}")')
    raise ImageAccessDenied
