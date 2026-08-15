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
    for marker in ('reveal" data-for="password"', 'reveal" data-for="confirm"', 'input[type=password].pa-input, input.revealed { padding-right:'):
        assert marker in setup
    assert 'uppercase letter, a number, and a special character' in setup

    c.post('/setup', json={'username': 'admin', 'password': 'Hunter2hunter!'})
    login = _remote().get('/login').text
    assert 'reveal" data-for="password"' in login
    assert 'input[type=password].pa-input, input.revealed { padding-right:' in login


def test_setup_compares_the_confirm_field_not_the_window_global() -> None:
    body = _remote().get('/setup').text
    assert 'confirmField.value' in body
    assert 'password.value !== confirm.value' not in body
    assert 'confirm.value' not in body.replace('confirmField.value', '')


def test_the_credential_pages_are_real_forms_browsers_can_autofill() -> None:
    c = _remote()
    setup = c.get('/setup').text
    for marker in ('method="post"', 'action="/setup"', 'autocomplete="username"', 'autocomplete="new-password"'):
        assert marker in setup, marker
    c.post('/setup', json={'username': 'admin', 'password': 'Hunter2hunter!'})

    login = _remote().get('/login').text
    for marker in ('method="post"', 'action="/login"', 'autocomplete="username"', 'autocomplete="current-password"'):
        assert marker in login, marker
    assert 'e.preventDefault()' not in login, 'a fetch-intercepted submit is what suppresses save-password prompts'


def test_the_credential_pages_declare_a_mobile_viewport() -> None:
    c = _remote()
    for page in (c.get('/setup').text,):
        assert '<meta name="viewport" content="width=device-width' in page
        assert 'font-size: 16px' in page, 'inputs under 16px make iOS zoom on focus'
    c.post('/setup', json={'username': 'admin', 'password': 'Hunter2hunter!'})
    for path in ('/login', '/account'):
        page = c.get(path).text
        assert '<meta name="viewport" content="width=device-width' in page, path


def test_a_form_login_redirects_and_sets_the_cookie() -> None:
    c = _remote()
    c.post('/setup', json={'username': 'admin', 'password': 'Hunter2hunter!'})

    fresh = _remote()
    ok = fresh.post('/login', data={'username': 'admin', 'password': 'Hunter2hunter!', 'next': '/people'}, follow_redirects=False)
    assert ok.status_code == 303 and ok.headers['location'] == '/people'
    assert 'pa_session' in fresh.cookies

    bad = _remote().post('/login', data={'username': 'admin', 'password': 'nope'}, follow_redirects=False)
    assert bad.status_code == 401
    assert 'Invalid username or password.' in bad.text and 'action="/login"' in bad.text


def test_a_form_login_will_not_redirect_off_site() -> None:
    c = _remote()
    c.post('/setup', json={'username': 'admin', 'password': 'Hunter2hunter!'})
    r = _remote().post('/login', data={'username': 'admin', 'password': 'Hunter2hunter!', 'next': 'https://evil.example'}, follow_redirects=False)
    assert r.status_code == 303 and r.headers['location'] == '/config'


def test_a_form_setup_redirects_and_reports_errors_inline() -> None:
    weak = _remote().post('/setup', data={'username': 'admin', 'password': 'weak'}, follow_redirects=False)
    assert weak.status_code == 400
    assert 'uppercase letter' in weak.text and 'action="/setup"' in weak.text

    c = _remote()
    ok = c.post('/setup', data={'username': 'admin', 'password': 'Hunter2hunter!'}, follow_redirects=False)
    assert ok.status_code == 303 and ok.headers['location'] == '/config'
    assert 'pa_session' in c.cookies


def test_password_strength_scores_without_blocking() -> None:
    c = _remote()
    weak = c.post('/api/password-strength', json={'password': 'Passw0rd!'}).json()
    strong = c.post('/api/password-strength', json={'password': 'correct horse battery staple 9X!'}).json()
    assert weak['score'] < strong['score'] == 4
    assert c.post('/api/password-strength', json={}).json() == {'score': 0, 'feedback': ''}


def test_the_strength_meter_is_advisory_on_every_password_surface() -> None:
    c = _remote()
    assert 'pwMeterFill' in c.get('/setup').text
    c.post('/setup', json={'username': 'admin', 'password': 'Hunter2hunter!'})
    assert 'pwMeterFill' in c.get('/account').text
    assert 'pwMeterFill' in c.get('/config').text
