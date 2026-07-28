from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from phoenixadult.clients.base import SceneDetail
from phoenixadult.models.metadata import PlexMetadata
from phoenixadult.utils.helpers.helpers import b64url_encode
from phoenixadult.utils.plex.rating_key import to_rating_key

TOKEN = 'devtoken'


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
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


def _stub_live_scrape(monkeypatch: pytest.MonkeyPatch) -> None:
    import phoenixadult.routes.dev_routes as dr

    async def fake_fetch(scene_url: str, site: Any, ctx: Any = None) -> SceneDetail:
        return SceneDetail(title='Cool Scene', studio='Brazzers')

    async def fake_map(detail: Any, rating_key: str, identifier: str, release_date: Any, site: Any, filename_site: Any = None) -> PlexMetadata:
        return PlexMetadata.model_validate(
            {'type': 'movie', 'ratingKey': rating_key, 'guid': f'guid://{rating_key}', 'title': 'Cool Scene', 'studio': 'Brazzers'}
        )

    monkeypatch.setattr(dr.scraper, 'fetch_scene_detail', fake_fetch)
    monkeypatch.setattr(dr.mapper, 'to_metadata', fake_map)


def _rating_key() -> str:
    return to_rating_key(b64url_encode('https://203.0.113.5/scene'), 'Brazzers', '2024-01-02')


def _post_metadata(client: TestClient, *, full_pipeline: bool) -> list[dict[str, Any]]:
    r = client.post(
        '/dev/metadata',
        params={'token': TOKEN},
        json={'ratingKey': _rating_key(), 'providerId': 'phoenixadult', 'fullPipeline': full_pipeline},
    )
    assert r.status_code == 200
    steps: list[dict[str, Any]] = r.json()['steps']
    return steps


def test_dev_metadata_full_pipeline_roundtrip(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    monkeypatch.setenv('DATA18_ENABLE', 'false')
    _stub_live_scrape(monkeypatch)

    steps = _post_metadata(client, full_pipeline=True)
    step6 = next(s for s in steps if s['step'].startswith('6.'))
    assert step6['ok'] is True
    data = step6['data']
    assert data['cacheEnabled'] is True and data['written'] is True
    assert data['identical'] is True and data['diffFields'] == []
    md = data['reassembled']['MediaContainer']['Metadata'][0]
    assert md['title'] == 'Cool Scene' and md['studio'] == 'Brazzers'

    again = _post_metadata(client, full_pipeline=True)
    step5 = next(s for s in again if s['step'].startswith('5.'))
    assert step5['data']['servedFrom'] == 'snapshot'
    step6 = next(s for s in again if s['step'].startswith('6.'))
    assert step6['ok'] is True and 'DB reassembly path' in step6['data']['note']


def test_dev_metadata_full_pipeline_reports_disabled_cache(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'false')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    _stub_live_scrape(monkeypatch)

    steps = _post_metadata(client, full_pipeline=True)
    step6 = next(s for s in steps if s['step'].startswith('6.'))
    assert step6['ok'] is True
    assert step6['data']['cacheEnabled'] is False
    assert 'METADATA_CACHE_ENABLE' in step6['data']['note']
    assert 'reassembled' not in step6['data']


def test_dev_metadata_no_roundtrip_step_when_toggle_off(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    monkeypatch.setenv('DATA18_ENABLE', 'false')
    _stub_live_scrape(monkeypatch)

    steps = _post_metadata(client, full_pipeline=False)
    assert not any(s['step'].startswith('6.') for s in steps)


def test_dev_page_has_full_pipeline_toggle(client: TestClient) -> None:
    r = client.get('/dev', params={'token': TOKEN})
    assert 'Full Pipeline (DB Round-Trip)' in r.text
    assert 'roundtrip-section' in r.text


def test_dev_page_has_a_mobile_layout(client: TestClient) -> None:
    r = client.get('/dev', params={'token': TOKEN})
    assert r.status_code == 200
    assert '@media (max-width: 720px)' in r.text
    assert 'data-label="Content Type"' in r.text
    assert 'class="c-site"' in r.text
    assert 'style="flex:0' not in r.text
