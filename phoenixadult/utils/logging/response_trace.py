from __future__ import annotations

import json
from contextvars import ContextVar, Token
from dataclasses import dataclass

from phoenixadult.models.capture import RawCaptureEntry
from phoenixadult.utils.logging.logger import logger, verbose_enabled

_TAG = 'scrape-body'
_BINARY_PREFIXES = ('image/', 'video/', 'audio/', 'font/', 'model/')
_BINARY_TYPES = frozenset({'application/octet-stream', 'application/zip', 'application/gzip', 'application/x-gzip', 'application/pdf', 'application/wasm'})
MAX_TRACE_BYTES = 8 * 1024 * 1024
_sink: ContextVar[list[RawCaptureEntry] | None] = ContextVar('body_capture', default=None)


@dataclass
class BodyCapture:
    entries: list[RawCaptureEntry]
    _token: Token[list[RawCaptureEntry] | None]

    def end(self) -> list[RawCaptureEntry]:
        _sink.reset(self._token)
        return self.entries


def begin_body_capture(into: list[RawCaptureEntry] | None = None) -> BodyCapture:
    entries = into if into is not None else []
    return BodyCapture(entries=entries, _token=_sink.set(entries))


def capture_open() -> bool:
    return _sink.get() is not None


def tracing_wanted() -> bool:
    return verbose_enabled() or capture_open()


def _clip(body: str) -> str:
    from phoenixadult.config.env import env

    cap = env.log_body_max_chars
    if cap <= 0 or len(body) <= cap:
        return body
    return f'{body[:cap]}\n[clipped — {len(body) - cap} more characters; raise LOG_BODY_MAX_CHARS or set it to 0 for the whole body]'


def is_traceable(content_type: str) -> bool:
    kind = content_type.split(';')[0].strip().lower()
    return not kind.startswith(_BINARY_PREFIXES) and kind not in _BINARY_TYPES


def _is_json(content_type: str, body: str = '') -> bool:
    if content_type:
        return 'json' in content_type.lower()
    return body.lstrip()[:1] in ('{', '[')


def _pretty(body: str, content_type: str) -> str:
    if not _is_json(content_type, body):
        return body
    try:
        return json.dumps(json.loads(body), indent=2, sort_keys=True, ensure_ascii=False)
    except ValueError:
        return body


def _record(label: str, body: str, content_type: str) -> None:
    entries = _sink.get()
    if entries is not None:
        entries.append(RawCaptureEntry(label, 'json' if _is_json(content_type, body) else 'html', body))


def trace_body(where: str, status: int | str, body: str, content_type: str = '') -> None:
    if not tracing_wanted() or not body:
        return
    rendered = _pretty(body, content_type)
    _record(where, rendered, content_type)
    if not verbose_enabled():
        return
    shape = content_type.split(';')[0].strip() or 'unknown type'
    logger.verbose(_TAG, f'{where} -> {status} {shape}, {len(body)} chars:\n{_clip(rendered)}')


def trace_payload(where: str, payload: object) -> None:
    if not tracing_wanted():
        return
    try:
        rendered = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        rendered = repr(payload)
    _record(where, rendered, 'application/json')
    if not verbose_enabled():
        return
    logger.verbose(_TAG, f'{where} -> parsed json, {len(rendered)} chars:\n{_clip(rendered)}')
