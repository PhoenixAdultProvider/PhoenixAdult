from __future__ import annotations

import base64
import hashlib
from urllib.parse import parse_qsl, urlsplit

# ── CurID Base64url Codec (no padding, matching Node Buffer base64url) ────────


def b64url_encode(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode('utf-8')).rstrip(b'=').decode('ascii')


def b64url_decode(s: str) -> str:
    pad = '=' * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode('ascii')).decode('utf-8')


def pack_cur_id(head: list[str]) -> str:
    return b64url_encode('|'.join(head))


_SUBSITE_SEP = '\x1f'


def embed_subsite(cur_id: str, subsite: str | None) -> str:
    if not subsite:
        return cur_id
    return b64url_encode(b64url_decode(cur_id) + _SUBSITE_SEP + subsite)


def split_subsite(decoded_cur_id: str) -> tuple[str, str | None]:
    payload, _, sub = decoded_cur_id.partition(_SUBSITE_SEP)
    return payload, sub or None


def unpack_cur_id(encoded: str) -> dict[str, str | None]:
    raw = b64url_decode(encoded)
    pipe = raw.find('|')
    if pipe < 0:
        return {'head': raw, 'tail': None}
    tail = raw[pipe + 1 :].strip()
    return {'head': raw[:pipe], 'tail': tail or None}


def hash_key(*parts: str, sep: str, length: int | None = None) -> str:
    digest = hashlib.sha1(sep.join(parts).encode('utf-8')).hexdigest()  # noqa: S324 - non-crypto key
    return digest[:length] if length else digest


def pad_jav_id(jav_id: str, ignore_labels: list[str]) -> str:
    label = jav_id.split('-')[0]
    num = '-'.join(jav_id.split('-')[1:])
    if len(num) >= 3 or any(item.lower() == label.lower() for item in ignore_labels):
        return jav_id
    return f'{label}-{num.zfill(3)}'


def same_scene(url: str | None) -> str:
    return (url or '').rstrip('/').casefold()


def scene_url_id(url: str | None) -> str:
    parts = urlsplit(url or '')
    for key, value in parse_qsl(parts.query):
        if key.casefold() == 'id' and value.isdigit():
            return value
    segments = [seg for seg in parts.path.split('/') if seg]
    return segments[-1] if segments and segments[-1].isdigit() else ''
