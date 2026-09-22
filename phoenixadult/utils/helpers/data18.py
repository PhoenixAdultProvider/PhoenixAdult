from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict
from urllib.parse import urlsplit

from phoenixadult.models.scrape import SceneDetail
from phoenixadult.utils.helpers.helpers import slugify

DATA18_BASE = 'https://www.data18.com'

Data18Kind = Literal['scene', 'movie']


def data18_scene_id(raw: str | None) -> str:
    return raw if raw and raw.isdigit() and int(raw) > 100 else ''


class ManualMapping(TypedDict):
    slug: str | list[str]
    type: Data18Kind
    also: NotRequired[list[str]]


def _load_manual_mappings(caller_file: str = __file__) -> dict[str, ManualMapping]:
    folder = Path(caller_file).parent / '_data' / 'data18'
    merged: dict[str, ManualMapping] = {}
    for name in ['data18_manual_mappings', *sorted(p.stem for p in folder.glob('data18_manual_mappings_*.json'))]:
        path = folder / f'{name}.json'
        if path.exists():
            merged.update(json.loads(path.read_text(encoding='utf-8')))

    return merged


DATA18_MANUAL_MAPPINGS: dict[str, ManualMapping] = _load_manual_mappings()


def mapping_slug(title: str, sub_site: str | None, metadata: SceneDetail | None = None) -> str | None:
    sid = slugify(title, replacements=[("'", '')])
    if not sid:
        return None

    if not sub_site and metadata:
        sub_site = metadata.tagline or metadata.studio

    return f'{sid}-{re.sub(r"\W", "", sub_site).lower()}' if sub_site else sid


def manual_mapping_url(mapping_key: str | None) -> str | None:
    if not mapping_key:
        return None

    for d18, entry in DATA18_MANUAL_MAPPINGS.items():
        slug = entry['slug']
        if mapping_key == slug or (isinstance(slug, list) and mapping_key in slug):
            return f'{DATA18_BASE}/{"movies" if entry["type"] == "movie" else "scenes"}/{d18}'

    return None


def manual_mapping_extras(url: str | None) -> list[str]:
    ref = data18_ref(url)
    if not ref:
        return []
    entry = DATA18_MANUAL_MAPPINGS.get(ref['id'])
    if not entry:
        return []
    segment = 'movies' if entry['type'] == 'movie' else 'scenes'
    return [f'{DATA18_BASE}/{segment}/{extra}' for extra in entry.get('also', [])]


def data18_ref_with_extras(url: str | None) -> dict[str, Any] | None:
    ref: dict[str, Any] | None = data18_ref(url)
    if not ref:
        return None
    entry = DATA18_MANUAL_MAPPINGS.get(str(ref['id']))
    if entry and entry.get('also'):
        ref['also'] = list(entry['also'])
    return ref


def xp_ns(sel: Any, xpath: str) -> str:
    return (sel.xpath(f'normalize-space({xpath})').get() or '').strip()


def xp_first_ns(sel: Any, xpaths: tuple[str, ...]) -> str:
    for xpath in xpaths:
        if value := xp_ns(sel, xpath):
            return value

    return ''


def squash(value: str) -> str:
    return re.sub(r'\s+', '', value).lower()


def url_id(url: str) -> str:
    return re.sub(r'.*/', '', url).split('-')[0]


_DATA18_REF_RE = re.compile(r'/(scenes|movies)/(\d+)')


def data18_ref(url: str | None) -> dict[str, str] | None:
    if not url:
        return None

    m = _DATA18_REF_RE.search(url)
    if not m:
        return None

    return {'type': 'scene' if m.group(1) == 'scenes' else 'movie', 'id': m.group(2)}


_REPTYLE_SUFFIX_RE = re.compile(r'\s*-\s*Reptyle$', re.IGNORECASE)


def strip_reptyle_suffix(studio: str) -> str:
    return _REPTYLE_SUFFIX_RE.sub('', studio).strip()


_SCENE_REF_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*$')
DATA18_HOSTS = ('data18.com', 'www.data18.com')


def scene_url_from_ref(ref: str | None) -> str | None:
    if not ref:
        return None

    ref = ref.strip()
    if '://' in ref:
        parts = urlsplit(ref)
        if (parts.hostname or '').lower() not in DATA18_HOSTS:
            return None

        ref = parts.path

    ref = ref.strip('/')
    kind = 'scenes'
    if ref.lower() in ('scenes', 'movies'):
        return None

    if ref.lower().startswith('movies/'):
        kind, ref = 'movies', ref[len('movies/') :].strip('/')
    elif ref.lower().startswith('scenes/'):
        ref = ref[len('scenes/') :].strip('/')

    return f'{DATA18_BASE}/{kind}/{ref}' if _SCENE_REF_RE.match(ref) else None
