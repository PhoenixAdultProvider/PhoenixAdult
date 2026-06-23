from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

EnvVarKind = Literal['string', 'boolean', 'number', 'secret', 'bytes', 'enum', 'list']

# fmt: off
ENV_GROUP_ORDER = [
    'Logging', 'Images', 'Manual NFO', 'Actor cache & sources', 'Gender handling',
    'Web search', 'HTTP bypass', 'Data18 enrichment', 'MetadataAPI', 'Misc',
]

# Default whole-word junk tokens (regex fragments) stripped from a parsed search
# title. Ported verbatim from src/utils/processors/searchTitleTrash.ts.
DEFAULT_SEARCH_TITLE_TRASH = [
    'RARBG', 'COM', r'\d{3,4}x\d{3,4}', 'HEVC', r'H\d{3}', 'AVC', r'\dK',
    r'\d{3,4}p', 'TOWN.AG_', 'MP4', 'KLEENEX', 'SD', 'HD',
    'KTR', 'IEVA', 'WRB', 'NBQ', 'ForeverAloneDude', r'X\d{3}', 'SoSuMi',
    'sexors', 'gush', '3dh', 'lr', 'int', 'WEB', 'WEBRip', 'BluRay', 'BDRip',
    'HDRip', 'DVDRip', 'AAC', 'DDP', '10bit', 'HDR', 'REMUX', 'AV1',
]
# fmt: on

_DEFAULT_FEMALE_IMAGE = 'https://t3.ftcdn.net/jpg/00/97/03/72/360_F_97037264_ZZfCG8aa12o7NEZmnhVHGW49VOdfYcxy.jpg'
_DEFAULT_MALE_IMAGE = 'https://t3.ftcdn.net/jpg/01/13/46/18/240_F_113461869_W12s5AqhOOZF0YT3n3izlwQLzj82MGsj.jpg'


@dataclass(frozen=True)
class EnvVarSpec:
    key: str
    label: str
    description: str
    group: str
    kind: EnvVarKind
    default_value: str | None = None
    requires_restart: bool = False
    options: list[str] = field(default_factory=list)
    min: int | None = None
    max: int | None = None
    preview: Literal['image'] | None = None


ENV_CATALOG: list[EnvVarSpec] = [
    EnvVarSpec(
        'LOG_LEVEL',
        'Log level',
        'Verbosity of the agent log.',
        'Logging',
        'enum',
        options=['error', 'warn', 'info', 'http', 'verbose', 'debug'],
        default_value='info',
        requires_restart=True,
    ),
    EnvVarSpec(
        'LOG_REDACT_HOSTS',
        'Redact hosts, IPs & secrets in logs',
        'Replace URL hosts, IP addresses and secret query values (?token=…, ?apikey=…) in the log output with '
        '***REDACTED*** — keeps logs safe to paste into bug reports. Defaults to ON when NODE_ENV=production and '
        'OFF otherwise; set this to override either way.',
        'Logging',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'IMAGE_DIR', 'Local image directory', 'Directory served back to Plex for local image files.', 'Images', 'string', default_value='./local/images'
    ),
    EnvVarSpec(
        'IMAGE_MAX_BYTES',
        'Max image size',
        'Hard ceiling on a single upstream image fetch — larger images are rejected. '
        'Accepts a plain byte count or a size like 20M, 2000K or 100B (M = MB, K = KB, B = bytes).',
        'Images',
        'bytes',
        default_value='20M',
    ),
    EnvVarSpec(
        'MANUAL_NFO_PATH', 'Manual NFO folder', 'Root folder served by the "Manual NFO" scraper.', 'Manual NFO', 'string', default_value='./local/manual'
    ),
    EnvVarSpec(
        'MANUAL_NFO_TOKEN',
        'Manual NFO filename prefix',
        'Leading filename token that pins a match request to the Manual NFO scraper.',
        'Manual NFO',
        'string',
        default_value='manual',
    ),
    EnvVarSpec(
        'ACTOR_CACHE_DIR',
        'Actor cache directory',
        'On-disk cache for downloaded actor / director / producer headshots.',
        'Actor cache & sources',
        'string',
        default_value='./local/images/people',
    ),
    EnvVarSpec(
        'ACTOR_CACHE_ENABLE',
        'Enable actor cache',
        'When off, photo URLs are re-resolved on every scene refresh.',
        'Actor cache & sources',
        'boolean',
        default_value='true',
    ),
    EnvVarSpec(
        'ACTOR_CACHE_REPLACE_ENABLE',
        'Force re-fetch cached photos',
        'When on, ignores existing cached photos and re-fetches every time.',
        'Actor cache & sources',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'METADATA_CACHE_ENABLE',
        'Snapshot metadata cache',
        'When on, each scraped scene’s metadata + images are snapshotted under the metadata '
        'cache dir and served cache-first on later requests — offline-safe protection against '
        'the source site going down or changing anti-scrape. Manage/purge at /metadata-cache.',
        'Actor cache & sources',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'METADATA_CACHE_DIR',
        'Metadata cache directory',
        'On-disk location for metadata snapshots (text + images).',
        'Actor cache & sources',
        'string',
        default_value='./local/cache',
    ),
    EnvVarSpec(
        'ACTOR_CACHE_FACE_ENABLE',
        'Face-crop cached photos',
        'When on (and the actor cache is enabled), cached headshots are face-detected '
        'and cropped to head + shoulders for Plex’s circular card. Requires '
        'opencv-python-headless (pip install "opencv-python-headless"); no-ops if absent. '
        'Generic/default placeholder images are never cropped. Review/undo crops at /actor-cache.',
        'Actor cache & sources',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'ACTOR_SOURCE_ORDER',
        'Actor source order',
        'Priority order of actor-photo lookup sources. Drag to reorder; IAFD requires FlareSolverr.',
        'Actor cache & sources',
        'list',
        options=['Local Storage', 'AdultDVDEmpire', 'Freeones', 'IAFD', 'Indexxx', 'Boobpedia', 'Babes and Stars', 'Babepedia', 'JAVBus', 'JAVDatabase'],
        default_value='Local Storage,AdultDVDEmpire,Freeones,IAFD,Indexxx,Boobpedia,Babes and Stars,Babepedia',
    ),
    EnvVarSpec(
        'ADULT_EMPIRE_LOGIN_TOKEN', 'Adult Empire login token', 'Session token for the AdultDVDEmpire actor-photo source.', 'Actor cache & sources', 'secret'
    ),
    EnvVarSpec(
        'GENDER_DETECT_ENABLE',
        'Detect actor gender',
        'Query IAFD for each uncached actor and bake the gender into the cached filename.',
        'Gender handling',
        'boolean',
        default_value='true',
    ),
    EnvVarSpec(
        'GENDER_ENABLE',
        'Drop male actors',
        'When on, male actors are dropped from the Plex cast list entirely.',
        'Gender handling',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'GENERIC_IMAGE_ENABLE',
        'Generic placeholder photos',
        'Use a generic silhouette image when an actor has no resolvable photo.',
        'Gender handling',
        'boolean',
        default_value='true',
    ),
    EnvVarSpec(
        'GENERIC_FEMALE_URL',
        'Generic female photo URL',
        'Overrides the built-in female placeholder image.',
        'Gender handling',
        'string',
        default_value=_DEFAULT_FEMALE_IMAGE,
        preview='image',
    ),
    EnvVarSpec(
        'GENERIC_MALE_URL',
        'Generic male photo URL',
        'Overrides the built-in male placeholder image.',
        'Gender handling',
        'string',
        default_value=_DEFAULT_MALE_IMAGE,
        preview='image',
    ),
    EnvVarSpec(
        'GOOGLE_SEARCH_API_KEY',
        'Google CSE API key',
        'Custom Search API key. With the CX set, Google CSE runs before the DuckDuckGo fallback.',
        'Web search',
        'secret',
    ),
    EnvVarSpec('GOOGLE_SEARCH_CX', 'Google CSE engine ID', 'Programmable Search Engine ID (CX) paired with the API key above.', 'Web search', 'secret'),
    EnvVarSpec('FLARESOLVERR_URL', 'FlareSolverr endpoint', 'Self-hosted FlareSolverr URL used to bypass Cloudflare challenges.', 'HTTP bypass', 'string'),
    EnvVarSpec(
        'REQBIN_ENABLE',
        'Enable ReqBin fallback',
        'Use the third-party ReqBin service as an HTTP-bypass fallback.',
        'HTTP bypass',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec('REQBIN_API_KEY', 'ReqBin API key', 'API key for the ReqBin HTTP-bypass fallback.', 'HTTP bypass', 'secret'),
    EnvVarSpec(
        'BYPASS_ORDER',
        'Bypass attempt order',
        'Order of HTTP-bypass strategies to try. Drag to reorder.',
        'HTTP bypass',
        'list',
        options=['Impersonate', 'FlareSolverr', 'Playwright', 'ReqBin'],
        default_value='Impersonate,FlareSolverr,Playwright,ReqBin',
    ),
    EnvVarSpec(
        'BYPASS_AUTO_RETRY',
        'Auto-retry every 4xx/5xx via bypass',
        'When on, the base Client re-routes every failed scraper request (4xx/5xx) through the bypass chain.',
        'HTTP bypass',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'DATA18_ENABLE',
        'Enable Data18 enrichment',
        'Master on/off for data18.com image enrichment (per-site opt-in still required).',
        'Data18 enrichment',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'DATA18_ACCURACY',
        'Data18 match accuracy',
        'Minimum match accuracy (0-100). Lower = more matches but more false positives.',
        'Data18 enrichment',
        'number',
        min=0,
        max=100,
        default_value='100',
    ),
    EnvVarSpec(
        'DATA18_EXTRA',
        'Data18 extra galleries',
        'Include large/low-quality photoset (1001) and 1901 galleries.',
        'Data18 enrichment',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'METADATAAPI_TOKEN',
        'ThePornDB API token',
        'Bearer token for api.theporndb.net. Optional — without it the API serves a reduced response.',
        'MetadataAPI',
        'secret',
    ),
    EnvVarSpec(
        'PHOENIX_EXTRA_COLLECTIONS',
        'Extra collections',
        'Restore the optional extra-collections pass (studio / serie / movie titles) in GammaEntOther.',
        'Misc',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'STRIP_ENABLE',
        'Strip junk around the title',
        'Enable the two strip-symbol rules below, which cut a junk prefix/suffix off the parsed title before searching.',
        'Misc',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'STRIP_SYMBOL',
        'Strip symbol — keep text before',
        'When strip is enabled and this symbol appears in the title, keep only the text BEFORE its first occurrence.',
        'Misc',
        'string',
    ),
    EnvVarSpec(
        'STRIP_SYMBOL_REVERSE',
        'Strip symbol — keep text after',
        'When strip is enabled and this symbol appears in the title, keep only the text AFTER its last occurrence.',
        'Misc',
        'string',
    ),
    EnvVarSpec(
        'SEARCH_TITLE_TRASH',
        'Search-title junk tokens',
        'Whole-word release / scene-group tokens stripped from the parsed title before searching.',
        'Misc',
        'list',
        options=list(DEFAULT_SEARCH_TITLE_TRASH),
        default_value=','.join(DEFAULT_SEARCH_TITLE_TRASH),
    ),
    EnvVarSpec(
        'DISABLE_AUTO_MATCH',
        'Disable automatic matching',
        'When on, suppress every match request Plex did NOT flag as user-initiated (manual=1).',
        'Misc',
        'boolean',
        default_value='false',
    ),
]

_CATALOG_BY_KEY = {spec.key: spec for spec in ENV_CATALOG}


def find_env_var(key: str) -> EnvVarSpec | None:
    return _CATALOG_BY_KEY.get(key)


def is_editable_key(key: str) -> bool:
    return key in _CATALOG_BY_KEY


# ── Byte-size helpers ─────────────────────────────────────────────────────────

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


# ── Validation / normalization ────────────────────────────────────────────────


def normalize_env_value(spec: EnvVarSpec, raw: str) -> tuple[bool, str]:
    """Returns (ok, value_or_error)."""
    value = raw.strip()

    if spec.kind == 'boolean':
        if value not in ('true', 'false'):
            return False, f'{spec.key} must be On or Off'
        return True, value

    if spec.kind == 'number':
        if not re.match(r'^-?\d+$', value):
            return False, f'{spec.key} must be an integer'
        n = int(value)
        if spec.min is not None and n < spec.min:
            return False, f'{spec.key} must be ≥ {spec.min}'
        if spec.max is not None and n > spec.max:
            return False, f'{spec.key} must be ≤ {spec.max}'
        return True, str(n)

    if spec.kind == 'bytes':
        parsed = parse_bytes(value)
        if parsed is None:
            return False, f'{spec.key} must be a size like 20M, 2000K or 100B'
        return True, parsed

    if spec.kind == 'enum':
        if spec.options and value not in spec.options:
            return False, f'{spec.key} must be one of: {", ".join(spec.options)}'
        return True, value

    if spec.kind == 'list':
        items = [s.strip() for s in value.split(',') if s.strip()]
        return True, ','.join(items)

    return True, value
