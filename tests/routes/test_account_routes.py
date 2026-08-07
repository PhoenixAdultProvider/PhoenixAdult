from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from phoenixadult.utils.auth import user_store
from tests.conftest import authed_client


def test_account_page_shows_the_username() -> None:
    client = authed_client()
    page = client.get('/account')
    assert page.status_code == 200 and 'tester' in page.text


def test_change_password_requires_the_current_one() -> None:
    client = authed_client()
    wrong = client.post('/account/api/password', json={'current': 'nope', 'new': 'Newpassword1!'})
    assert wrong.status_code == 403
    ok = client.post('/account/api/password', json={'current': 'pytest-pw', 'new': 'Newpassword1!'})
    assert ok.status_code == 200


def test_change_password_revokes_other_sessions() -> None:
    app = create_app()
    uid = user_store.create_user('tester', 'pytest-pw', is_admin=True)
    keep = user_store.create_session(uid, 'keep')
    other = user_store.create_session(uid, 'other')
    client = TestClient(app)
    client.cookies.set('pa_session', keep)
    r = client.post('/account/api/password', json={'current': 'pytest-pw', 'new': 'Newpassword1!'})
    assert r.status_code == 200
    import time

    from phoenixadult.utils.auth.passwords import hash_token

    assert user_store.session_user(hash_token(keep), time.time()) is not None
    assert user_store.session_user(hash_token(other), time.time()) is None


def test_regenerate_api_key_returns_a_working_key() -> None:
    client = authed_client()
    r = client.post('/account/api/key/regenerate')
    assert r.status_code == 200
    key = r.json()['key']
    assert key.startswith('pa_')
    assert key in client.get('/account').text, 'the key stays visible on the account page'

    other = TestClient(create_app())
    assert other.get('/config', headers={'accept': 'text/html', 'x-api-key': key}, follow_redirects=False).status_code == 200


def test_sessions_can_be_listed_and_revoked() -> None:
    app = create_app()
    uid = user_store.create_user('tester', 'pytest-pw', is_admin=True)
    current = user_store.create_session(uid, 'current')
    other = user_store.create_session(uid, 'other')
    client = TestClient(app)
    client.cookies.set('pa_session', current)

    sessions = client.get('/account/api/sessions').json()['sessions']
    assert len(sessions) == 2
    assert sum(1 for s in sessions if s['current']) == 1

    from phoenixadult.utils.auth.passwords import hash_token

    r = client.post('/account/api/sessions/revoke', json={'tokenHash': hash_token(other)})
    assert r.status_code == 200
    assert len(client.get('/account/api/sessions').json()['sessions']) == 1


def test_the_account_page_explains_how_to_add_the_provider_to_plex() -> None:
    body = authed_client().get('/account').text
    assert 'Configure The Provider In Plex' in body
    assert 'Settings &rarr; Metadata Agents &rarr; Add Provider' in body
    assert 'Add Agent' in body and 'Primary' in body
    assert 'Plex Local Media' in body
    assert '/phoenixadult/movies' in body


def test_the_provider_url_shows_a_key_slot_when_token_auth_is_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('TOKEN_BASED_AUTH', 'true')
    body = authed_client().get('/account').text
    assert '/api/hook/YOUR_API_KEY/phoenixadult/movies' in body
    assert 'const TOKEN_AUTH = true;' in body, 'regenerating a key should fill the URL in'
    monkeypatch.setenv('TOKEN_BASED_AUTH', 'false')
    off = authed_client().get('/account').text
    assert 'YOUR_API_KEY' not in off, 'with token auth off the plain URL is what Plex needs'
    assert 'const TOKEN_AUTH = false;' in off


def test_the_page_scripts_are_valid_javascript() -> None:
    body = authed_client().get('/account').text
    script = body.split('<script>')[1].split('</script>')[0]
    assert '&#34;' not in script and '&amp;' not in script, 'autoescaped entities inside <script> kill every button on the page'


def test_the_account_page_shows_the_full_key_and_a_copy_button() -> None:
    client = authed_client()
    key = client.post('/account/api/key/regenerate').json()['key']
    body = client.get('/account').text
    assert key in body, 'the key is shown in full, not obfuscated'
    assert "copyText('keyReveal'" in body and '>Copy Key</button>' in body
    assert '>Copy URL</button>' in body


def test_the_provider_url_carries_the_real_key_when_token_auth_is_on(monkeypatch: pytest.MonkeyPatch) -> None:
    client = authed_client()
    key = client.post('/account/api/key/regenerate').json()['key']
    monkeypatch.setenv('TOKEN_BASED_AUTH', 'true')
    body = client.get('/account').text
    assert f'/api/hook/{key}/phoenixadult/movies' in body, 'the instructions show the URL Plex actually needs'
    assert 'YOUR_API_KEY' not in body
