from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.app_factory import create_app

TOKEN = 'devtoken'


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """The /dev UI is only mounted outside production; pin it so an ambient
    NODE_ENV=production in the developer's .env can't 404 these tests."""
    monkeypatch.setenv('NODE_ENV', 'development')
    monkeypatch.setenv('ADMIN_TOKEN', TOKEN)
    return TestClient(create_app())


def test_dev_requires_auth(client: TestClient) -> None:
    assert client.get('/dev').status_code == 401


def test_dev_open_when_token_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('NODE_ENV', 'development')
    monkeypatch.delenv('ADMIN_TOKEN', raising=False)
    open_client = TestClient(create_app())
    assert open_client.get('/dev').status_code == 200
    assert open_client.get('/config').status_code == 200


def test_dev_page_renders(client: TestClient) -> None:
    r = client.get('/dev', params={'token': TOKEN})
    assert r.status_code == 200
    assert 'Provider Dev UI' in r.text
    assert 'Registered Sites' in r.text


def test_dev_test_pipeline(client: TestClient) -> None:
    r = client.post('/dev/test', params={'token': TOKEN}, json={'filename': 'Unknown.Site.2024.01.02.scene.mp4'})
    assert r.status_code == 200
    data = r.json()
    assert 'steps' in data and 'logs' in data
    assert data['steps'][0]['step'].startswith('1.')
    assert data['steps'][0]['ok'] is False
    assert 'durationMs' in data['steps'][0]


def test_dev_test_requires_filename(client: TestClient) -> None:
    r = client.post('/dev/test', params={'token': TOKEN}, json={})
    assert r.status_code == 400


def test_dev_metadata_pipeline(client: TestClient) -> None:
    r = client.post(
        '/dev/metadata',
        params={'token': TOKEN},
        json={'ratingKey': 'scene-somesite-YWJj', 'providerId': 'phoenixadult'},
    )
    assert r.status_code == 200
    data = r.json()
    assert data['steps'][0]['step'].startswith('1.')
    assert data['steps'][0]['ok'] is True
    assert any(not s['ok'] for s in data['steps'])
    assert 'logs' in data


def test_dev_metadata_requires_fields(client: TestClient) -> None:
    r = client.post('/dev/metadata', params={'token': TOKEN}, json={'ratingKey': 'x'})
    assert r.status_code == 400
