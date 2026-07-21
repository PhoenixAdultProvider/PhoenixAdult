from __future__ import annotations

import time
import uuid
from typing import Any
from urllib.parse import quote

import httpx2

from app.config.env import env
from app.utils.http.client import make_http
from app.utils.logging.logger import logger

_PLEX_TV = 'https://plex.tv'
_PRODUCT = 'PhoenixAdult'
_UPDATE_TTL = 6 * 3600.0

_update_cache: tuple[float, dict[str, Any]] | None = None


def _headers(client_id: str, token: str | None = None) -> dict[str, str]:
    headers = {'X-Plex-Product': _PRODUCT, 'X-Plex-Client-Identifier': client_id, 'Accept': 'application/json'}
    if token:
        headers['X-Plex-Token'] = token
    return headers


def client_id_or_new() -> str:
    return env.plex_client_id or uuid.uuid4().hex


async def create_pin(client_id: str) -> dict[str, Any]:
    async with make_http(_headers(client_id), timeout=15.0) as http:
        res = await http.post(f'{_PLEX_TV}/api/v2/pins', params={'strong': 'true'})
        res.raise_for_status()
        pin = res.json()
    auth_url = 'https://app.plex.tv/auth#?clientID=' + quote(client_id) + '&code=' + quote(str(pin['code'])) + '&context%5Bdevice%5D%5Bproduct%5D=' + _PRODUCT
    return {'id': pin['id'], 'code': pin['code'], 'clientId': client_id, 'authUrl': auth_url}


async def check_pin(pin_id: int, client_id: str) -> str | None:
    async with make_http(_headers(client_id), timeout=15.0) as http:
        res = await http.get(f'{_PLEX_TV}/api/v2/pins/{pin_id}')
        res.raise_for_status()
        return res.json().get('authToken') or None


async def list_servers(token: str, client_id: str) -> list[dict[str, Any]]:
    async with make_http(_headers(client_id, token), timeout=20.0) as http:
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
    async with make_http({'Accept': 'application/json'}, timeout=15.0) as http:
        try:
            res = await http.get(f'{base}/identity')
            res.raise_for_status()
            container = res.json().get('MediaContainer') or {}
            identity = {'ok': True, 'machineIdentifier': container.get('machineIdentifier') or '', 'version': container.get('version') or ''}
        except (httpx2.HTTPError, ValueError) as err:
            identity['error'] = str(err)
        try:
            res = await http.get(f'{base}/library/sections', headers={'X-Plex-Token': token})
            res.raise_for_status()
            sections = (res.json().get('MediaContainer') or {}).get('Directory') or []
            auth = {'ok': True, 'sections': len(sections)}
        except (httpx2.HTTPError, ValueError) as err:
            auth['error'] = str(err)
    return {'identity': identity, 'auth': auth}


def _version_tuple(version: str) -> tuple[int, ...]:
    head = version.split('-')[0]
    try:
        return tuple(int(p) for p in head.split('.'))
    except ValueError:
        return (0,)


async def update_status(force: bool = False) -> dict[str, Any]:
    """Local-only Plex update check: current PMS version vs plex.tv downloads, TTL-cached."""
    global _update_cache
    now = time.monotonic()
    if not force and _update_cache and now - _update_cache[0] < _UPDATE_TTL:
        return _update_cache[1]

    if not (env.plex_url and env.plex_token):
        return {'error': 'Set PLEX_URL and PLEX_TOKEN first'}

    base = env.plex_url.rstrip('/')
    async with make_http({'Accept': 'application/json'}, timeout=20.0) as http:
        res = await http.get(f'{base}/', headers={'X-Plex-Token': env.plex_token})
        res.raise_for_status()
        container = res.json().get('MediaContainer') or {}
        current = container.get('version') or ''
        platform = container.get('platform') or ''

        res = await http.get(f'{_PLEX_TV}/api/downloads/5.json')
        res.raise_for_status()
        downloads = res.json()

    latest = ''
    for section in ('computer', 'nas'):
        for name, info in (downloads.get(section) or {}).items():
            if platform and name.lower() != platform.lower():
                continue
            candidate = str(info.get('version') or '')
            if _version_tuple(candidate) > _version_tuple(latest):
                latest = candidate
    if not latest:
        for section in ('computer', 'nas'):
            for info in (downloads.get(section) or {}).values():
                candidate = str(info.get('version') or '')
                if _version_tuple(candidate) > _version_tuple(latest):
                    latest = candidate

    result = {
        'current': current,
        'latest': latest,
        'platform': platform,
        'updateAvailable': bool(latest and _version_tuple(latest) > _version_tuple(current)),
        'checkedAt': time.time(),
    }
    _update_cache = (now, result)
    logger.info('plex-update', f'PMS {current} ({platform}) vs latest {latest}')
    return result
