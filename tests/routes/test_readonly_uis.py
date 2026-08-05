from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from tests.conftest import authed_client


@pytest.fixture
def member() -> TestClient:
    from phoenixadult.utils.auth import user_store

    user_store.create_user('boss', 'pw-boss', is_admin=True)
    uid = user_store.create_user('member', 'pw-member', is_admin=False)
    client = TestClient(create_app())
    client.cookies.set('pa_session', user_store.create_session(uid, 'pytest'))
    return client


def test_metadata_hides_purge_and_says_view(member: TestClient) -> None:
    body = member.get('/metadata').text
    assert 'const IS_ADMIN = false;' in body
    assert 'id="purgeAllBtn"' not in body
    assert 'id="dupBtn"' not in body
    assert 'id="pruneBtn"' not in body
    admin_body = authed_client().get('/metadata').text
    assert 'id="purgeAllBtn"' in admin_body and 'const IS_ADMIN = true;' in admin_body


def test_metadata_edit_is_read_only(member: TestClient) -> None:
    from phoenixadult.utils import cache as metadata_cache
    from phoenixadult.utils.cache import scene_store

    md = {'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': 'Scene', 'studio': 'Studio'}
    payload = {'MediaContainer': {'identifier': 'i', 'size': 1, 'Metadata': [md]}}
    scene_store.upsert('Studio', 'cur1', metadata_cache._hash('Studio', 'cur1'), metadata_cache.bundle_path(metadata_cache._hash('Studio', 'cur1')), payload)
    key = scene_store.snapshot_state('Studio', 'cur1')['key']

    body = member.get(f'/metadata/edit?key={key}').text
    assert 'id="f-title" readonly' in body
    assert 'id="f-summary" readonly' in body
    assert 'id="saveBtn"' not in body
    assert 'data-add="Genre"' not in body
    assert 'id="addImg"' not in body
    assert '>Back</button>' in body


def test_people_hides_writes_and_the_serving_line(member: TestClient) -> None:
    body = member.get('/people').text
    assert 'id="bulkBtn"' not in body
    assert 'id="bulkSource"' not in body
    assert 'Serving people images via' not in body
    assert '>View</button>' in body and '>Edit</button>' not in body
    assert 'class="purge"' not in body
    assert 'class="restore"' not in body


def test_logos_and_queue_hide_their_write_controls(member: TestClient) -> None:
    logos = member.get('/logos').text
    logos_markup = logos.split('<script>')[0]
    assert 'id="rescanBtn"' not in logos_markup
    assert 'onclick="purgeAll()"' not in logos_markup
    assert 'const IS_ADMIN = false;' in logos
    assert 'onclick="purgeAll()"' in authed_client().get('/logos').text

    queue = member.get('/queue').text
    assert 'flushKind(' not in queue.split('<script>')[0]
    assert 'const IS_ADMIN = false;' in queue
    assert "flushKind('search')" in authed_client().get('/queue').text


def test_write_endpoints_reject_non_admins(member: TestClient) -> None:
    posts = [
        ('/metadata/save', {'key': 'a/b', 'title': 'x'}),
        ('/metadata/purge', {'key': 'a/b'}),
        ('/metadata/purge-bulk', {'keys': ['a/b']}),
        ('/metadata/purge-duplicates', {}),
        ('/metadata/prune-names', {}),
        ('/people/save', {'filename': 'a.jpg'}),
        ('/people/purge', {'filename': 'a.jpg'}),
        ('/people/restore', {'filename': 'a.jpg'}),
        ('/people/gender', {'filename': 'a.jpg', 'gender': 'female'}),
        ('/people/lookup', {'filename': 'a.jpg', 'source': 'IAFD'}),
        ('/people/bulk-fetch', {'source': 'IAFD', 'filenames': ['a.jpg']}),
        ('/logos/api/purge', {'rel': 'x.png'}),
        ('/logos/api/purge-all', {}),
        ('/logos/api/rescan', {}),
        ('/queue/api/flush', {'kind': 'search'}),
        ('/queue/api/resume', {}),
    ]
    for path, body in posts:
        assert member.post(path, json=body).status_code == 403, path


def test_read_only_pages_still_load_for_non_admins(member: TestClient) -> None:
    for path in ('/metadata', '/people', '/logos', '/queue'):
        assert member.get(path).status_code == 200, path


def test_the_nav_logout_button_cannot_stretch(member: TestClient) -> None:
    body = member.get('/people').text
    nav_css = body.split('.nav-logout {')[1].split('}')[0]
    assert 'width: auto' in nav_css
    assert 'flex: none' in nav_css
