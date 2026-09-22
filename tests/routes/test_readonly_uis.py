from __future__ import annotations

import os
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from phoenixadult.utils.cache import layout as cache_layout
from tests.support import authed_client


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
    assert 'var IS_ADMIN = false;' in body
    assert 'id="purgeAllBtn"' not in body
    assert 'id="dupBtn"' not in body
    assert 'id="pruneBtn"' not in body
    assert 'id="refreshAllBtn"' not in body
    assert 'id="exportBtn"' in body, 'export is read-only and stays available'
    admin_body = authed_client().get('/metadata').text
    assert 'id="purgeAllBtn"' in admin_body and 'var IS_ADMIN = true;' in admin_body
    assert 'id="refreshAllBtn"' in admin_body


def test_metadata_edit_is_read_only(member: TestClient) -> None:
    from phoenixadult.utils.cache import scene_store

    md = {'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': 'Scene', 'studio': 'Studio'}
    payload = {'MediaContainer': {'identifier': 'i', 'size': 1, 'Metadata': [md]}}
    scene_store.upsert(
        'Studio', 'cur1', cache_layout.scene_hash_for('Studio', 'cur1'), cache_layout.bundle_path(cache_layout.scene_hash_for('Studio', 'cur1')), payload
    )
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
    assert member.get('/people/api/entries').json()['total'] == 1, 'the fixture person should be listed'
    assert 'var IS_ADMIN = false;' in body
    assert 'id="bulkBtn"' not in body
    assert 'id="bulkSource"' not in body
    assert 'Serving people images via' not in body
    assert "(IS_ADMIN ? 'Edit' : 'View')" in body, 'the card builder decides Edit vs View from IS_ADMIN'
    assert 'purgeBtn = IS_ADMIN ?' in body and 'if (IS_ADMIN) {' in body, 'purge and restore are admin-gated'

    admin_body = authed_client().get('/people').text
    assert 'var IS_ADMIN = true;' in admin_body


def test_logos_and_queue_hide_their_write_controls(member: TestClient) -> None:
    logos = member.get('/logos').text
    logos_markup = logos.split('<script>')[0]
    assert 'id="rescanBtn"' not in logos_markup
    assert 'onclick="purgeAll()"' not in logos_markup
    assert 'var IS_ADMIN = false;' in logos
    assert 'onclick="purgeAll()"' in authed_client().get('/logos').text

    queue = member.get('/queue').text
    assert 'flushKind(' not in queue.split('<script>')[0]
    assert 'togglePause(' not in queue.split('<script>')[0], 'pause/resume is a write control and hides from non-admins'
    assert 'var IS_ADMIN = false;' in queue
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
        ('/logos/api/template', {'studio': 'Vixen', 'template': 'https://x/y.png'}),
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


def test_base_html_is_the_only_place_the_components_are_declared() -> None:
    import re

    admin = authed_client()
    for path in ('/metadata', '/people', '/logos', '/queue', '/searches'):
        body = admin.get(path).text
        for component in ('pa-btn', 'pa-card', 'pa-badge', 'pa-input'):
            hits = re.findall(rf'^\s*\.{component}\s*\{{', body, re.M)
            assert len(hits) == 1, f'{path} declares .{component} {len(hits)} times; base.html owns it'
        assert not re.search(r'^\s*button\s*\{', body, re.M), f'{path} styles bare <button>, which every component then has to undo'
        assert not re.search(r'outline:\s*(0|none)', body), f'{path} cancels the keyboard focus ring'


def test_source_json_is_admin_only(member: TestClient) -> None:
    key = _seed_snapshot()
    assert member.get(f'/metadata/source-json?key={key}').status_code == 403
    admin = authed_client()
    r = admin.get(f'/metadata/source-json?key={key}')
    assert r.status_code == 200
    assert r.json() == {'ok': True, 'json': {'title': 'Scene', 'poster': '/img/x.jpg'}}


def _seed_snapshot() -> str:
    import json

    from phoenixadult.utils.cache import scene_store
    from phoenixadult.utils.helpers.ids import b64url_encode

    cur_id = b64url_encode(json.dumps({'title': 'Scene', 'poster': '/img/x.jpg'}))
    md = {'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': 'Scene', 'studio': 'Studio'}
    payload = {'MediaContainer': {'identifier': 'i', 'size': 1, 'Metadata': [md]}}
    scene_hash = cache_layout.scene_hash_for('Studio', cur_id)
    scene_store.upsert('Studio', cur_id, scene_hash, cache_layout.bundle_path(scene_hash), payload)
    return str(scene_store.snapshot_state('Studio', cur_id)['key'])


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
    _assert_page_scripts_load(admin, '/searches', 'admin-searches', tmp_path)
    _assert_page_scripts_load(admin, '/logos/add', 'admin-logos-add', tmp_path)


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
    assert 'paintSfwToggle();\n    installLockUI();\n    load();' in body
    assert "if (qs('a-img'))" in body


def test_the_nav_logout_button_cannot_stretch(member: TestClient) -> None:
    body = member.get('/people').text
    nav_css = body.split('.nav-logout {')[1].split('}')[0]
    assert 'width: auto' in nav_css
    assert 'flex: none' in nav_css


def test_every_template_stylesheet_has_balanced_braces() -> None:
    import re
    from pathlib import Path

    html_dir = Path(__file__).resolve().parents[2] / 'phoenixadult' / 'routes' / 'html'
    for path in sorted(html_dir.glob('*.html')):
        for block in re.findall(r'<style>(.*?)</style>', path.read_text(encoding='utf-8'), re.S):
            depth = 0
            for line in block.splitlines():
                depth += line.count('{') - line.count('}')
                assert depth >= 0, f'{path.name}: stray closing brace at {line.strip()!r}'
            assert depth == 0, f'{path.name}: unbalanced braces (net {depth})'


def test_page_headings_share_one_position_and_spacing() -> None:
    import re

    client = authed_client()
    canonical = 'h1 { font-size: var(--text-xl); font-weight: 700; letter-spacing: -0.01em; color: var(--heading-text); margin: 0 0 4px; }'

    for path in ('/metadata', '/people', '/logos', '/queue', '/searches', '/account'):
        css = ' '.join(re.findall(r'<style>(.*?)</style>', client.get(path).text, re.S))
        assert canonical in css, f'{path} does not use the shared heading rule'
        assert re.findall(r'h1\s*\{[^}]*\}', css) == [canonical], f'{path} restates the shared heading rule'
        assert re.search(r'body\s*\{[^}]*padding:\s*24px', css), f'{path} uses a different body padding'


_VOID = frozenset({'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'})
_OPTIONAL_END = frozenset({'dd', 'dt', 'li', 'optgroup', 'option', 'p', 'rp', 'rt', 'tbody', 'td', 'tfoot', 'th', 'thead', 'tr'})


class _TagBalance(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, int]] = []
        self.problems: list[str] = []

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag not in _VOID:
            self.stack.append((tag, self.getpos()[0]))

    def handle_startendtag(self, tag: str, attrs: object) -> None:
        return

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID:
            return
        for depth in range(len(self.stack) - 1, -1, -1):
            if self.stack[depth][0] == tag:
                for open_tag, line in self.stack[depth + 1 :]:
                    if open_tag not in _OPTIONAL_END:
                        self.problems.append(f'<{open_tag}> opened on line {line} is still open at </{tag}>')
                del self.stack[depth:]
                return
        self.problems.append(f'</{tag}> on line {self.getpos()[0]} closes a tag that was never opened')

    def unclosed(self) -> list[str]:
        return [f'<{tag}> opened on line {line} is never closed' for tag, line in self.stack if tag not in _OPTIONAL_END]


def _structure_problems(html: str) -> list[str]:
    parser = _TagBalance()
    parser.feed(html)
    parser.close()
    return parser.problems + parser.unclosed()


def test_every_page_is_structurally_balanced() -> None:
    from fastapi.testclient import TestClient as _Client

    from phoenixadult.app_factory import create_app as _create

    admin = authed_client()
    anon = _Client(_create())
    pages = [(admin, p) for p in ('/metadata', '/people', '/logos', '/logos/add', '/queue', '/searches', '/config', '/account')]
    pages += [(anon, '/login'), (anon, '/setup')]
    for client, path in pages:
        problems = _structure_problems(client.get(path).text)
        assert not problems, f'{path} is malformed:\n  ' + '\n  '.join(problems[:6])


def test_the_balance_check_catches_a_stray_tag() -> None:
    good = '<html><body><main><div class="x">hi</div></main><script>if (1 < 2) {}</script></body></html>'
    assert _structure_problems(good) == []
    assert _structure_problems(good.replace('<main>', '<main><script>')), 'an unclosed script must be reported'
    assert _structure_problems('<html><body><div><span>x</div></body></html>'), 'a crossed tag must be reported'
    assert _structure_problems('<html><body></div></body></html>'), 'an orphan close must be reported'
