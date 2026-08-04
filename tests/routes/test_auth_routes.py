from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from phoenixadult.utils.auth import rate_limit


@pytest.fixture(autouse=True)
def _clear_rate_limit() -> None:
    rate_limit._buckets.clear()


def _remote() -> TestClient:
    return TestClient(create_app(), client=('203.0.113.9', 51234))


def test_setup_creates_the_first_admin_and_sets_a_cookie() -> None:
    c = _remote()
    assert c.get('/setup').status_code == 200
    r = c.post('/setup', json={'username': 'admin', 'password': 'Hunter2hunter!'})
    assert r.status_code == 200 and r.json()['redirect'] == '/config'
    assert 'pa_session' in c.cookies
    assert c.get('/config', headers={'accept': 'text/html'}, follow_redirects=False).status_code == 200


def test_setup_404s_once_a_user_exists() -> None:
    c = _remote()
    c.post('/setup', json={'username': 'admin', 'password': 'Hunter2hunter!'})
    assert _remote().get('/setup').status_code == 404
    assert _remote().post('/setup', json={'username': 'second', 'password': 'Password12!'}).status_code == 409


def test_setup_validates_the_username_and_password_policy() -> None:
    assert _remote().post('/setup', json={'username': 'ab', 'password': 'Hunter2hunter!'}).status_code == 400
    for weak in ('Sh0rt!', 'hunter2hunter!', 'Hunterhunter!', 'Hunter2hunter'):
        r = _remote().post('/setup', json={'username': 'admin', 'password': weak})
        assert r.status_code == 400 and 'uppercase' in r.json()['error']


def test_unauthenticated_html_redirects_to_setup_then_login() -> None:
    c = _remote()
    r = c.get('/config', headers={'accept': 'text/html'}, follow_redirects=False)
    assert r.status_code == 302 and r.headers['location'] == '/setup'
    c.post('/setup', json={'username': 'admin', 'password': 'Hunter2hunter!'})
    r2 = _remote().get('/metadata', headers={'accept': 'text/html'}, follow_redirects=False)
    assert r2.status_code == 302 and r2.headers['location'].startswith('/login?next=') and 'metadata' in r2.headers['location']


def test_unauthenticated_json_is_401() -> None:
    c = _remote()
    c.post('/setup', json={'username': 'admin', 'password': 'Hunter2hunter!'})
    assert _remote().get('/config/api/state', headers={'accept': 'application/json'}).status_code == 401


def test_login_success_and_failure() -> None:
    c = _remote()
    c.post('/setup', json={'username': 'admin', 'password': 'Hunter2hunter!'})
    fresh = _remote()
    bad = fresh.post('/login', json={'username': 'admin', 'password': 'nope'})
    assert bad.status_code == 401
    ok = fresh.post('/login', json={'username': 'admin', 'password': 'Hunter2hunter!', 'next': '/people'})
    assert ok.status_code == 200 and ok.json()['redirect'] == '/people'
    assert 'pa_session' in fresh.cookies


def test_login_next_is_validated_against_open_redirect() -> None:
    c = _remote()
    c.post('/setup', json={'username': 'admin', 'password': 'Hunter2hunter!'})
    fresh = _remote()
    r = fresh.post('/login', json={'username': 'admin', 'password': 'Hunter2hunter!', 'next': 'https://evil.example'})
    assert r.json()['redirect'] == '/config'


def test_login_is_rate_limited() -> None:
    c = _remote()
    c.post('/setup', json={'username': 'admin', 'password': 'Hunter2hunter!'})
    fresh = _remote()
    for _ in range(rate_limit._FREE_ATTEMPTS + 1):
        fresh.post('/login', json={'username': 'admin', 'password': 'wrong'})
    blocked = fresh.post('/login', json={'username': 'admin', 'password': 'wrong'})
    assert blocked.status_code == 429 and 'Retry-After' in blocked.headers


def test_logout_clears_the_session() -> None:
    c = _remote()
    c.post('/setup', json={'username': 'admin', 'password': 'Hunter2hunter!'})
    assert c.post('/logout').status_code == 200
    assert c.get('/config', headers={'accept': 'text/html'}, follow_redirects=False).status_code == 302


def test_session_cookie_is_httponly_and_lax() -> None:
    c = _remote()
    r = c.post('/setup', json={'username': 'admin', 'password': 'Hunter2hunter!'})
    set_cookie = r.headers['set-cookie'].lower()
    assert 'httponly' in set_cookie and 'samesite=lax' in set_cookie


def test_the_credential_pages_reveal_outside_the_password_manager_overlay() -> None:
    c = _remote()
    setup = c.get('/setup').text
    for marker in ('class="reveal" data-for="password"', 'class="reveal" data-for="confirm"', 'input[type=password], input.revealed { padding-right: 40px; }'):
        assert marker in setup
    assert 'uppercase letter, a number, and a special character' in setup

    c.post('/setup', json={'username': 'admin', 'password': 'Hunter2hunter!'})
    login = _remote().get('/login').text
    assert 'class="reveal" data-for="password"' in login
    assert 'input[type=password], input.revealed { padding-right: 40px; }' in login


def test_setup_compares_the_confirm_field_not_the_window_global() -> None:
    body = _remote().get('/setup').text
    assert 'pwField.value !== confirmField.value' in body
    assert 'password.value !== confirm.value' not in body
