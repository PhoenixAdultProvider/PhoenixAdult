from __future__ import annotations

import json

from phoenixadult.utils.logging.logger import logger, verbose_enabled

_TAG = 'scrape-body'
_TEXTUAL = ('text/', 'application/json', 'application/xml', 'application/xhtml', 'application/javascript', '+json', '+xml')


def _clip(body: str) -> str:
    from phoenixadult.config.env import env

    cap = env.log_body_max_chars
    if cap <= 0 or len(body) <= cap:
        return body
    return f'{body[:cap]}\n[clipped — {len(body) - cap} more characters; raise LOG_BODY_MAX_CHARS or set it to 0 for the whole body]'


def is_textual(content_type: str) -> bool:
    kind = content_type.split(';')[0].strip().lower()
    return bool(kind) and any(marker in kind for marker in _TEXTUAL)


def _pretty(body: str, content_type: str) -> str:
    if 'json' not in content_type.lower():
        return body
    try:
        return json.dumps(json.loads(body), indent=2, sort_keys=True, ensure_ascii=False)
    except ValueError:
        return body


def trace_body(where: str, status: int | str, body: str, content_type: str = '') -> None:
    if not verbose_enabled() or not body:
        return
    rendered = _pretty(body, content_type)
    shape = content_type.split(';')[0].strip() or 'unknown type'
    logger.verbose(_TAG, f'{where} -> {status} {shape}, {len(body)} chars:\n{_clip(rendered)}')


def trace_payload(where: str, payload: object) -> None:
    if not verbose_enabled():
        return
    try:
        rendered = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        rendered = repr(payload)
    logger.verbose(_TAG, f'{where} -> parsed json, {len(rendered)} chars:\n{_clip(rendered)}')
