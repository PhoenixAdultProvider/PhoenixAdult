from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from phoenixadult.utils.images import logo_cache
from tests.conftest import authed_client


@pytest.fixture()
def _cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    root = tmp_path / 'logos'
    (root / 'brazzers').mkdir(parents=True)
    (root / 'brazzers' / 'logo.baby-got-boobs.png').write_bytes(b'png')
    logo_cache.invalidate()
    return root


def test_requires_auth_and_lists_with_site_names(_cache: Path) -> None:
    assert TestClient(create_app()).get('/logos', headers={'accept': 'application/json'}).status_code == 401
    client = authed_client()
    page = client.get('/logos')
    assert page.status_code == 200 and 'Logo Cache' in page.text

    data = client.get('/logos/api/list').json()
    assert data['logos'][0]['slug'] == 'baby-got-boobs'
    assert data['logos'][0]['site'] == 'Baby Got Boobs'
    assert data['logos'][0]['url'].startswith('/images/local/logos/brazzers/logo.baby-got-boobs.png?v=')


def test_purge_endpoints(_cache: Path) -> None:
    client = authed_client()
    assert client.post('/logos/api/purge', json={}).status_code == 400
    assert client.post('/logos/api/purge', json={'rel': 'nope.png'}).status_code == 404
    assert client.post('/logos/api/purge', json={'rel': 'brazzers/logo.baby-got-boobs.png'}).status_code == 200
    assert client.post('/logos/api/purge-all').json()['purged'] == 0


def test_local_route_serves_logo_cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    (tmp_path / 'logos' / 'brazzers').mkdir(parents=True)
    (tmp_path / 'logos' / 'brazzers' / 'logo.brazzers.png').write_bytes(b'pngbytes')
    client = authed_client()
    r = client.get('/images/local/logos/brazzers/logo.brazzers.png')
    assert r.status_code == 200 and r.content == b'pngbytes'
    assert client.get('/images/local/logos/../secrets.png').status_code in (400, 404)
