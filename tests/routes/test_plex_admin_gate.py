from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from phoenixadult.utils.auth import user_store
from tests.support import authed_client

_SHARED_STATE = [
    '/plex/connections/1/verify',
    '/plex/connections/1/import',
    '/plex/connections/1/import-item',
]


@pytest.fixture()
def member() -> TestClient:
    user_store.create_user('boss', 'pw-boss', is_admin=True)
    uid = user_store.create_user('member', 'pw-member', is_admin=False)
    client = TestClient(create_app())
    client.cookies.set('pa_session', user_store.create_session(uid, 'pytest'))
    return client


@pytest.mark.parametrize('path', _SHARED_STATE)
def test_endpoints_that_cross_a_user_boundary_refuse_members(member: TestClient, path: str) -> None:
    assert member.post(path, json={}).status_code == 403, f'{path} reaches shared state or fetches an arbitrary URL'


def test_members_keep_their_own_connections(member: TestClient) -> None:
    assert member.get('/plex/connections').status_code == 200, 'connections are scoped per user by _owned'
    assert member.get('/plex/status').status_code == 200


def test_an_admin_is_not_blocked_by_the_new_gate() -> None:
    admin = authed_client()
    for path in _SHARED_STATE:
        assert admin.post(path, json={}).status_code != 403, f'{path} must stay open to admins'


def _connection(client: TestClient) -> int:
    made = client.post('/plex/connections', json={'name': 'Home'})
    assert made.status_code == 200, made.text
    cid = int(made.json()['id'])
    set_url = client.post(f'/plex/connections/{cid}', json={'serverUrl': 'https://plex.example:32400'})
    assert set_url.status_code == 200, set_url.text
    return cid


def test_verify_refuses_an_address_plex_never_advertised(monkeypatch: pytest.MonkeyPatch) -> None:
    import phoenixadult.services.plex_account as pa
    import phoenixadult.services.plex_connections as pc

    admin = authed_client()
    cid = _connection(admin)
    monkeypatch.setattr(pc, 'token_for', lambda _cid: 'tok')

    reached: list[str] = []

    async def never_called(url: str, token: str) -> dict[str, object]:
        reached.append(url)
        return {}

    async def advertised(token: str, client_id: str) -> set[str]:
        return {'plex.example'}

    monkeypatch.setattr(pa, 'verify_server', never_called)
    monkeypatch.setattr(pa, 'advertised_hosts', advertised)

    blocked = admin.post(f'/plex/connections/{cid}/verify', json={'url': 'http://169.254.169.254/latest/meta-data'})
    assert blocked.status_code == 400 and 'advertises' in blocked.json()['error']
    assert reached == [], 'the refused address must not reach the fetcher at all'

    allowed = admin.post(f'/plex/connections/{cid}/verify', json={'url': 'https://plex.example:32400/'})
    assert allowed.status_code == 200
