"""Plex fixture addresses use the RFC 5737 documentation range only — never the host's real address."""

from __future__ import annotations

import httpx
import pytest
import respx

from phoenixadult.services import plex_account

BASE = 'http://192.0.2.10:32400'


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    plex_account._update_cache = None


def test_client_id_prefers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PLEX_CLIENT_ID', 'fixed-id')
    assert plex_account.client_id_or_new() == 'fixed-id'
    monkeypatch.delenv('PLEX_CLIENT_ID')
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


@respx.mock
async def test_update_status_compares_platform_versions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PLEX_URL', BASE)
    monkeypatch.setenv('PLEX_TOKEN', 'tok')
    respx.get(f'{BASE}/').mock(return_value=httpx.Response(200, json={'MediaContainer': {'version': '1.41.0.100-abc', 'platform': 'FreeBSD'}}))
    respx.get('https://plex.tv/api/downloads/5.json').mock(
        return_value=httpx.Response(
            200,
            json={
                'computer': {'Linux': {'version': '1.42.0.200-xyz'}},
                'nas': {'FreeBSD': {'version': '1.41.5.150-fbd'}},
            },
        )
    )
    result = await plex_account.update_status(force=True)
    assert result['current'] == '1.41.0.100-abc'
    assert result['latest'] == '1.41.5.150-fbd'
    assert result['updateAvailable'] is True

    respx.get(f'{BASE}/').mock(return_value=httpx.Response(500))
    cached = await plex_account.update_status()
    assert cached == result
