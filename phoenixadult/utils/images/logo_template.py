from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote, urlsplit

from phoenixadult.config.env import env
from phoenixadult.i18n import N_, gettext
from phoenixadult.utils.helpers.text import slugify
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.processors.site_key import normalize_site_key

EXT_CANDIDATES = ('.svg', '.png', '.webp', '.jpg')

PLACEHOLDERS: tuple[tuple[str, str], ...] = (
    ('{domain}', N_('logo_add.token_domain')),
    ('{subsiteclean}', N_('logo_add.token_subsiteclean')),
    ('{subsite-name}', N_('logo_add.token_subsite_hyphen')),
    ('{subsite_name}', N_('logo_add.token_subsite_underscore')),
    ('{subsite}', N_('logo_add.token_subsite')),
    ('{studioclean}', N_('logo_add.token_studioclean')),
    ('{studio-name}', N_('logo_add.token_studio_hyphen')),
    ('{studio_name}', N_('logo_add.token_studio_underscore')),
    ('{studio}', N_('logo_add.token_studio')),
    ('{ext}', N_('logo_add.token_ext')),
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
        raise ValueError(gettext('logo_add.unknown_placeholder') % {'names': ', '.join(f'{{{name}}}' for name in unknown)})
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
