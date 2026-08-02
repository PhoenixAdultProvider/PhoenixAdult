from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from phoenixadult.utils.images import logo_cache


@pytest.fixture()
def _cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    monkeypatch.setenv('LOGO_CACHE_DIR', str(tmp_path))
    (tmp_path / 'brazzers').mkdir()
    (tmp_path / 'brazzers' / 'logo.baby-got-boobs.png').write_bytes(b'png')
    logo_cache.invalidate()
    return tmp_path


def test_requires_auth_and_lists_with_site_names(_cache: Path) -> None:
    client = TestClient(create_app())
    assert client.get('/logos').status_code == 401
    page = client.get('/logos?token=tok')
    assert page.status_code == 200 and 'Logo Cache' in page.text

    data = client.get('/logos/api/list', headers={'x-admin-token': 'tok'}).json()
    assert data['logos'][0]['slug'] == 'baby-got-boobs'
    assert data['logos'][0]['site'] == 'Baby Got Boobs'
    assert data['logos'][0]['url'].startswith('/images/local/logos/brazzers/logo.baby-got-boobs.png?v=')


def test_purge_endpoints(_cache: Path) -> None:
    client = TestClient(create_app())
    hdr = {'x-admin-token': 'tok'}
    assert client.post('/logos/api/purge', json={}, headers=hdr).status_code == 400
    assert client.post('/logos/api/purge', json={'rel': 'nope.png'}, headers=hdr).status_code == 404
    assert client.post('/logos/api/purge', json={'rel': 'brazzers/logo.baby-got-boobs.png'}, headers=hdr).status_code == 200
    assert client.post('/logos/api/purge-all', headers=hdr).json()['purged'] == 0


def test_local_route_serves_logo_cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    outside = tmp_path / 'elsewhere'
    (outside / 'brazzers').mkdir(parents=True)
    (outside / 'brazzers' / 'logo.brazzers.png').write_bytes(b'pngbytes')
    monkeypatch.setenv('LOGO_CACHE_DIR', str(outside))
    client = TestClient(create_app())
    r = client.get('/images/local/logos/brazzers/logo.brazzers.png')
    assert r.status_code == 200 and r.content == b'pngbytes'
    assert client.get('/images/local/logos/../secrets.png').status_code in (400, 404)
