from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

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
    assert 'id="refreshAllBtn"' not in body
    assert 'id="exportBtn"' in body, 'export is read-only and stays available'
    admin_body = authed_client().get('/metadata').text
    assert 'id="purgeAllBtn"' in admin_body and 'const IS_ADMIN = true;' in admin_body
    assert 'id="refreshAllBtn"' in admin_body


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


@pytest.fixture
def _one_cached_person(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('IMAGE_DIR', str(tmp_path / 'images'))
    folder = tmp_path / 'images' / 'people' / 'actors' / 'female'
    folder.mkdir(parents=True)
    (folder / 'actor.jane-doe_female.jpg').write_bytes(b'x')


def test_people_hides_writes_and_the_serving_line(member: TestClient, _one_cached_person: None) -> None:
    body = member.get('/people').text
    assert 'class="card' in body, 'the fixture person should render a card to assert against'
    assert 'id="bulkBtn"' not in body
    assert 'id="bulkSource"' not in body
    assert 'Serving people images via' not in body
    assert '>View</button>' in body and '>Edit</button>' not in body
    assert 'class="purge"' not in body
    assert 'class="restore"' not in body

    admin_body = authed_client().get('/people').text
    assert '>Edit</button>' in admin_body and 'class="purge"' in admin_body


def test_logos_and_queue_hide_their_write_controls(member: TestClient) -> None:
    logos = member.get('/logos').text
    logos_markup = logos.split('<script>')[0]
    assert 'id="rescanBtn"' not in logos_markup
    assert 'onclick="purgeAll()"' not in logos_markup
    assert 'const IS_ADMIN = false;' in logos
    assert 'onclick="purgeAll()"' in authed_client().get('/logos').text

    queue = member.get('/queue').text
    assert 'flushKind(' not in queue.split('<script>')[0]
    assert 'togglePause(' not in queue.split('<script>')[0], 'pause/resume is a write control and hides from non-admins'
    assert 'const IS_ADMIN = false;' in queue
    assert "flushKind('search')" in authed_client().get('/queue').text


def test_write_endpoints_reject_non_admins(member: TestClient) -> None:
    posts = [
        ('/metadata/save', {'key': 'a/b', 'title': 'x'}),
        ('/metadata/purge', {'key': 'a/b'}),
        ('/metadata/purge-bulk', {'keys': ['a/b']}),
        ('/metadata/refresh', {'key': 'a/b'}),
        ('/metadata/refresh-bulk', {'keys': ['a/b']}),
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
        ('/queue/api/pause', {'kind': 'search'}),
        ('/queue/api/remove', {'key': 'x'}),
        ('/queue/api/resume', {}),
    ]
    for path, body in posts:
        assert member.post(path, json=body).status_code == 403, path


def test_read_only_pages_still_load_for_non_admins(member: TestClient) -> None:
    for path in ('/metadata', '/people', '/logos', '/queue'):
        assert member.get(path).status_code == 200, path


def _seed_snapshot() -> str:
    from phoenixadult.utils import cache as metadata_cache
    from phoenixadult.utils.cache import scene_store

    md = {'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': 'Scene', 'studio': 'Studio'}
    payload = {'MediaContainer': {'identifier': 'i', 'size': 1, 'Metadata': [md]}}
    scene_hash = metadata_cache._hash('Studio', 'cur1')
    scene_store.upsert('Studio', 'cur1', scene_hash, metadata_cache.bundle_path(scene_hash), payload)
    return str(scene_store.snapshot_state('Studio', 'cur1')['key'])


_HARNESS = Path(__file__).parent / '_js' / 'page_load_harness.js'


def _assert_page_scripts_load(client: TestClient, path: str, label: str, tmp_path: Path) -> None:
    html = client.get(path).text
    page = tmp_path / f'{label}.html'
    page.write_text(html, encoding='utf-8')
    result = subprocess.run(['node', str(_HARNESS), str(page)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, f'{path} ({label}) failed at load: {result.stdout.strip()} {result.stderr.strip()}'


def _in_ci() -> bool:
    return bool(os.environ.get('CI') or os.environ.get('GITHUB_ACTIONS'))


@pytest.mark.skipif(shutil.which('node') is None and not _in_ci(), reason='node is needed to execute the page scripts')
def test_every_page_script_survives_load_for_both_roles(member: TestClient, tmp_path: Path) -> None:
    assert shutil.which('node'), 'CI installs nodejs for this test — a missing node must fail, not skip'
    key = _seed_snapshot()
    admin = authed_client()
    for path in ('/metadata', f'/metadata/edit?key={key}', '/people', '/logos', '/queue', '/config', '/account'):
        slug = path.strip('/').replace('/', '-').split('?')[0]
        _assert_page_scripts_load(member, path, f'member-{slug}', tmp_path)
        _assert_page_scripts_load(admin, path, f'admin-{slug}', tmp_path)


def test_a_lone_view_button_is_centered(member: TestClient) -> None:
    metadata = member.get('/metadata').text
    assert '.c-actions:has(> button:only-child)' in metadata
    people = member.get('/people').text
    assert '.actions:has(> button:only-child){justify-content:center}' in people


def test_duplicate_toggles_are_admin_only(member: TestClient) -> None:
    body = member.get('/metadata').text
    assert 'id="potToggle"' not in body
    assert 'id="dupToggle"' not in body
    admin_body = authed_client().get('/metadata').text
    assert 'id="potToggle"' in admin_body and 'id="dupToggle"' in admin_body


def test_the_viewer_still_populates_and_labels_sfw(member: TestClient) -> None:
    body = member.get(f'/metadata/edit?key={_seed_snapshot()}').text
    assert body.rstrip().endswith('</html>')
    assert 'paintSfwToggle();\n    load();' in body
    assert "if (qs('a-img'))" in body


def test_the_nav_logout_button_cannot_stretch(member: TestClient) -> None:
    body = member.get('/people').text
    nav_css = body.split('.nav-logout {')[1].split('}')[0]
    assert 'width: auto' in nav_css
    assert 'flex: none' in nav_css
