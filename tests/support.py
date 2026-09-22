from __future__ import annotations

from typing import Any

from phoenixadult.app_factory import create_app
from phoenixadult.mappers.metadata_mapper import MetadataMapper
from phoenixadult.models.scrape import SceneDetail, SearchContext
from phoenixadult.models.site_info import ResolvedSiteInfo
from phoenixadult.utils.auth import user_store

PLEX_UA = 'PlexMediaServer/1.43.3.10861-07dfddaeb'


def _seed_session(is_admin: bool = True) -> str:

    uid = user_store.oldest_admin_id() if user_store.user_count() else user_store.create_user('tester', 'pytest-pw', is_admin=is_admin)
    assert uid is not None
    return user_store.create_session(uid, 'pytest')


def authed_cookies() -> dict[str, str]:
    return {'pa_session': _seed_session()}


def seed_connection(name: str = 'Test Server', url: str = 'http://192.0.2.10:32400', token: str = 'test-token', **fields: Any) -> Any:
    from phoenixadult.services import plex_connections

    owner = user_store.oldest_admin_id() or user_store.create_user('tester', 'pytest-pw', is_admin=True)
    connection_id = plex_connections.create(owner, name)
    plex_connections.update_fields(connection_id, {'serverUrl': url, **fields})
    if token:
        plex_connections.save_token(connection_id, token)
    connection = plex_connections.get(connection_id)
    assert connection is not None
    return connection


def authed_client(app: Any = None, is_admin: bool = True) -> Any:
    from starlette.testclient import TestClient

    token = _seed_session(is_admin)
    client = TestClient(app or create_app())
    client.cookies.set('pa_session', token)
    return client


def plex_client(app: Any = None, host: str = '203.0.113.9') -> Any:
    from starlette.testclient import TestClient

    return TestClient(app or create_app(), client=(host, 51234), headers={'user-agent': PLEX_UA})


def served_collections(detail: SceneDetail) -> list[str]:
    return MetadataMapper()._resolve_labels(detail, None)[2]


def search_context(site: ResolvedSiteInfo | None, title: str = '', *, space: str = '+', **kw: Any) -> SearchContext:
    assert site is not None
    return SearchContext(title=title, encoded=title.replace(' ', space), search_site=site.name, site_info=site, **kw)
