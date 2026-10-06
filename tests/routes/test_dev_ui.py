from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from phoenixadult.models.metadata import PlexMetadata
from phoenixadult.models.scrape import SceneDetail
from phoenixadult.utils.helpers.ids import b64url_encode
from phoenixadult.utils.plex.rating_key import to_rating_key
from tests.support import authed_client

TOKEN = 'devtoken'


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv('DEV_UI_ENABLE', 'true')
    return authed_client()


def test_dev_requires_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('DEV_UI_ENABLE', 'true')
    assert TestClient(create_app()).get('/dev', headers={'accept': 'application/json'}).status_code == 401


def test_dev_page_renders(client: TestClient) -> None:
    r = client.get('/dev')
    assert r.status_code == 200
    assert 'Provider Dev UI' in r.text
    assert 'Registered Sites' in r.text


def test_dev_test_pipeline(client: TestClient) -> None:
    r = client.post('/dev/test', json={'filename': 'Unknown.Site.2024.01.02.scene.mp4'})
    assert r.status_code == 200
    data = r.json()
    assert 'steps' in data and 'logs' in data
    assert data['steps'][0]['step'].startswith('1.')
    assert data['steps'][0]['ok'] is False
    assert 'durationMs' in data['steps'][0]


def test_dev_test_requires_filename(client: TestClient) -> None:
    r = client.post('/dev/test', json={})
    assert r.status_code == 400


def test_dev_metadata_pipeline(client: TestClient) -> None:
    r = client.post(
        '/dev/metadata',
        json={'ratingKey': 'scene-somesite-YWJj', 'providerId': 'phoenixadult'},
    )
    assert r.status_code == 200
    data = r.json()
    assert data['steps'][0]['step'].startswith('1.')
    assert data['steps'][0]['ok'] is True
    assert any(not s['ok'] for s in data['steps'])
    assert 'logs' in data


def test_dev_metadata_requires_fields(client: TestClient) -> None:
    r = client.post('/dev/metadata', json={'ratingKey': 'x'})
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
    r = client.get('/dev')
    assert 'Full Pipeline (DB Round-Trip)' in r.text
    assert 'roundtrip-section' in r.text


def test_dev_page_has_a_mobile_layout(client: TestClient) -> None:
    r = client.get('/dev')
    assert r.status_code == 200
    assert '@media (max-width: 720px)' in r.text
    assert 'data-label="Content Type"' in r.text
    assert 'class="c-site"' in r.text
    assert 'style="flex:0' not in r.text


def test_dev_ui_is_off_until_the_config_turns_it_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('DEV_UI_ENABLE', raising=False)
    monkeypatch.setenv('NODE_ENV', 'development')
    assert authed_client().get('/dev').status_code == 404


def test_dev_ui_serves_in_production_once_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('NODE_ENV', 'production')
    monkeypatch.setenv('DEV_UI_ENABLE', 'true')
    assert authed_client().get('/dev').status_code == 200


def test_dev_ui_stays_admin_only_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.utils.auth import user_store

    monkeypatch.setenv('DEV_UI_ENABLE', 'true')
    user_store.create_user('boss', 'pw-boss', is_admin=True)
    uid = user_store.create_user('member', 'pw-member', is_admin=False)
    client = TestClient(create_app())
    client.cookies.set('pa_session', user_store.create_session(uid, 'pytest'))

    assert client.get('/dev').status_code == 403


def test_dev_ui_is_a_documented_config_toggle() -> None:
    from phoenixadult.config.env_catalog import ENV_CATALOG, GROUP_TAB

    spec = next(entry for entry in ENV_CATALOG if entry.key == 'DEV_UI_ENABLE')
    assert spec.kind == 'boolean'
    assert spec.default_value == 'false'
    assert GROUP_TAB[spec.group] == 'system'


def _steps(response: Any) -> dict[str, dict[str, Any]]:
    assert response.status_code == 200
    return {s['step']: s for s in response.json()['steps']}


def test_dev_test_searches_and_scores_the_results(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import phoenixadult.routes.dev_routes as dr
    from phoenixadult.models.scrape import SearchResult

    async def fake_search(search_data: Any) -> list[SearchResult]:
        return [SearchResult(title='Cool Scene', scene_url='https://203.0.113.5/scene', cur_id='abc', score=100.0, release_date='2024-01-02')]

    monkeypatch.setattr(dr.scraper, 'search', fake_search)
    steps = _steps(client.post('/dev/test', json={'filename': 'Brazzers - 2024-01-02 - Cool Scene.mp4', 'yearOverride': '2024'}))
    assert list(steps) == ['1. Parse filename', '2. Site lookup', '3. Provider lookup', '4. Search query', '5. Search results']
    assert all(s['ok'] for s in steps.values())
    assert steps['2. Site lookup']['data']['name'] == 'Brazzers'
    assert steps['4. Search query']['data']['query']
    found = steps['5. Search results']['data']
    assert found['count'] == 1 and found['results'][0]['title'] == 'Cool Scene' and found['searchDate'] == '2024-01-02'


@pytest.mark.parametrize(
    ('outcome', 'error'),
    [(None, 'No scraper registered'), (RuntimeError('boom'), 'Internal error'), ([], 'No results returned from upstream')],
)
def test_dev_test_reports_a_failed_search(client: TestClient, monkeypatch: pytest.MonkeyPatch, outcome: Any, error: str) -> None:
    import phoenixadult.routes.dev_routes as dr

    async def fake_search(search_data: Any) -> Any:
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(dr.scraper, 'search', fake_search)
    step5 = _steps(client.post('/dev/test', json={'filename': 'Brazzers - 2024-01-02 - Cool Scene.mp4'}))['5. Search results']
    assert step5['ok'] is False and error in step5['error']


@pytest.mark.parametrize(
    ('rating_key', 'failed_step', 'error'),
    [
        ('garbage', '1. Parse ratingKey', 'Could not parse ratingKey'),
        (to_rating_key(b64url_encode('https://203.0.113.5/scene'), 'No Such Site', '2024-01-02'), '2. Site lookup', 'No site found'),
        (to_rating_key(b64url_encode('http://127.0.0.1/scene'), 'Brazzers', '2024-01-02'), '4. Decode identifier', 'sceneURL blocked'),
    ],
)
def test_dev_metadata_stops_at_the_first_failed_step(client: TestClient, rating_key: str, failed_step: str, error: str) -> None:
    response = client.post('/dev/metadata', json={'ratingKey': rating_key, 'providerId': 'phoenixadult'})
    last = response.json()['steps'][-1]
    assert last['step'] == failed_step and last['ok'] is False and error in last['error']


def test_dev_metadata_reports_an_unknown_provider(client: TestClient) -> None:
    steps = _steps(client.post('/dev/metadata', json={'ratingKey': _rating_key(), 'providerId': 'nope'}))
    assert steps['3. Provider lookup']['ok'] is False and 'Provider "nope" not found' in steps['3. Provider lookup']['error']


@pytest.mark.parametrize(('outcome', 'error'), [(None, 'Scraper returned no SceneDetail'), (RuntimeError('boom'), 'Internal error')])
def test_dev_metadata_reports_a_failed_live_fetch(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, outcome: Any, error: str) -> None:
    import phoenixadult.routes.dev_routes as dr

    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))

    async def fake_fetch(scene_url: str, site: Any, ctx: Any = None) -> Any:
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(dr.scraper, 'fetch_scene_detail', fake_fetch)
    step5 = _steps(client.post('/dev/metadata', json={'ratingKey': _rating_key(), 'providerId': 'phoenixadult'}))['5. Fetch metadata']
    assert step5['ok'] is False and error in step5['error']


def test_dev_metadata_live_summary_lists_the_mapped_fields(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'false')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    _stub_live_scrape(monkeypatch)
    data = _steps(client.post('/dev/metadata', json={'ratingKey': _rating_key(), 'providerId': 'phoenixadult', 'filename': 'x.mp4', 'resultScore': 91}))[
        '5. Fetch metadata'
    ]['data']
    assert data['servedFrom'] == 'live' and data['title'] == 'Cool Scene' and data['studio'] == 'Brazzers'
    assert data['fixture']['site'] == 'Brazzers' and data['fixture']['filename'] == 'x.mp4' and data['fixture']['expect']['score'] == 91
