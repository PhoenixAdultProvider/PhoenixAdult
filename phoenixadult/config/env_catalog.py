from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from phoenixadult.i18n import DEFAULT_LANGUAGE, LANGUAGES, N_, gettext

EnvVarKind = Literal['string', 'boolean', 'number', 'secret', 'bytes', 'enum', 'list']

# fmt: off
ENV_GROUP_ORDER = [
    'matching',
    'scraping',
    'http_bypass',
    'web_search',
    'data18',
    'manual_nfo',
    'people_cache',
    'gender',
    'images',
    'interface',
    'logging',
    'metadata_cache',
    'provider_access',
    'log_redaction',
]

ENV_TABS: list[tuple[str, list[str]]] = [
    ('matching', ['matching']),
    ('scraping', ['scraping', 'http_bypass', 'web_search']),
    ('enrichment', ['data18', 'manual_nfo']),
    ('people', ['people_cache', 'gender']),
    ('images', ['images']),
    ('system', ['interface', 'logging', 'metadata_cache', 'developer']),
    ('security', ['provider_access', 'log_redaction']),
]
GROUP_TAB = {group: tab for tab, tab_groups in ENV_TABS for group in tab_groups}
GROUP_TITLES = {
    'matching': N_('settings.group_matching'),
    'scraping': N_('settings.group_scraping'),
    'http_bypass': N_('settings.group_http_bypass'),
    'web_search': N_('settings.group_web_search'),
    'data18': N_('settings.group_data18'),
    'manual_nfo': N_('settings.group_manual_nfo'),
    'people_cache': N_('settings.group_people_cache'),
    'gender': N_('settings.group_gender'),
    'images': N_('settings.group_images'),
    'interface': N_('settings.group_interface'),
    'logging': N_('settings.group_logging'),
    'metadata_cache': N_('settings.group_metadata_cache'),
    'provider_access': N_('settings.group_provider_access'),
    'log_redaction': N_('settings.group_log_redaction'),
    'developer': N_('settings.group_developer'),
}
TAB_TITLES = {
    'matching': N_('settings.tab_matching'),
    'scraping': N_('settings.tab_scraping'),
    'enrichment': N_('settings.tab_enrichment'),
    'people': N_('settings.tab_people'),
    'images': N_('settings.tab_images'),
    'system': N_('settings.tab_system'),
    'security': N_('settings.tab_security'),
}

DEFAULT_SEARCH_TITLE_TRASH = [
    'RARBG', 'COM', r'\d{3,4}x\d{3,4}', 'HEVC', r'H\d{3}', 'AVC',
     r'[245678]K', r'\d{3,4}p', 'TOWN.AG_', 'MP4', 'KLEENEX', 'SD', 'HD',
    'KTR', 'IEVA', 'WRB', 'NBQ', 'ForeverAloneDude', r'X\d{3}', 'SoSuMi',
    'sexors', 'gush', '3dh', 'lr', 'int', 'WEBRip', 'BluRay', 'BDRip',
    'HDRip', 'DVDRip', 'AAC', 'DDP', '10bit', 'HDR', 'REMUX', 'AV1',
]
# fmt: on

DEFAULT_FEMALE_IMAGE_URL = 'https://t3.ftcdn.net/jpg/00/97/03/72/360_F_97037264_ZZfCG8aa12o7NEZmnhVHGW49VOdfYcxy.jpg'
DEFAULT_MALE_IMAGE_URL = 'https://t3.ftcdn.net/jpg/01/13/46/18/240_F_113461869_W12s5AqhOOZF0YT3n3izlwQLzj82MGsj.jpg'


@dataclass(frozen=True)
class EnvVarSpec:
    key: str
    group: str
    kind: EnvVarKind
    default_value: str | None = None
    requires_restart: bool = False
    options: list[str] = field(default_factory=list)
    min: int | None = None
    max: int | None = None
    preview: Literal['image'] | None = None
    secret_items: bool = False
    pattern_items: bool = False
    option_labels: dict[str, str] = field(default_factory=dict)

    def text_keys(self) -> tuple[str, str]:
        return f'settings.{self.key.lower()}.label', f'settings.{self.key.lower()}.description'


ENV_CATALOG: list[EnvVarSpec] = [
    EnvVarSpec('TOKEN_BASED_AUTH', 'provider_access', 'boolean', default_value='false'),
    EnvVarSpec('CLIENT_TOKEN_REQUIRED', 'provider_access', 'boolean', default_value='false'),
    EnvVarSpec('API_REQUESTS_PER_DAY', 'provider_access', 'number', default_value='0', min=0, max=1000000),
    EnvVarSpec('UI_LANGUAGE', 'interface', 'enum', options=list(LANGUAGES), option_labels=LANGUAGES, default_value=DEFAULT_LANGUAGE),
    EnvVarSpec('LOG_LEVEL', 'logging', 'enum', options=['error', 'warn', 'info', 'debug', 'http', 'verbose'], default_value='info', requires_restart=True),
    EnvVarSpec('HTTP_BODY_DUMP', 'logging', 'boolean', default_value='false'),
    EnvVarSpec('LOG_BODY_MAX_CHARS', 'logging', 'number', default_value='0', min=0, max=10000000),
    EnvVarSpec('LOG_REDACT_HOSTS', 'log_redaction', 'boolean', default_value='false'),
    EnvVarSpec('LOG_REDACT_TOKEN', 'log_redaction', 'boolean', default_value='false'),
    EnvVarSpec('IMAGE_DIR', 'images', 'string', default_value='./local/images'),
    EnvVarSpec('IMAGE_MAX_BYTES', 'images', 'bytes', default_value='20M'),
    EnvVarSpec('IMAGE_PROXY_PIN', 'images', 'boolean', default_value='true'),
    EnvVarSpec('IMAGE_GUARD_ENABLE', 'images', 'boolean', default_value='true'),
    EnvVarSpec('MANUAL_NFO_PATH', 'manual_nfo', 'string', default_value='./local/manual'),
    EnvVarSpec('MANUAL_NFO_TOKEN', 'manual_nfo', 'string', default_value='manual'),
    EnvVarSpec('DEV_UI_ENABLE', 'developer', 'boolean', default_value='false'),
    EnvVarSpec('PEOPLE_CACHE_ENABLE', 'people_cache', 'boolean', default_value='true'),
    EnvVarSpec('PEOPLE_CACHE_REPLACE_ENABLE', 'people_cache', 'boolean', default_value='false'),
    EnvVarSpec('METADATA_CACHE_ENABLE', 'metadata_cache', 'boolean', default_value='false'),
    EnvVarSpec('METADATA_CACHE_DIR', 'metadata_cache', 'string', default_value='./local/cache'),
    EnvVarSpec('PEOPLE_CACHE_FACE_ENABLE', 'people_cache', 'boolean', default_value='false'),
    EnvVarSpec(
        'PEOPLE_SOURCE_ORDER',
        'people_cache',
        'list',
        options=['Local Storage', 'Scene', 'IAFD', 'AdultDVDEmpire', 'Indexxx', 'Boobpedia', 'Babes and Stars', 'Babepedia', 'JAVDatabase'],
        default_value='Local Storage,Scene,IAFD,AdultDVDEmpire,Indexxx,Boobpedia,Babes and Stars,Babepedia',
    ),
    EnvVarSpec('IMAGE_BASE_URL', 'images', 'string', default_value='baseurl'),
    EnvVarSpec('ADULT_EMPIRE_LOGIN_TOKEN', 'people_cache', 'secret'),
    EnvVarSpec('GENDER_DETECT_ENABLE', 'gender', 'boolean', default_value='true'),
    EnvVarSpec('GENDER_SKIP_MALE_ENABLE', 'gender', 'boolean', default_value='false'),
    EnvVarSpec('GENERIC_IMAGE_ENABLE', 'gender', 'boolean', default_value='true'),
    EnvVarSpec('GENERIC_FEMALE_URL', 'gender', 'string', default_value=DEFAULT_FEMALE_IMAGE_URL, preview='image'),
    EnvVarSpec('GENERIC_MALE_URL', 'gender', 'string', default_value=DEFAULT_MALE_IMAGE_URL, preview='image'),
    EnvVarSpec('GOOGLE_SEARCH_API_KEY', 'web_search', 'secret'),
    EnvVarSpec('GOOGLE_SEARCH_CX', 'web_search', 'secret'),
    EnvVarSpec('FLARESOLVERR_URL', 'http_bypass', 'string'),
    EnvVarSpec('REQBIN_ENABLE', 'http_bypass', 'boolean', default_value='false'),
    EnvVarSpec('REQBIN_API_KEY', 'http_bypass', 'secret'),
    EnvVarSpec(
        'BYPASS_ORDER',
        'http_bypass',
        'list',
        options=['Impersonate', 'FlareSolverr', 'Playwright', 'ReqBin'],
        default_value='Impersonate,FlareSolverr,Playwright,ReqBin',
    ),
    EnvVarSpec('PLAYWRIGHT_BROWSER', 'http_bypass', 'enum', options=['chromium', 'firefox', 'webkit'], default_value='chromium'),
    EnvVarSpec('BYPASS_AUTO_RETRY', 'http_bypass', 'boolean', default_value='false'),
    EnvVarSpec('BYPASS_TIMEOUT_MS', 'http_bypass', 'number', min=1000, default_value='10000'),
    EnvVarSpec('DATA18_ENABLE', 'data18', 'boolean', default_value='false'),
    EnvVarSpec('DATA18_ACCURACY', 'data18', 'number', min=0, max=100, default_value='100'),
    EnvVarSpec('DATA18_EXTRA', 'data18', 'boolean', default_value='false'),
    EnvVarSpec('PHOENIX_EXTRA_COLLECTIONS', 'scraping', 'boolean', default_value='false'),
    EnvVarSpec('STRIP_ENABLE', 'matching', 'boolean', default_value='false'),
    EnvVarSpec('STRIP_SYMBOL', 'matching', 'string'),
    EnvVarSpec('STRIP_SYMBOL_REVERSE', 'matching', 'string'),
    EnvVarSpec('SEARCH_TITLE_TRASH', 'matching', 'list', default_value='', pattern_items=True),
    EnvVarSpec('SCENE_GAP', 'scraping', 'number', default_value='10', min=0, max=3600),
    EnvVarSpec('REFRESH_FORCE_COUNT', 'scraping', 'number', default_value='3', min=1, max=10),
    EnvVarSpec('SEARCH_STORE_TTL_DAYS', 'scraping', 'number', default_value='0', min=0, max=3650),
    EnvVarSpec('STATE_DB_PATH', 'metadata_cache', 'string', default_value='./local/phoenixadult.db', requires_restart=True),
    EnvVarSpec('DB_BACKUP_INTERVAL_HOURS', 'metadata_cache', 'number', default_value='24', min=0, max=8760),
    EnvVarSpec('DB_BACKUP_KEEP', 'metadata_cache', 'number', default_value='7', min=1, max=365),
    EnvVarSpec('DB_BACKUP_DIR', 'metadata_cache', 'string', default_value=''),
    EnvVarSpec('SEARCH_STRIP_ACTORS', 'matching', 'list', default_value=''),
    EnvVarSpec('DISABLE_AUTO_MATCH', 'matching', 'boolean', default_value='false'),
]

_CATALOG_BY_KEY = {spec.key: spec for spec in ENV_CATALOG}


def find_env_var(key: str) -> EnvVarSpec | None:
    return _CATALOG_BY_KEY.get(key)


def is_editable_key(key: str) -> bool:
    return key in _CATALOG_BY_KEY


# ── Byte-Size Helpers ─────────────────────────────────────────────────────────

_BYTE_UNITS = {'B': 1, 'K': 1024, 'M': 1024 * 1024}


def parse_bytes(raw: str) -> str | None:
    m = re.match(r'^(\d+)\s*([BKM])?$', raw.strip(), re.IGNORECASE)
    if not m:
        return None
    n = int(m.group(1))
    unit = (m.group(2) or 'B').upper()
    return str(n * _BYTE_UNITS[unit])


def humanize_bytes(raw: str | None) -> str:
    if not raw:
        return ''
    try:
        n = int(raw)
    except ValueError:
        return raw
    if str(n) != raw.strip() or n < 0:
        return raw
    if n != 0 and n % _BYTE_UNITS['M'] == 0:
        return f'{n // _BYTE_UNITS["M"]}M'
    if n != 0 and n % _BYTE_UNITS['K'] == 0:
        return f'{n // _BYTE_UNITS["K"]}K'
    return f'{n}B'


# ── Validation / Normalization ────────────────────────────────────────────────


_Verdict = tuple[bool, str]


def _normalize_boolean(spec: EnvVarSpec, value: str) -> _Verdict:
    if value not in ('true', 'false'):
        return False, gettext('settings_errors.boolean') % {'key': spec.key}
    return True, value


def _normalize_number(spec: EnvVarSpec, value: str) -> _Verdict:
    if not re.match(r'^-?\d+$', value):
        return False, gettext('settings_errors.integer') % {'key': spec.key}
    n = int(value)
    if spec.min is not None and n < spec.min:
        return False, gettext('settings_errors.minimum') % {'key': spec.key, 'min': spec.min}
    if spec.max is not None and n > spec.max:
        return False, gettext('settings_errors.maximum') % {'key': spec.key, 'max': spec.max}
    return True, str(n)


def _normalize_bytes(spec: EnvVarSpec, value: str) -> _Verdict:
    parsed = parse_bytes(value)
    if parsed is None:
        return False, gettext('settings_errors.bytes') % {'key': spec.key}
    return True, parsed


def _normalize_enum(spec: EnvVarSpec, value: str) -> _Verdict:
    if spec.options and value not in spec.options:
        return False, gettext('settings_errors.enum') % {'key': spec.key, 'options': ', '.join(spec.options)}
    return True, value


def _normalize_list(spec: EnvVarSpec, value: str) -> _Verdict:
    items = [s.strip() for s in value.split(',') if s.strip()]
    if not spec.pattern_items:
        return True, ','.join(items)
    for item in items:
        try:
            re.compile(item)
        except re.error as err:
            return False, gettext('settings_errors.pattern') % {'key': spec.key, 'item': repr(item), 'reason': err}
    return True, ','.join(items)


_NORMALIZERS: dict[str, Callable[[EnvVarSpec, str], _Verdict]] = {
    'boolean': _normalize_boolean,
    'number': _normalize_number,
    'bytes': _normalize_bytes,
    'enum': _normalize_enum,
    'list': _normalize_list,
}


def normalize_env_value(spec: EnvVarSpec, raw: str) -> _Verdict:
    normalize = _NORMALIZERS.get(spec.kind)
    value = raw.strip()
    return normalize(spec, value) if normalize else (True, value)
