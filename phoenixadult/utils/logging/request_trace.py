from __future__ import annotations

import json
from typing import Any

from fastapi import Request

from phoenixadult.config.env import env
from phoenixadult.utils.logging.logger import logger, verbose_enabled
from phoenixadult.utils.logging.redaction import MASK

_SECRET_HEADERS = frozenset({'authorization', 'cookie', 'proxy-authorization', 'set-cookie', 'x-api-key', 'x-plex-token'})


def _headers(request: Request) -> str:
    if env.log_redact_token:
        shown = {k: (MASK if k.lower() in _SECRET_HEADERS else v) for k, v in request.headers.items()}
    else:
        shown = dict(request.headers)
    return json.dumps(shown, indent=2, sort_keys=True)


def _where(request: Request) -> str:
    query = f'?{request.url.query}' if request.url.query else ''
    origin = request.client.host if request.client else 'an unknown address'
    return f'{request.method} {request.url.path}{query} from {origin}'


def trace_request(tag: str, request: Request) -> None:
    if not verbose_enabled():
        return
    logger.verbose(tag, f'{_where(request)} headers:\n{_headers(request)}')


def trace_body(tag: str, request: Request, body: Any) -> None:
    if not verbose_enabled():
        return
    logger.verbose(tag, f'{request.method} {request.url.path} body:\n' + json.dumps(body, indent=2, sort_keys=True, default=str))
