from __future__ import annotations

from urllib.parse import urlparse

from fastapi import Request

from phoenixadult.config.env import env
from phoenixadult.utils.auth.env_auth import _is_loopback, _presented_token, _token_matches

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
    if _PLEX_UA in (request.headers.get('user-agent') or '').lower():
        return
    if _is_loopback(request.client.host if request.client else None):
        return
    token = env.admin_token
    if token and _token_matches(_presented_token(request), token):
        return
    if _same_origin_subresource(request):
        return
    raise ImageAccessDenied
