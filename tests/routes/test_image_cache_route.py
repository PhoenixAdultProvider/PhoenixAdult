from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app


def test_cache_route_serves_and_images_prefix_is_gone(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    images = tmp_path / 'brazzers' / 'baby-got-boobs' / 'abc' / 'images'  # type: ignore[operator]
    images.mkdir(parents=True)
    (images / 'poster-00.jpg').write_bytes(b'IMG')
    client = TestClient(create_app())

    ok = client.get('/cache/brazzers/baby-got-boobs/abc/images/poster-00.jpg')
    assert ok.status_code == 200 and ok.content == b'IMG'

    assert client.get('/images/cache/brazzers/baby-got-boobs/abc/images/poster-00.jpg').status_code == 404
    assert client.get('/cache/brazzers/baby-got-boobs/abc/images/missing.jpg').status_code == 404
    assert client.get('/cache/brazzers/evil.txt').status_code == 400


def test_versioned_local_images_are_cached_immutably(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    monkeypatch.delenv('ADMIN_TOKEN', raising=False)
    (tmp_path / 'poster.jpg').write_bytes(b'\xff\xd8\xff\xe0JPEG')
    client = TestClient(create_app())

    versioned = client.get('/images/local/poster.jpg', params={'v': 'abc123'})
    assert versioned.status_code == 200
    assert versioned.headers['cache-control'] == 'public, max-age=31536000, immutable'

    bare = client.get('/images/local/poster.jpg')
    assert bare.status_code == 200
    assert bare.headers['cache-control'] == 'public, max-age=300'


def test_a_rejected_proxy_url_is_logged_with_its_reason(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.delenv('ADMIN_TOKEN', raising=False)
    client = TestClient(create_app())

    with caplog.at_level('WARNING'):
        r = client.get('/images/proxy', params={'url': 'ftp://example.com/x.jpg'})

    assert r.status_code == 400
    assert r.json() == {'error': 'Invalid url'}
    assert 'blocked scheme' in caplog.text
