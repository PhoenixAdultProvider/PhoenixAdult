from __future__ import annotations

import hashlib
import itertools
import json
import re
from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from phoenixadult.models.capture import RawCaptureEntry
from phoenixadult.utils.logging.logger import logger, verbose_enabled

_TAG = 'scrape-body'
_BINARY_PREFIXES = ('image/', 'video/', 'audio/', 'font/', 'model/')
_BINARY_TYPES = frozenset({'application/octet-stream', 'application/zip', 'application/gzip', 'application/x-gzip', 'application/pdf', 'application/wasm'})
MAX_TRACE_BYTES = 8 * 1024 * 1024
TRACED = 'pa_body_traced'
DUMP_KEEP = 300
_NL = chr(10)
_seq = itertools.count(1)
_UNSAFE = re.compile(r'[^A-Za-z0-9._-]+')
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
    tail = f'[clipped — {len(body) - cap} more characters; the file holds all of it]'
    return body[:cap] + _NL + tail


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


def dump_dir() -> Path:
    from phoenixadult.config.env import env

    return Path(env.log_dir) / 'dumps'


def _extension(content_type: str, body: str) -> str:
    if _is_json(content_type, body):
        return 'json'
    kind = content_type.split(';')[0].strip().lower()
    return 'html' if 'html' in kind or body.lstrip()[:1] == '<' else 'txt'


def _prune(root: Path) -> None:
    keep = sorted(root.glob('*.*'), key=lambda f: f.stat().st_mtime, reverse=True)
    for stale in keep[DUMP_KEEP:]:
        stale.unlink(missing_ok=True)


def write_dump(where: str, body: str, content_type: str) -> str:
    root = dump_dir()
    stem = _UNSAFE.sub('-', where.replace('https://', '').replace('http://', '')).strip('-')[:90]
    name = f'{next(_seq):04d}-{stem}-{hashlib.sha1(where.encode()).hexdigest()[:6]}.{_extension(content_type, body)}'
    try:
        root.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(body, encoding='utf-8', errors='replace')
        _prune(root)
    except OSError as err:
        logger.warn(_TAG, f'could not write the body dump for {where}: {err}')
        return ''
    return str(root / name)


def trace_body(where: str, status: int | str, body: str, content_type: str = '') -> None:
    if not tracing_wanted():
        return
    if not body:
        logger.debug(f'[{_TAG}] {where} -> {status} carried an empty body, nothing to dump')
        return
    rendered = _pretty(body, content_type)
    _record(where, rendered, content_type)
    shape = content_type.split(';')[0].strip() or 'unknown type'
    saved = write_dump(where, rendered, content_type)
    if saved:
        logger.info(_TAG, f'{where} -> {status} {shape}, {len(body)} chars -> {saved}')
    if verbose_enabled():
        logger.verbose(_TAG, f'{where} -> {status} {shape}, {len(body)} chars:' + _NL + _clip(rendered))


def trace_payload(where: str, payload: object) -> None:
    if not tracing_wanted():
        return
    try:
        rendered = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        rendered = repr(payload)
    _record(where, rendered, 'application/json')
    saved = write_dump(where, rendered, 'application/json')
    if saved:
        logger.info(_TAG, f'{where} -> parsed json, {len(rendered)} chars -> {saved}')
    if verbose_enabled():
        logger.verbose(_TAG, f'{where} -> parsed json, {len(rendered)} chars:' + _NL + _clip(rendered))


def trace_response(response: Any) -> None:
    if not tracing_wanted():
        return
    where = f'{response.request.method} {response.url}'
    if response.extensions.get(TRACED):
        logger.debug(f'[{_TAG}] {where} was already dumped by the transport hook')
        return
    content_type = response.headers.get('content-type', '')
    if not is_traceable(content_type):
        logger.debug(f'[{_TAG}] {where} skipped: {content_type or "untyped"} is binary')
        return
    response.extensions[TRACED] = True
    try:
        body = response.text
    except Exception as err:  # noqa: BLE001 - a body we cannot decode is not worth failing the request over
        logger.warn(_TAG, f'{where} body could not be decoded for the dump: {err!r}')
        return
    if len(body) > MAX_TRACE_BYTES:
        logger.debug(f'[{_TAG}] {where} skipped: {len(body)} chars of {content_type or "untyped"} exceeds the trace ceiling')
        return
    trace_body(where, response.status_code, body, content_type)
