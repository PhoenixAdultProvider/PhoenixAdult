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
