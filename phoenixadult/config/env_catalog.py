from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

EnvVarKind = Literal['string', 'boolean', 'number', 'secret', 'bytes', 'enum', 'list']

# fmt: off
ENV_GROUP_ORDER = [
    'Matching & Title Parsing', 'Scraping & Pacing', 'HTTP Bypass', 'Web Search',
    'Data18 Enrichment', 'MetadataAPI', 'Manual NFO', 'People Cache & Sources',
    'Gender Handling', 'Images', 'Metadata Cache', 'Logging', 'Plex Server',
]

ENV_TABS: list[tuple[str, list[str]]] = [
    ('Matching', ['Matching & Title Parsing']),
    ('Scraping', ['Scraping & Pacing', 'HTTP Bypass', 'Web Search']),
    ('Enrichment', ['Data18 Enrichment', 'MetadataAPI', 'Manual NFO']),
    ('People', ['People Cache & Sources', 'Gender Handling']),
    ('Images', ['Images']),
    ('System', ['Metadata Cache', 'Logging']),
    ('Plex', ['Plex Server']),
]
GROUP_TAB = {group: tab for tab, tab_groups in ENV_TABS for group in tab_groups}

DEFAULT_SEARCH_TITLE_TRASH = [
    'RARBG', 'COM', r'\d{3,4}x\d{3,4}', 'HEVC', r'H\d{3}', 'AVC', r'\dK',
    r'\d{3,4}p', 'TOWN.AG_', 'MP4', 'KLEENEX', 'SD', 'HD',
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


ENV_CATALOG: list[EnvVarSpec] = [
    EnvVarSpec(
        'LOG_LEVEL',
        'Log Level',
        'Verbosity, least to most: error, warn, info, debug, http, verbose. HTTP access lines only appear at http or verbose.',
        'Logging',
        'enum',
        options=['error', 'warn', 'info', 'debug', 'http', 'verbose'],
        default_value='info',
        requires_restart=True,
    ),
    EnvVarSpec(
        'LOG_REDACT_HOSTS',
        'Redact the Server Host in Logs',
        'Public IP addresses are ALWAYS redacted in logs (a real routable address never appears). This flag '
        'additionally redacts the server’s own host/FQDN (from PHOENIX_BASE_URL) and private/LAN/loopback IPs — so '
        'with it OFF you can see your own LAN address (e.g. IMAGE_BASE_URL=localipv4) while testing. Secret query '
        'values are gated separately by LOG_REDACT_TOKEN. Defaults to ON when NODE_ENV=production and OFF otherwise.',
        'Logging',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'LOG_REDACT_TOKEN',
        'Redact Tokens in Logs',
        'Mask secret query values (?token=…, ?apikey=…, ?password=…) in logs. Defaults to ON when NODE_ENV=production '
        '(so tokens stay out of persisted logs) and OFF otherwise, so you can see the admin token in the startup '
        'banner URL while testing. IP addresses are always redacted regardless.',
        'Logging',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'IMAGE_DIR', 'Local Image Directory', 'Directory served back to Plex for local image files.', 'Images', 'string', default_value='./local/images'
    ),
    EnvVarSpec(
        'LOGO_CACHE_DIR',
        'Logo Cache Directory',
        'Folder holding logo.<site-slug>.<ext> clearLogo files (per-studio subfolders). Manage them at /logos '
        'and push them to Plex collections from the Plex tab.',
        'Images',
        'string',
        default_value='./local/images/logos',
    ),
    EnvVarSpec(
        'IMAGE_MAX_BYTES',
        'Max Image Size',
        'Hard ceiling on a single upstream image fetch — larger images are rejected. '
        'Accepts a plain byte count or a size like 20M, 2000K or 100B (M = MB, K = KB, B = bytes).',
        'Images',
        'bytes',
        default_value='20M',
    ),
    EnvVarSpec(
        'IMAGE_PROXY_PIN',
        'Pin Proxy Fetches to the Resolved IP',
        'SSRF hardening for /images/proxy: each hop is resolved once, validated public, and fetched by pinned IP '
        '(hostname kept in Host + TLS SNI). Turn off if a CDN rejects pinned fetches.',
        'Images',
        'boolean',
        default_value='true',
    ),
    EnvVarSpec(
        'MANUAL_NFO_PATH', 'Manual NFO Folder', 'Root folder served by the "Manual NFO" scraper.', 'Manual NFO', 'string', default_value='./local/manual'
    ),
    EnvVarSpec(
        'MANUAL_NFO_TOKEN',
        'Manual NFO Filename Prefix',
        'Leading filename token that pins a match request to the Manual NFO scraper.',
        'Manual NFO',
        'string',
        default_value='manual',
    ),
    EnvVarSpec(
        'PEOPLE_CACHE_DIR',
        'People Cache Directory',
        'On-disk cache for downloaded actor / director / producer headshots.',
        'People Cache & Sources',
        'string',
        default_value='./local/images/people',
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
        'When on, ignores existing cached photos and re-fetches every time.',
        'People Cache & Sources',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'METADATA_CACHE_ENABLE',
        'Snapshot Metadata Cache',
        'When on, each scraped scene’s metadata + images are snapshotted under the metadata '
        'cache dir and served cache-first on later requests — offline-safe protection against '
        'the source site going down or changing anti-scrape. Manage/purge at /metadata.',
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
        'When on (and people caching is enabled), cached headshots are face-detected '
        'and cropped to head + shoulders for Plex’s circular card. Requires '
        'opencv-python-headless (pip install "opencv-python-headless"); no-ops if absent. '
        'Generic/default placeholder images are never cropped. Review/undo crops at /people.',
        'People Cache & Sources',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'PEOPLE_SOURCE_ORDER',
        'People Source Order',
        'Priority order of headshot lookup sources. "Scene" is the actor image from the scene page itself — '
        'remove it to skip the scene image and use only the external sources, or drag it lower to prefer a '
        'provider over it. Drag to reorder; IAFD needs a bypass backend (Impersonate).',
        'People Cache & Sources',
        'list',
        options=[
            'Local Storage',
            'Scene',
            'IAFD',
            'AdultDVDEmpire',
            'Freeones',
            'Indexxx',
            'Boobpedia',
            'Babes and Stars',
            'Babepedia',
            'JAVBus',
            'JAVDatabase',
        ],
        default_value='Local Storage,Scene,IAFD,AdultDVDEmpire,Freeones,Indexxx,Boobpedia,Babes and Stars,Babepedia,JAVBus,JAVDatabase',
    ),
    EnvVarSpec(
        'IMAGE_BASE_URL',
        'Local Image Base Address',
        'Base URL Plex uses to fetch our locally-served images — actor/director/producer headshots and '
        'the clearLogos pushed to collections. Plex re-requests these periodically and does not keep them, '
        'so behind a Cloudflare tunnel the FQDN eventually dies and the images break — a stable local address '
        'is more durable. baseurl = the configured PHOENIX_BASE_URL (tunnel/FQDN); localhost = loopback (Plex '
        "on this same machine); localipv4/localipv6 = this machine's LAN address (Plex elsewhere on the "
        'network); or an explicit address like 192.0.2.10 or http://192.0.2.10:8080 to pin the interface when '
        'auto-detection picks the wrong one (e.g. a VPN owning the default route) — the scheme defaults to http '
        'and the configured PORT is appended when omitted. Metadata (poster/art) images always use baseurl. '
        'A metadata refresh in Plex is needed to pick up changed image URLs.',
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
        'When on, male actors are hidden from the served Plex cast list. Applied at serve time, '
        'so it also re-filters already-cached scenes (snapshots keep every actor on disk).',
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
        'Custom Search API key. With the CX set, Google CSE runs before the DuckDuckGo fallback.',
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
        'PLEX_URL',
        'Plex Server URL',
        'Base URL of the Plex server to reconcile against, e.g. http://plex.lan:32400. A LAN address is fine. '
        'Reconciliation is only available when this and PLEX_TOKEN are both set.',
        'Plex Server',
        'string',
    ),
    EnvVarSpec(
        'PLEX_TOKEN',
        'Plex Token',
        'X-Plex-Token for the server above. Needs library write access, so treat it like a password. '
        'Fetch one with the Plex tab\'s "Fetch New Token" button (plex.tv sign-in).',
        'Plex Server',
        'secret',
    ),
    EnvVarSpec(
        'PLEX_CLIENT_ID',
        'Plex Client Identifier',
        'Device identifier the fetched token is bound to; saved automatically by "Fetch New Token". Clear it together with the token to unlink this device.',
        'Plex Server',
        'secret',
    ),
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
        'Browser the Playwright bypass launches. On FreeBSD/linuxulator, Firefox is far more reliable than Chromium.',
        'HTTP Bypass',
        'enum',
        options=['chromium', 'firefox', 'webkit'],
        default_value='chromium',
    ),
    EnvVarSpec(
        'BYPASS_AUTO_RETRY',
        'Auto-Retry Every 4xx/5xx via Bypass',
        'When on, the base Client re-routes every failed scraper request (4xx/5xx) through the bypass chain.',
        'HTTP Bypass',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'BYPASS_TIMEOUT_MS',
        'Bypass Solve Timeout (ms)',
        'Per-attempt ceiling for FlareSolverr/Playwright challenge solves; an unsolvable site falls through to the next backend after this long.',
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
        'Minimum match accuracy (0-100). Lower = more matches but more false positives.',
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
        'METADATAAPI_TOKEN',
        'ThePornDB API Token',
        'Bearer token for api.theporndb.net. Optional — without it the API serves a reduced response.',
        'MetadataAPI',
        'secret',
    ),
    EnvVarSpec(
        'PHOENIX_EXTRA_COLLECTIONS',
        'Extra Collections',
        'Restore the optional extra-collections pass (studio / serie / movie titles) in GammaEntOther.',
        'Scraping & Pacing',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'STRIP_ENABLE',
        'Strip Junk Around the Title',
        'Enable the two strip-symbol rules below, which cut a junk prefix/suffix off the parsed title before searching.',
        'Matching & Title Parsing',
        'boolean',
        default_value='false',
    ),
    EnvVarSpec(
        'STRIP_SYMBOL',
        'Strip Symbol — Keep Text Before',
        'When strip is enabled and this symbol appears in the title, keep only the text BEFORE its first occurrence.',
        'Matching & Title Parsing',
        'string',
    ),
    EnvVarSpec(
        'STRIP_SYMBOL_REVERSE',
        'Strip Symbol — Keep Text After',
        'When strip is enabled and this symbol appears in the title, keep only the text AFTER its last occurrence.',
        'Matching & Title Parsing',
        'string',
    ),
    EnvVarSpec(
        'SEARCH_TITLE_TRASH',
        'Extra Search-Title Junk Tokens',
        'Additional whole-word release / scene-group tokens stripped from the parsed title, appended to the built-in list.',
        'Matching & Title Parsing',
        'list',
        default_value='',
    ),
    EnvVarSpec(
        'SCENE_GAP',
        'Paced Scrapers: Between-Scenes Delay',
        'Base seconds between units of work (searches AND scene scrapes share one track) on rate-limited scrapers '
        '(Nubiles, Naughty America); a 10-45s random jitter is always added on top, and at most 8 scenes run '
        'per 10 minutes regardless. Deferred work runs in the background (watch it at /queue); finished background '
        'searches persist to the search store so a later scan consumes them.',
        'Scraping & Pacing',
        'number',
        default_value='10',
        min=0,
        max=3600,
    ),
    EnvVarSpec(
        'REFRESH_FORCE_COUNT',
        'Refreshes Needed to Force a Refetch',
        'How many Plex refreshes of one scene within 60 seconds force a fresh scrape instead of the cached snapshot. Set 1 to refetch on every refresh.',
        'Scraping & Pacing',
        'number',
        default_value='3',
        min=1,
        max=10,
    ),
    EnvVarSpec(
        'SEARCH_STORE_TTL_DAYS',
        'Search Result Lifetime (Days)',
        'How long a cached search result stays valid before a later scan re-searches. 0 = perpetual '
        '(never expires) — the default, so matches survive indefinitely. Empty banned/no-result searches are '
        'never stored regardless.',
        'Scraping & Pacing',
        'number',
        default_value='0',
        min=0,
        max=3650,
    ),
    EnvVarSpec(
        'STATE_DB_PATH',
        'State Database Path',
        'SQLite database (WAL) holding queue replays, the search store, and — since the relational scene '
        'store — PRIMARY scene metadata. Do NOT delete. Keep it on storage only this process touches: '
        'a network mount or an SMB-exported path that another machine can open will corrupt WAL. The app '
        'backs it up and self-heals from those backups (below).',
        'Metadata Cache',
        'string',
        default_value='./local/phoenixadult.db',
        requires_restart=True,
    ),
    EnvVarSpec(
        'DB_BACKUP_INTERVAL_HOURS',
        'Database Backup Interval (Hours)',
        'How often the app writes a VACUUM INTO snapshot of the state database (no cron needed). 0 disables '
        'backups. On startup, if the live database fails its integrity check it is quarantined and the newest '
        'good snapshot is restored automatically.',
        'Metadata Cache',
        'number',
        default_value='24',
        min=0,
        max=8760,
    ),
    EnvVarSpec(
        'DB_BACKUP_KEEP',
        'Database Backups to Keep',
        'How many VACUUM INTO snapshots to retain; older ones are pruned after each backup.',
        'Metadata Cache',
        'number',
        default_value='7',
        min=1,
        max=365,
    ),
    EnvVarSpec(
        'DB_BACKUP_DIR',
        'Database Backup Directory',
        'Where VACUUM INTO snapshots are written. Blank uses a "backups" folder next to STATE_DB_PATH. '
        'A different local disk is safest, so a disk failure does not take the database and its backups together.',
        'Metadata Cache',
        'string',
        default_value='',
    ),
    EnvVarSpec(
        'SEARCH_STRIP_ACTORS',
        'Strip Actor Names — Sites',
        'Sites whose filenames lead with actor names: the names are dropped when building the site search, '
        'and title scoring uses the best of the stripped and unstripped title. Entries match a site, '
        'a studio, or a whole network (e.g. Nubiles). Type to search.',
        'Matching & Title Parsing',
        'list',
        default_value='',
    ),
    EnvVarSpec(
        'DISABLE_AUTO_MATCH',
        'Disable Automatic Matching',
        'When on, suppress every match request Plex did NOT flag as user-initiated (manual=1).',
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
