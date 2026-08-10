from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

EnvVarKind = Literal['string', 'boolean', 'number', 'secret', 'bytes', 'enum', 'list']

# fmt: off
ENV_GROUP_ORDER = [
    'Matching & Title Parsing', 'Scraping & Pacing', 'HTTP Bypass', 'Web Search',
    'Data18 Enrichment', 'Manual NFO', 'People Cache & Sources',
    'Gender Handling', 'Images', 'Logging', 'Metadata Cache', 'Provider Access', 'Log Redaction',
]

ENV_TABS: list[tuple[str, list[str]]] = [
    ('Matching', ['Matching & Title Parsing']),
    ('Scraping', ['Scraping & Pacing', 'HTTP Bypass', 'Web Search']),
    ('Enrichment', ['Data18 Enrichment', 'Manual NFO']),
    ('People', ['People Cache & Sources', 'Gender Handling']),
    ('Images', ['Images']),
    ('System', ['Logging', 'Metadata Cache']),
    ('Security', ['Provider Access', 'Log Redaction']),
]
GROUP_TAB = {group: tab for tab, tab_groups in ENV_TABS for group in tab_groups}

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
    secret_items: bool = False


ENV_CATALOG: list[EnvVarSpec] = [
    EnvVarSpec(
        'TOKEN_BASED_AUTH',
        'Require an API Key in the Provider URL',
        'When on, the provider mount answers only through its hook path. Register it in Plex as '
        'http://host:port/api/hook/YOUR_KEY/phoenixadult/movies. Generate keys on the Account page.',
        'Provider Access',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'CLIENT_TOKEN_REQUIRED',
        'Require a Registered Plex Client',
        'When on, match and metadata requests must carry an X-Plex-Client-Identifier listed under a Plex connection. '
        'The provider URL itself always answers, so Plex can add the provider at any time.',
        'Provider Access',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'API_REQUESTS_PER_DAY',
        'Daily Provider Request Limit',
        'Requests each Plex client and each API key may make to the provider per day. 0 means unlimited. Over the limit '
        'the provider answers 429 until midnight.',
        'Provider Access',
        'number',
        default_value='0',
        min=0,
        max=1000000,
    ),
    EnvVarSpec(
        'LOG_LEVEL',
        'Log Level',
        'Log Verbosity, least to most; HTTP access lines only appear at http or verbose.',
        'Logging',
        'enum',
        options=['error', 'warn', 'info', 'debug', 'http', 'verbose'],
        default_value='info',
        requires_restart=True,
    ),
    EnvVarSpec(
        'LOG_REDACT_HOSTS',
        'Redact Hosts and IPs in Logs',
        'Mask every IP address and the server’s own host in logs. A development-only switch: production always redacts and this setting disappears there.',
        'Log Redaction',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'LOG_REDACT_TOKEN',
        'Redact Tokens in Logs',
        'Mask credentials in logs: hook-path API keys (/api/hook/…), secret query values (?token=…, ?password=…), and '
        'credential headers in request dumps. A development-only switch: production always redacts and this setting '
        'disappears there.',
        'Log Redaction',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'IMAGE_DIR',
        'Local Image Directory',
        'Directory served back to Plex for local people and logo image files (people/ and logos/ subfolders).',
        'Images',
        'string',
        default_value='./local/images',
    ),
    EnvVarSpec(
        'IMAGE_MAX_BYTES',
        'Max Image Size',
        'Ceiling on a single upstream image fetch; accepts a byte count or a size like 20M, 2000K or 100B.',
        'Images',
        'bytes',
        default_value='20M',
    ),
    EnvVarSpec(
        'IMAGE_PROXY_PIN',
        'Pin Proxy Fetches to the Resolved IP',
        'SSRF hardening: /images/proxy fetches by pinned, validated-public IP; turn off if a CDN rejects it.',
        'Images',
        'boolean',
        default_value='true',
    ),
    EnvVarSpec(
        'IMAGE_GUARD_ENABLE',
        'Block Direct Image Browsing',
        'Serve images only to signed URLs, Plex, image fetchers, loopback, admin token, and the admin UIs — a typed-in URL gets a 403.',
        'Images',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'MANUAL_NFO_PATH', 'Manual NFO Folder', 'Root folder served by the "Manual NFO" scraper.', 'Manual NFO', 'string', default_value='./local/manual'
    ),
    EnvVarSpec(
        'MANUAL_NFO_TOKEN',
        'Manual NFO Filename Prefix',
        'Leading filename token that pins a match to the Manual NFO scraper.',
        'Manual NFO',
        'string',
        default_value='manual',
    ),
    EnvVarSpec(
        'PEOPLE_CACHE_ENABLE',
        'Enable People Cache',
        'When off, photo URLs are re-resolved on every scene refresh.',
        'People Cache & Sources',
        'boolean',
        default_value='true',
    ),
    EnvVarSpec(
        'PEOPLE_CACHE_REPLACE_ENABLE',
        'Force Re-Fetch Cached Photos',
        'Ignore existing cached photos and re-fetch every time.',
        'People Cache & Sources',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'METADATA_CACHE_ENABLE',
        'Snapshot Metadata Cache',
        'Snapshot each scraped scene’s metadata + images and serve them cache-first; manage at /metadata.',
        'Metadata Cache',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'METADATA_CACHE_DIR',
        'Metadata Cache Directory',
        'On-disk location for metadata snapshots (text + images).',
        'Metadata Cache',
        'string',
        default_value='./local/cache',
    ),
    EnvVarSpec(
        'PEOPLE_CACHE_FACE_ENABLE',
        'Face-Crop Cached Photos',
        'Crop cached headshots to head + shoulders (needs opencv-python-headless); review/undo at /people.',
        'People Cache & Sources',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'PEOPLE_SOURCE_ORDER',
        'People Source Order',
        'Headshot lookup priority — drag to reorder; "Scene" is the scene-page image, IAFD needs the Impersonate bypass.',
        'People Cache & Sources',
        'list',
        options=[
            'Local Storage',
            'Scene',
            'IAFD',
            'AdultDVDEmpire',
            'Indexxx',
            'Boobpedia',
            'Babes and Stars',
            'Babepedia',
            'JAVDatabase',
        ],
        default_value='Local Storage,Scene,IAFD,AdultDVDEmpire,Indexxx,Boobpedia,Babes and Stars,Babepedia',
    ),
    EnvVarSpec(
        'IMAGE_BASE_URL',
        'Local Image Base Address',
        'Base URL Plex fetches headshots/logos from: baseurl (PHOENIX_BASE_URL), localhost, localipv4, '
        'localipv6, or an explicit address like http://192.0.2.10:8080.',
        'Images',
        'string',
        default_value='baseurl',
    ),
    EnvVarSpec(
        'ADULT_EMPIRE_LOGIN_TOKEN', 'Adult Empire Login Token', 'Session token for the AdultDVDEmpire actor-photo source.', 'People Cache & Sources', 'secret'
    ),
    EnvVarSpec(
        'GENDER_DETECT_ENABLE',
        'Detect Actor Gender',
        'Query IAFD for each uncached actor and bake the gender into the cached filename.',
        'Gender Handling',
        'boolean',
        default_value='true',
    ),
    EnvVarSpec(
        'GENDER_SKIP_MALE_ENABLE',
        'Drop Male Actors',
        'Hide male actors from the served Plex cast list (applied at serve time, so cached scenes re-filter too).',
        'Gender Handling',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'GENERIC_IMAGE_ENABLE',
        'Generic Placeholder Photos',
        'Use a generic silhouette image when an actor has no resolvable photo.',
        'Gender Handling',
        'boolean',
        default_value='true',
    ),
    EnvVarSpec(
        'GENERIC_FEMALE_URL',
        'Generic Female Photo URL',
        'Overrides the built-in female placeholder image.',
        'Gender Handling',
        'string',
        default_value=DEFAULT_FEMALE_IMAGE_URL,
        preview='image',
    ),
    EnvVarSpec(
        'GENERIC_MALE_URL',
        'Generic Male Photo URL',
        'Overrides the built-in male placeholder image.',
        'Gender Handling',
        'string',
        default_value=DEFAULT_MALE_IMAGE_URL,
        preview='image',
    ),
    EnvVarSpec(
        'GOOGLE_SEARCH_API_KEY',
        'Google CSE API Key',
        'Custom Search API key; with the CX set, Google CSE runs before the DuckDuckGo fallback.',
        'Web Search',
        'secret',
    ),
    EnvVarSpec('GOOGLE_SEARCH_CX', 'Google CSE Engine ID', 'Programmable Search Engine ID (CX) paired with the API key above.', 'Web Search', 'secret'),
    EnvVarSpec('FLARESOLVERR_URL', 'FlareSolverr Endpoint', 'Self-hosted FlareSolverr URL used to bypass Cloudflare challenges.', 'HTTP Bypass', 'string'),
    EnvVarSpec(
        'REQBIN_ENABLE',
        'Enable ReqBin Fallback',
        'Use the third-party ReqBin service as an HTTP-bypass fallback.',
        'HTTP Bypass',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec('REQBIN_API_KEY', 'ReqBin API Key', 'API key for the ReqBin HTTP-bypass fallback.', 'HTTP Bypass', 'secret'),
    EnvVarSpec(
        'BYPASS_ORDER',
        'Bypass Attempt Order',
        'Order of HTTP-bypass strategies to try. Drag to reorder.',
        'HTTP Bypass',
        'list',
        options=['Impersonate', 'FlareSolverr', 'Playwright', 'ReqBin'],
        default_value='Impersonate,FlareSolverr,Playwright,ReqBin',
    ),
    EnvVarSpec(
        'PLAYWRIGHT_BROWSER',
        'Playwright Browser Engine',
        'Browser the Playwright bypass launches; on FreeBSD/linuxulator, Firefox is the most reliable.',
        'HTTP Bypass',
        'enum',
        options=['chromium', 'firefox', 'webkit'],
        default_value='chromium',
    ),
    EnvVarSpec(
        'BYPASS_AUTO_RETRY',
        'Auto-Retry Every 4xx/5xx via Bypass',
        'Re-route every failed scraper request (4xx/5xx) through the bypass chain.',
        'HTTP Bypass',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'BYPASS_TIMEOUT_MS',
        'Bypass Solve Timeout (ms)',
        'Per-attempt ceiling for a challenge solve before falling through to the next backend.',
        'HTTP Bypass',
        'number',
        min=1000,
        default_value='10000',
    ),
    EnvVarSpec(
        'DATA18_ENABLE',
        'Enable Data18 Enrichment',
        'Master on/off for data18.com image enrichment (per-site opt-in still required).',
        'Data18 Enrichment',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'DATA18_ACCURACY',
        'Data18 Match Accuracy',
        'Minimum match accuracy (0-100); lower = more matches but more false positives.',
        'Data18 Enrichment',
        'number',
        min=0,
        max=100,
        default_value='100',
    ),
    EnvVarSpec(
        'DATA18_EXTRA',
        'Data18 Extra Galleries',
        'Include large/low-quality photoset (1001) and 1901 galleries.',
        'Data18 Enrichment',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'PHOENIX_EXTRA_COLLECTIONS',
        'Extra Collections',
        'Restore the extra-collections pass (studio / serie / movie titles) in GammaEntOther.',
        'Scraping & Pacing',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'STRIP_ENABLE',
        'Strip Junk Around the Title',
        'Enable the two strip-symbol rules below.',
        'Matching & Title Parsing',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'STRIP_SYMBOL',
        'Strip Symbol — Keep Text Before',
        'Keep only the text BEFORE this symbol’s first occurrence in the parsed title.',
        'Matching & Title Parsing',
        'string',
    ),
    EnvVarSpec(
        'STRIP_SYMBOL_REVERSE',
        'Strip Symbol — Keep Text After',
        'Keep only the text AFTER this symbol’s last occurrence in the parsed title.',
        'Matching & Title Parsing',
        'string',
    ),
    EnvVarSpec(
        'SEARCH_TITLE_TRASH',
        'Extra Search-Title Junk Tokens',
        'Extra whole-word junk tokens stripped from the parsed title, appended to the built-in list.',
        'Matching & Title Parsing',
        'list',
        default_value='',
    ),
    EnvVarSpec(
        'SCENE_GAP',
        'Paced Scrapers: Between-Scenes Delay',
        'Base seconds between units of work on rate-limited scrapers (10-45s jitter added on top); deferred work runs at /queue.',
        'Scraping & Pacing',
        'number',
        default_value='10',
        min=0,
        max=3600,
    ),
    EnvVarSpec(
        'REFRESH_FORCE_COUNT',
        'Refreshes Needed to Force a Refetch',
        'Plex refreshes of one scene within 60 seconds that force a fresh scrape (1 = refetch every refresh).',
        'Scraping & Pacing',
        'number',
        default_value='3',
        min=1,
        max=10,
    ),
    EnvVarSpec(
        'SEARCH_STORE_TTL_DAYS',
        'Search Result Lifetime (Days)',
        'Days a cached search result stays valid before a later scan re-searches; 0 = never expires.',
        'Scraping & Pacing',
        'number',
        default_value='0',
        min=0,
        max=3650,
    ),
    EnvVarSpec(
        'STATE_DB_PATH',
        'Database Path',
        'SQLite database holding queues, the search store, and PRIMARY scene metadata — do NOT delete or put on a network mount.',
        'Metadata Cache',
        'string',
        default_value='./local/phoenixadult.db',
        requires_restart=True,
    ),
    EnvVarSpec(
        'DB_BACKUP_INTERVAL_HOURS',
        'Database Backup Interval (Hours)',
        'Hours between database backup snapshots (0 disables); a corrupt database auto-restores from the newest good one.',
        'Metadata Cache',
        'number',
        default_value='24',
        min=0,
        max=8760,
    ),
    EnvVarSpec(
        'DB_BACKUP_KEEP',
        'Database Backups to Keep',
        'Backup snapshots to retain; older ones are pruned after each backup.',
        'Metadata Cache',
        'number',
        default_value='7',
        min=1,
        max=365,
    ),
    EnvVarSpec(
        'DB_BACKUP_DIR',
        'Database Backup Directory',
        'Where backup snapshots are written; blank = a "backups" folder next to the database (a separate disk is safest).',
        'Metadata Cache',
        'string',
        default_value='',
    ),
    EnvVarSpec(
        'SEARCH_STRIP_ACTORS',
        'Strip Actor Names — Sites',
        'Sites/studios/networks whose filenames lead with actor names — the names are dropped from the site search.',
        'Matching & Title Parsing',
        'list',
        default_value='',
    ),
    EnvVarSpec(
        'DISABLE_AUTO_MATCH',
        'Disable Automatic Matching',
        'Suppress every match request Plex did NOT flag as user-initiated (manual=1).',
        'Matching & Title Parsing',
        'boolean',
        default_value='false',
    ),
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


def normalize_env_value(spec: EnvVarSpec, raw: str) -> tuple[bool, str]:
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
