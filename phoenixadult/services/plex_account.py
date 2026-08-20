from __future__ import annotations

import time
import uuid
from typing import Any
from urllib.parse import quote

import httpx2

from phoenixadult.services.plex_connections import Connection
from phoenixadult.utils.http.client import make_http
from phoenixadult.utils.logging.logger import logger

_PLEX_TV = 'https://plex.tv'
_PRODUCT = 'PhoenixAdult'
_UPDATE_TTL = 6 * 3600.0
_PLATFORM_NAME_OVERRIDES = {'MacOSX': 'Mac'}

_update_cache: dict[int, tuple[float, tuple[str, str], dict[str, Any]]] = {}


def _headers(client_id: str, token: str | None = None) -> dict[str, str]:
    headers = {'X-Plex-Product': _PRODUCT, 'X-Plex-Client-Identifier': client_id, 'Accept': 'application/json'}
    if token:
        headers['X-Plex-Token'] = token
    return headers


def client_id_or_new(existing: str = '') -> str:
    return existing or uuid.uuid4().hex


async def create_pin(client_id: str) -> dict[str, Any]:
    async with make_http(_headers(client_id), timeout=15.0, verify=True) as http:
        res = await http.post(f'{_PLEX_TV}/api/v2/pins', params={'strong': 'true'})
        res.raise_for_status()
        pin = res.json()
    auth_url = 'https://app.plex.tv/auth#?clientID=' + quote(client_id) + '&code=' + quote(str(pin['code'])) + '&context%5Bdevice%5D%5Bproduct%5D=' + _PRODUCT
    return {'id': pin['id'], 'code': pin['code'], 'clientId': client_id, 'authUrl': auth_url}


async def check_pin(pin_id: int, client_id: str) -> str | None:
    async with make_http(_headers(client_id), timeout=15.0, verify=True) as http:
        res = await http.get(f'{_PLEX_TV}/api/v2/pins/{pin_id}')
        res.raise_for_status()
        return res.json().get('authToken') or None


async def list_servers(token: str, client_id: str) -> list[dict[str, Any]]:
    async with make_http(_headers(client_id, token), timeout=20.0, verify=True) as http:
        res = await http.get(f'{_PLEX_TV}/api/v2/resources', params={'includeHttps': '1', 'includeRelay': '0'})
        res.raise_for_status()
        resources = res.json()

    servers = []
    for r in resources if isinstance(resources, list) else []:
        if 'server' not in (r.get('provides') or ''):
            continue
        connections = [
            {'uri': c.get('uri') or '', 'address': c.get('address') or '', 'local': bool(c.get('local'))}
            for c in (r.get('connections') or [])
            if not c.get('relay')
        ]
        servers.append({'name': r.get('name') or '', 'product': r.get('product') or '', 'version': r.get('productVersion') or '', 'connections': connections})
    return servers


async def verify_server(url: str, token: str) -> dict[str, Any]:
    base = url.rstrip('/')
    identity: dict[str, Any] = {'ok': False}
    auth: dict[str, Any] = {'ok': False}
    async with make_http({'Accept': 'application/json'}, timeout=15.0, verify=True) as http:
        try:
            res = await http.get(f'{base}/identity')
            res.raise_for_status()
            container = res.json().get('MediaContainer') or {}
            identity = {'ok': True, 'machineIdentifier': container.get('machineIdentifier') or '', 'version': container.get('version') or ''}
        except (httpx2.HTTPError, ValueError) as err:
            logger.warn('plex-auth', f'verify identity failed for {base}: {err}')
            identity['error'] = 'Could not reach the server'
        try:
            res = await http.get(f'{base}/library/sections', headers={'X-Plex-Token': token})
            res.raise_for_status()
            sections = (res.json().get('MediaContainer') or {}).get('Directory') or []
            auth = {'ok': True, 'sections': len(sections)}
        except (httpx2.HTTPError, ValueError) as err:
            logger.warn('plex-auth', f'verify auth failed for {base}: {err}')
            auth['error'] = 'Server unreachable or token rejected'
    return {'identity': identity, 'auth': auth}


def _version_tuple(version: str) -> tuple[int, ...]:
    def to_int(part: str) -> int:
        try:
            return int(part)
        except ValueError:
            return 0

    return tuple(to_int(p) for p in version.replace('-', '.').split('.'))


async def _server_update_channel(http: httpx2.AsyncClient, base: str, token: str, channel: str) -> str:
    if channel != 'plex':
        return channel
    try:
        res = await http.get(f'{base}/:/prefs', headers={'X-Plex-Token': token})
        res.raise_for_status()
        settings = (res.json().get('MediaContainer') or {}).get('Setting') or []
        value = next((str(s.get('value')) for s in settings if s.get('id') == 'ButlerUpdateChannel'), '')
    except (httpx2.HTTPError, ValueError):
        value = ''
    return 'beta' if value == '8' else 'public'


async def update_status(connection: Connection, token: str, force: bool = False) -> dict[str, Any]:
    now = time.monotonic()
    config = (connection.update_channel, connection.update_release)
    cached = _update_cache.get(connection.id)
    if not force and cached and cached[1] == config and now - cached[0] < _UPDATE_TTL:
        return cached[2]

    if not (connection.server_url and token):
        return {'error': 'This connection needs a server URL and a token first'}

    base = connection.server_url.rstrip('/')
    async with make_http({'Accept': 'application/json'}, timeout=20.0, verify=True) as http:
        res = await http.get(f'{base}/', headers={'X-Plex-Token': token})
        res.raise_for_status()
        container = res.json().get('MediaContainer') or {}
        current = container.get('version') or ''
        platform = container.get('platform') or ''

        channel = await _server_update_channel(http, base, token, connection.update_channel)
        params = {'channel': 'plexpass'} if channel == 'beta' else {}
        res = await http.get(f'{_PLEX_TV}/api/downloads/5.json', params=params, headers={'X-Plex-Token': token})
        res.raise_for_status()
        downloads = res.json()

    available = {**(downloads.get('computer') or {}), **(downloads.get('nas') or {})}
    platform_name = _PLATFORM_NAME_OVERRIDES.get(platform, platform)
    info = next((v for k, v in available.items() if k.lower() == platform_name.lower()), None)
    if not info:
        logger.warn('plex-update', f'Could not match server platform: {platform_name}')
        return {'error': f'Could not match server platform: {platform_name}', 'current': current, 'platform': platform, 'channel': channel}

    releases = [r for r in (info.get('releases') or []) if isinstance(r, dict)]
    latest = str(info.get('version') or '')
    wanted = tuple(connection.update_release.split('|', 1)) if '|' in connection.update_release else None
    current_builds = [r for r in releases if latest and latest in str(r.get('url') or '')]
    release = next(
        (r for r in releases if wanted and r.get('distro') == wanted[0] and r.get('build') == wanted[1]),
        current_builds[0] if current_builds else (releases[0] if releases else {}),
    )
    result = {
        'current': current,
        'latest': latest,
        'platform': str(info.get('name') or platform),
        'serverPlatform': platform,
        'channel': channel,
        'updateAvailable': bool(latest and _version_tuple(latest) > _version_tuple(current)),
        'releaseDate': info.get('release_date'),
        'requirements': info.get('requirements'),
        'extraInfo': info.get('extra_info'),
        'changelogAdded': info.get('items_added'),
        'changelogFixed': info.get('items_fixed'),
        'label': release.get('label'),
        'distro': release.get('distro'),
        'build': release.get('build'),
        'downloadUrl': release.get('url'),
        'releases': [{'label': r.get('label'), 'distro': r.get('distro'), 'build': r.get('build')} for r in releases],
        'checkedAt': time.time(),
    }
    _update_cache[connection.id] = (now, config, result)
    logger.info('plex-update', f'PMS {current} ({platform}, {channel}) vs latest {latest}')
    return result
