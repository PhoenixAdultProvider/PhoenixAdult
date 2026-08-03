from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app

PLEX_UA = {'User-Agent': 'PlexMediaServer/1.41.0.8992-8f13ecb3f'}
BROWSER_NAV = {'User-Agent': 'Mozilla/5.0', 'Sec-Fetch-Site': 'none', 'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Dest': 'document'}
ADMIN_IMG = {'User-Agent': 'Mozilla/5.0', 'Sec-Fetch-Site': 'same-origin', 'Sec-Fetch-Mode': 'no-cors', 'Sec-Fetch-Dest': 'image'}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv('IMAGE_GUARD_ENABLE', 'true')
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path / 'cache'))
    (tmp_path / 'pic.jpg').write_bytes(b'\xff\xd8\xff\xdb' + b'0' * 16)
    (tmp_path / 'cache').mkdir()
    (tmp_path / 'cache' / 'shot.jpg').write_bytes(b'\xff\xd8\xff\xdb' + b'0' * 16)
    return TestClient(create_app(), client=('203.0.113.9', 51234))


def test_direct_browsing_gets_a_403_page(client: TestClient) -> None:
    browser = {**BROWSER_NAV, 'Accept': 'text/html,application/xhtml+xml,*/*'}
    r = client.get('/images/local/pic.jpg', headers=browser)
    assert r.status_code == 403
    assert r.headers['content-type'].startswith('text/html')
    assert '<h1>403</h1>' in r.text
    assert client.get('/cache/shot.jpg', headers=browser).status_code == 403
    assert client.get('/images/proxy?url=https://x/p.jpg', headers=browser).status_code == 403


def test_non_browser_denial_stays_json(client: TestClient) -> None:
    r = client.get('/images/local/pic.jpg', headers={'User-Agent': 'curl/8.0', 'Accept': '*/*'})
    assert r.status_code == 403
    assert r.json() == {'error': 'Direct image access is not allowed'}


def test_plex_user_agent_is_served(client: TestClient) -> None:
    assert client.get('/images/local/pic.jpg', headers=PLEX_UA).status_code == 200
    assert client.get('/cache/shot.jpg', headers=PLEX_UA).status_code == 200


def test_admin_ui_same_origin_subresource_is_served(client: TestClient) -> None:
    assert client.get('/images/local/pic.jpg', headers=ADMIN_IMG).status_code == 200


def test_legacy_browser_referer_fallback(client: TestClient) -> None:
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'http://testserver/people?token=tok'}
    assert client.get('/images/local/pic.jpg', headers=headers).status_code == 200
    foreign = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://evil.example/embed'}
    assert client.get('/images/local/pic.jpg', headers=foreign).status_code == 403


def test_admin_token_is_served(client: TestClient) -> None:
    assert client.get('/images/local/pic.jpg?token=tok', headers=BROWSER_NAV).status_code == 200


def test_guard_defaults_off(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv('IMAGE_GUARD_ENABLE', raising=False)
    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    (tmp_path / 'pic.jpg').write_bytes(b'\xff\xd8\xff\xdb' + b'0' * 16)
    client = TestClient(create_app(), client=('203.0.113.9', 51234))
    assert client.get('/images/local/pic.jpg', headers=BROWSER_NAV).status_code == 200
