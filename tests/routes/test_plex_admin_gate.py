from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from phoenixadult.utils.auth import user_store
from tests.conftest import authed_client

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
