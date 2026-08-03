from __future__ import annotations

import hashlib
import hmac
import re
from urllib.parse import unquote, urlsplit

from fastapi import Request

from phoenixadult.config.env import env

_SIG_RE = re.compile(r'[?&]sig=[0-9a-f]*$')


def _key() -> bytes | None:
    token = env.admin_token
    return token.encode() if token else None


def strip_sig(url: str) -> str:
    return _SIG_RE.sub('', url)


def _digest(key: bytes, path: str, query: str) -> str:
    message = unquote(path) + (f'?{query}' if query else '')
    return hmac.new(key, message.encode(), hashlib.sha256).hexdigest()[:32]


def sign_url(url: str | None) -> str | None:
    key = _key()
    if not url or key is None:
        return url
    bare = strip_sig(url)
    parts = urlsplit(bare)
    if not parts.path.startswith('/'):
        return url
    digest = _digest(key, parts.path, parts.query)
    return f'{bare}{"&" if parts.query else "?"}sig={digest}'


def signed_request_ok(request: Request) -> bool:
    key = _key()
    if key is None:
        return False
    raw = request.url.query
    if raw.startswith('sig=') and '&' not in raw:
        sig, query = raw[4:], ''
    elif (idx := raw.rfind('&sig=')) >= 0:
        sig, query = raw[idx + 5 :], raw[:idx]
    else:
        return False
    return hmac.compare_digest(sig, _digest(key, request.url.path, query))
