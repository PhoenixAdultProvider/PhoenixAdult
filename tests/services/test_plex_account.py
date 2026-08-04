from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from phoenixadult.services import plex_account
from tests.conftest import seed_connection

BASE = 'http://192.0.2.10:32400'


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    plex_account._update_cache.clear()


@pytest.fixture
def connection() -> Any:
    return seed_connection(url=BASE, token='tok')


def test_client_id_keeps_an_existing_value() -> None:
    assert plex_account.client_id_or_new('fixed-id') == 'fixed-id'
    generated = plex_account.client_id_or_new()
    assert generated and generated != plex_account.client_id_or_new()


@respx.mock
async def test_create_and_poll_pin() -> None:
    respx.post('https://plex.tv/api/v2/pins').mock(return_value=httpx.Response(201, json={'id': 123, 'code': 'abcd', 'authToken': None}))
    pin = await plex_account.create_pin('cid-1')
    assert pin['id'] == 123 and pin['clientId'] == 'cid-1'
    assert 'app.plex.tv/auth' in pin['authUrl'] and 'code=abcd' in pin['authUrl']

    respx.get('https://plex.tv/api/v2/pins/123').mock(return_value=httpx.Response(200, json={'id': 123, 'authToken': 'tok-9'}))
    assert await plex_account.check_pin(123, 'cid-1') == 'tok-9'


@respx.mock
async def test_list_servers_filters_relay_and_non_servers() -> None:
    respx.get(url__startswith='https://plex.tv/api/v2/resources').mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    'name': 'Home PMS',
                    'product': 'Plex Media Server',
                    'productVersion': '1.41.0',
                    'provides': 'server',
                    'connections': [
                        {'uri': f'{BASE}', 'address': '192.0.2.10', 'local': True, 'relay': False},
                        {'uri': 'https://relay.example', 'address': '', 'local': False, 'relay': True},
                    ],
                },
                {'name': 'Player', 'provides': 'client', 'connections': []},
            ],
        )
    )
    servers = await plex_account.list_servers('tok', 'cid')
    assert len(servers) == 1
    assert servers[0]['name'] == 'Home PMS'
    assert servers[0]['connections'] == [{'uri': BASE, 'address': '192.0.2.10', 'local': True}]


@respx.mock
async def test_verify_server_reports_identity_and_auth() -> None:
    respx.get(f'{BASE}/identity').mock(return_value=httpx.Response(200, json={'MediaContainer': {'machineIdentifier': 'm-1', 'version': '1.41.0'}}))
    respx.get(f'{BASE}/library/sections').mock(return_value=httpx.Response(200, json={'MediaContainer': {'Directory': [{'key': '1'}, {'key': '2'}]}}))
    result = await plex_account.verify_server(BASE, 'tok')
    assert result['identity'] == {'ok': True, 'machineIdentifier': 'm-1', 'version': '1.41.0'}
    assert result['auth'] == {'ok': True, 'sections': 2}


@respx.mock
async def test_verify_server_flags_bad_token() -> None:
    respx.get(f'{BASE}/identity').mock(return_value=httpx.Response(200, json={'MediaContainer': {'machineIdentifier': 'm-1', 'version': '1.41.0'}}))
    respx.get(f'{BASE}/library/sections').mock(return_value=httpx.Response(401))
    result = await plex_account.verify_server(BASE, 'bad')
    assert result['identity']['ok'] is True
    assert result['auth']['ok'] is False


def _mock_prefs(channel_value: str = '0') -> None:
    respx.get(f'{BASE}/:/prefs').mock(
        return_value=httpx.Response(200, json={'MediaContainer': {'Setting': [{'id': 'ButlerUpdateChannel', 'value': channel_value}]}})
    )


@respx.mock
async def test_update_status_compares_platform_versions(monkeypatch: pytest.MonkeyPatch, connection: Any) -> None:
    respx.get(f'{BASE}/').mock(return_value=httpx.Response(200, json={'MediaContainer': {'version': '1.41.0.100-abc', 'platform': 'FreeBSD'}}))
    _mock_prefs()
    respx.get('https://plex.tv/api/downloads/5.json').mock(
        return_value=httpx.Response(
            200,
            json={
                'computer': {'Linux': {'version': '1.42.0.200-xyz'}},
                'nas': {'FreeBSD': {'version': '1.41.5.150-fbd'}},
            },
        )
    )
    result = await plex_account.update_status(connection, 'tok', force=True)
    assert result['current'] == '1.41.0.100-abc'
    assert result['latest'] == '1.41.5.150-fbd'
    assert result['channel'] == 'public'
    assert result['updateAvailable'] is True

    respx.get(f'{BASE}/').mock(return_value=httpx.Response(500))
    cached = await plex_account.update_status(connection, 'tok')
    assert cached == result


@respx.mock
async def test_update_status_server_beta_pref_uses_plexpass_channel(monkeypatch: pytest.MonkeyPatch, connection: Any) -> None:
    respx.get(f'{BASE}/').mock(return_value=httpx.Response(200, json={'MediaContainer': {'version': '1.41.0', 'platform': 'Windows'}}))
    _mock_prefs('8')
    beta = respx.get('https://plex.tv/api/downloads/5.json', params={'channel': 'plexpass'}).mock(
        return_value=httpx.Response(200, json={'computer': {'Windows': {'version': '1.42.0', 'releases': [{'label': 'x64', 'url': 'https://d/x64.exe'}]}}})
    )
    result = await plex_account.update_status(connection, 'tok', force=True)
    assert beta.called
    assert result['channel'] == 'beta'
    assert result['downloadUrl'] == 'https://d/x64.exe'


@respx.mock
async def test_update_status_explicit_channel_skips_server_pref() -> None:
    connection = seed_connection(name='public-channel', url=BASE, token='tok', updateChannel='public')
    respx.get(f'{BASE}/').mock(return_value=httpx.Response(200, json={'MediaContainer': {'version': '1.41.0', 'platform': 'MacOSX'}}))
    respx.get('https://plex.tv/api/downloads/5.json').mock(return_value=httpx.Response(200, json={'computer': {'Mac': {'version': '1.40.0'}}}))
    result = await plex_account.update_status(connection, 'tok', force=True)
    assert result['channel'] == 'public'
    assert result['platform'] == 'MacOSX'
    assert result['updateAvailable'] is False


@respx.mock
async def test_update_status_picks_the_configured_linux_release() -> None:
    connection = seed_connection(name='pinned-release', url=BASE, token='tok', updateRelease='redhat|linux-x86_64')
    respx.get(f'{BASE}/').mock(return_value=httpx.Response(200, json={'MediaContainer': {'version': '1.41.0', 'platform': 'Linux'}}))
    _mock_prefs()
    releases = [
        {'label': 'Ubuntu (x86_64)', 'distro': 'debian', 'build': 'linux-x86_64', 'url': 'https://d/deb.deb'},
        {'label': 'Fedora (x86_64)', 'distro': 'redhat', 'build': 'linux-x86_64', 'url': 'https://d/rpm.rpm'},
    ]
    respx.get('https://plex.tv/api/downloads/5.json').mock(
        return_value=httpx.Response(200, json={'computer': {'Linux': {'version': '1.42.0', 'releases': releases}}})
    )
    result = await plex_account.update_status(connection, 'tok', force=True)
    assert result['label'] == 'Fedora (x86_64)'
    assert result['downloadUrl'] == 'https://d/rpm.rpm'
    assert [r['label'] for r in result['releases']] == ['Ubuntu (x86_64)', 'Fedora (x86_64)']

    connection = seed_connection(name='no-release', url=BASE, token='tok')
    fallback = await plex_account.update_status(connection, 'tok', force=True)
    assert fallback['downloadUrl'] == 'https://d/deb.deb'


@respx.mock
async def test_update_status_default_release_skips_stale_builds(monkeypatch: pytest.MonkeyPatch, connection: Any) -> None:
    respx.get(f'{BASE}/').mock(return_value=httpx.Response(200, json={'MediaContainer': {'version': '1.43.0', 'platform': 'Windows'}}))
    _mock_prefs()
    releases = [
        {'label': 'Windows 32-bit', 'distro': 'english', 'build': 'windows-x86', 'url': 'https://d/1.42.2-x86.exe'},
        {'label': 'Windows 64-bit', 'distro': 'english', 'build': 'windows-x86_64', 'url': 'https://d/1.43.3-x86_64.exe'},
    ]
    respx.get('https://plex.tv/api/downloads/5.json').mock(
        return_value=httpx.Response(200, json={'computer': {'Windows': {'version': '1.43.3', 'releases': releases}}})
    )
    result = await plex_account.update_status(connection, 'tok', force=True)
    assert result['label'] == 'Windows 64-bit'
    assert result['downloadUrl'] == 'https://d/1.43.3-x86_64.exe'


@respx.mock
async def test_update_status_reports_unmatched_platform(monkeypatch: pytest.MonkeyPatch, connection: Any) -> None:
    respx.get(f'{BASE}/').mock(return_value=httpx.Response(200, json={'MediaContainer': {'version': '1.41.0', 'platform': 'BeOS'}}))
    _mock_prefs()
    respx.get('https://plex.tv/api/downloads/5.json').mock(return_value=httpx.Response(200, json={'computer': {'Windows': {'version': '1.42.0'}}}))
    result = await plex_account.update_status(connection, 'tok', force=True)
    assert result['error'] == 'Could not match server platform: BeOS'
