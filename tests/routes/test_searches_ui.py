from __future__ import annotations

from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from phoenixadult.models.scrape import SearchResult
from phoenixadult.utils.cache import search_store
from tests.support import authed_client

_APIS = ('/searches/api/purge', '/searches/api/purge-site', '/searches/api/purge-all', '/searches/api/sweep', '/searches/api/research')


def _seed(site: str = 'Nubile Films', title: str = 'stored query', cur_id: str = 'sr1') -> str:
    search_store.save((site, title, '2024-06-21', '', ''), [SearchResult(title='Stored Result', scene_url='https://x/1', cur_id=cur_id, score=88.0)])
    entries = search_store.dump()['entries']
    return str(next(e for e in entries if e['title'] == title)['keyHash'])


def test_the_page_is_admin_only() -> None:
    anon = TestClient(create_app())
    assert anon.get('/searches', headers={'accept': 'application/json'}).status_code == 401

    from phoenixadult.utils.auth import user_store

    user_store.create_user('boss', 'pw-boss', is_admin=True)
    uid = user_store.create_user('member', 'pw-member', is_admin=False)
    member = TestClient(create_app())
    member.cookies.set('pa_session', user_store.create_session(uid, 'pytest'))
    assert member.get('/searches').status_code == 403
    assert member.get('/searches/api/list').status_code == 403
    for api in _APIS:
        assert member.post(api, json={}).status_code == 403, api
    assert 'Searches' not in member.get('/queue').text.split('<h1>')[0], 'the nav must not advertise an admin-only page'


def test_admins_see_the_page_and_the_state() -> None:
    _seed()
    client = authed_client()
    body = client.get('/searches').text
    assert '<title>Stored Searches</title>' in body and 'stored query' in body
    assert '>Searches</a>' in body, 'admins get the nav link'
    state = client.get('/searches/api/list').json()
    assert state['totals']['searches'] == 1
    assert state['entries'][0]['results'][0]['title'] == 'Stored Result'


def test_purge_endpoints_walk_the_status_codes() -> None:
    key = _seed()
    client = authed_client()
    assert client.post('/searches/api/purge', json={}).status_code == 400
    assert client.post('/searches/api/purge', json={'keyHash': 'nope'}).status_code == 404
    ok = client.post('/searches/api/purge', json={'keyHash': key})
    assert ok.status_code == 200 and ok.json()['totals']['searches'] == 0

    _seed(site='Bratty Sis')
    _seed(site='Nubile Films', title='other', cur_id='sr2')
    assert client.post('/searches/api/purge-site', json={}).status_code == 400
    r = client.post('/searches/api/purge-site', json={'site': 'Bratty Sis'})
    assert r.status_code == 200 and r.json()['purged'] == 1
    r = client.post('/searches/api/purge-all', json={})
    assert r.status_code == 200 and r.json()['purged'] == 1 and r.json()['totals']['searches'] == 0


def test_sweep_removes_only_expired_rows(monkeypatch) -> None:
    import time

    monkeypatch.setenv('SEARCH_STORE_TTL_DAYS', '10')
    search_store._write(
        ('Nubile Films', 'ancient', '2024-01-01', '', ''), [SearchResult(title='Old', scene_url='https://x/o', cur_id='old')], time.time() - 11 * 86400
    )
    _seed(title='fresh')
    client = authed_client()
    r = client.post('/searches/api/sweep', json={})
    assert r.status_code == 200 and r.json()['removed'] == 1
    assert [e['title'] for e in client.get('/searches/api/list').json()['entries']] == ['fresh']


def test_research_purges_and_requeues_with_the_stored_query(monkeypatch) -> None:
    from phoenixadult.routes import search_routes

    key = _seed(title='requeue me')
    captured: list[dict[str, str]] = []

    class _FakeService:
        def requeue_search(self, replay, provider):
            captured.append(replay)

    monkeypatch.setattr(search_routes, 'match_service_for', lambda pid: (object(), _FakeService()))
    client = authed_client()
    assert client.post('/searches/api/research', json={'keyHash': 'nope'}).status_code == 404
    r = client.post('/searches/api/research', json={'keyHash': key})
    assert r.status_code == 200
    assert r.json()['totals']['searches'] == 0, 'the stored search is purged before the requeue'
    assert captured and captured[0]['title'] == 'requeue me' and captured[0]['search_site'] == 'Nubile Films'
    assert captured[0]['date'] == '2024-06-21'


def test_the_page_offers_a_duplicates_only_filter() -> None:
    _seed()
    client = authed_client()
    body = client.get('/searches').text
    assert 'id="dup-filter"' in body and 'Duplicates only' in body
    assert "params.set('dupes', '1')" in body, 'the filter is applied server-side so totals stay right'

    everything = client.get('/searches/api/entries').json()
    only_dupes = client.get('/searches/api/entries', params={'dupes': '1'}).json()
    assert all(len(group) > 1 for group in only_dupes['groups']), 'solo searches must drop out'
    assert only_dupes['matched'] <= everything['matched']
    assert only_dupes['totals'] == everything['totals'], 'the headline totals count the whole store, not the page'
