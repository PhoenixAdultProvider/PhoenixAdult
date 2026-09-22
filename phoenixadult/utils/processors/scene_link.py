from __future__ import annotations

import binascii
import json
import re
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

from phoenixadult.models.site_info import SiteInfo
from phoenixadult.utils.helpers.ids import b64url_decode, split_subsite

Kind = Literal['scene', 'listing', 'api', 'json']

_URL_RE = re.compile(r'^https?://', re.IGNORECASE)
_API_HOST_RE = re.compile(r'(^|[.-])api($|[.-])', re.IGNORECASE)
_JSON_URL_KEYS = ('movieURL', 'sceneURL', 'url')


@dataclass(frozen=True)
class SourceLink:
    kind: Kind | None = None
    url: str | None = None
    payload: Any | None = None


def is_api_url(url: str) -> bool:
    parts = urlsplit(url)
    return bool(_API_HOST_RE.search(parts.hostname or '')) or '/api/' in f'{parts.path}/' or '/graphql' in parts.path


def _fill(template: str, site: SiteInfo, head: str = '', blob_id: Any = None) -> str:
    url = template.replace('{base}', site.base_url.rstrip('/')).replace('{head}', head.lstrip('/'))
    return url.replace('{id}', str(blob_id)) if blob_id is not None else url


def _from_blob(blob: Any, site: SiteInfo | None) -> SourceLink:
    if isinstance(blob, dict):
        for key in _JSON_URL_KEYS:
            url = blob.get(key)
            if isinstance(url, str) and _URL_RE.match(url):
                return SourceLink('scene', url, blob)
        template = site.direct_url_template if site else None
        if site and template and '{id}' in template and blob.get('id') is not None:
            return SourceLink('scene', _fill(template, site, blob_id=blob['id']), blob)
    return SourceLink('json', None, blob)


def resolve_source_link(cur_id: str, site: SiteInfo | None) -> SourceLink:
    try:
        decoded = b64url_decode(cur_id)
    except (UnicodeDecodeError, binascii.Error, ValueError):
        return SourceLink()
    text, _ = split_subsite(decoded)
    if not text:
        return SourceLink()
    if text.lstrip()[:1] in '{[':
        try:
            return _from_blob(json.loads(text), site)
        except ValueError:
            pass
    segments = text.split('|')
    head = segments[0].strip()
    if _URL_RE.match(head):
        return SourceLink('api', head) if is_api_url(head) else SourceLink('scene', head)
    template = site.direct_url_template if site else None
    if site and template and '{id}' not in template and head:
        return SourceLink('scene', _fill(template, site, head))
    for segment in segments[1:]:
        if _URL_RE.match(segment.strip()):
            return SourceLink('listing', segment.strip())
    return SourceLink()
