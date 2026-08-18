from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote, urlsplit

from phoenixadult.config.env import env
from phoenixadult.registry import normalize_site_key
from phoenixadult.utils.helpers.helpers import slugify
from phoenixadult.utils.logging.logger import logger

EXT_CANDIDATES = ('.svg', '.png', '.webp', '.jpg')

PLACEHOLDERS: tuple[tuple[str, str], ...] = (
    ('{domain}', "the sub-site's own host, without www."),
    ('{subsiteclean}', 'sub-site name, letters and digits only'),
    ('{subsite-name}', 'sub-site name, hyphenated'),
    ('{subsite_name}', 'sub-site name, underscored'),
    ('{subsite}', 'sub-site name as written, URL-encoded'),
    ('{studioclean}', 'studio name, letters and digits only'),
    ('{studio-name}', 'studio name, hyphenated'),
    ('{studio_name}', 'studio name, underscored'),
    ('{studio}', 'studio name as written, URL-encoded'),
    ('{ext}', 'tries ' + ', '.join(EXT_CANDIDATES) + ' in turn'),
)

_TOKEN = re.compile(r'\{([^{}]*)\}')


def _host(base_url: str) -> str:
    host = (urlsplit(base_url).hostname or '') if base_url else ''
    return host[4:] if host.startswith('www.') else host


def _values(studio: str, subsite: str, base_url: str) -> dict[str, str]:
    return {
        'studioclean': normalize_site_key(studio),
        'subsiteclean': normalize_site_key(subsite),
        'studio-name': slugify(studio),
        'subsite-name': slugify(subsite),
        'studio_name': slugify(studio, separator='_'),
        'subsite_name': slugify(subsite, separator='_'),
        'studio': quote(studio),
        'subsite': quote(subsite),
        'domain': _host(base_url),
    }


def expand(template: str, studio: str, subsite: str, base_url: str = '') -> list[str]:
    values = _values(studio, subsite, base_url)
    unknown = sorted({name for name in _TOKEN.findall(template) if name != 'ext' and name not in values})
    if unknown:
        raise ValueError('unknown placeholder ' + ', '.join(f'{{{name}}}' for name in unknown))
    filled = _TOKEN.sub(lambda m: values.get(m.group(1), m.group(0)), template)
    if '{ext}' not in filled:
        return [filled]
    return [filled.replace('{ext}', ext) for ext in EXT_CANDIDATES]


def _store() -> Path:
    return Path(env.state_db_path).parent / 'logo-templates.json'


def templates() -> dict[str, str]:
    try:
        stored = json.loads(_store().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    if not isinstance(stored, dict):
        return {}
    return {str(key): value for key, value in stored.items() if isinstance(value, str) and value}


def remember(studio: str, template: str) -> None:
    if not studio or not template:
        return
    current = templates()
    if current.get(studio) == template:
        return
    current[studio] = template
    target = _store()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(current, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        tmp.replace(target)
    except OSError as err:
        logger.warn('logo-cache', f'could not persist the logo templates: {err}')
