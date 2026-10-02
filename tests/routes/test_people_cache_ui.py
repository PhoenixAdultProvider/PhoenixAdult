from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from phoenixadult.utils.cache import layout as cache_layout
from tests.support import authed_client


def test_requires_auth() -> None:
    assert TestClient(create_app()).get('/people', headers={'accept': 'application/json'}).status_code == 401
    page = authed_client().get('/people')
    assert page.status_code == 200
    assert 'People Cache' in page.text


def test_restore_requires_filename(monkeypatch: pytest.MonkeyPatch) -> None:
    client = authed_client()
    r = client.post('/people/restore', json={})
    assert r.status_code == 400


def test_gender_validates() -> None:
    client = authed_client()
    assert client.post('/people/gender', json={'gender': 'male'}).status_code == 400
    assert client.post('/people/gender', json={'filename': 'a.jpg', 'gender': 'x'}).status_code == 400
    r = client.post('/people/gender', json={'filename': 'unknown.jpg', 'gender': 'female'})
    assert r.status_code == 200 and r.json()['ok'] is False


def test_apostrophe_filename_renders_safe_buttons(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    from pathlib import Path

    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    d = Path(str(tmp_path)) / 'people' / 'actors' / 'female'
    d.mkdir(parents=True)
    (d / "actor.april-o'neil_female.jpg").write_bytes(b'x')

    client = authed_client()
    page = client.get('/people')
    assert page.status_code == 200
    rows = client.get('/people/api/entries', params={'type': 'actors-female'}).json()['entries']
    assert rows[0]['filename'] == "actor.april-o'neil_female.jpg"
    assert 'data-fn="' + "' + esc(e.filename)" in page.text, 'the card builder must escape the filename'
    assert 'onclick="purge(' not in page.text
    assert 'onclick="restore(' not in page.text
    assert 'onclick="setGender(' not in page.text


def test_cards_are_hidden_until_the_tab_filter_runs(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    from pathlib import Path

    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    d = Path(str(tmp_path)) / 'people' / 'actors' / 'male'
    d.mkdir(parents=True)
    (d / 'actor.voodoo-child_male.jpg').write_bytes(b'x')

    page = authed_client().get('/people')
    assert 'display: none; }' in page.text.split('.card {')[1].split('.card.gf')[0]


def test_listing_is_built_from_the_index_tables(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    from pathlib import Path

    from phoenixadult.routes import people_cache_routes as pcr
    from phoenixadult.utils.images import face_crop_log

    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    root = Path(str(tmp_path)) / 'people'
    d = root / 'actors' / 'female'
    d.mkdir(parents=True)
    (d / 'actor.jane-doe_female.jpg').write_bytes(b'x')
    (root / 'directors').mkdir()
    (root / 'directors' / 'director.greg-lansky.png').write_bytes(b'x')
    (root / 'originals').mkdir()
    (root / 'originals' / 'actor.jane-doe_female.webp').write_bytes(b'x')
    face_crop_log.record(
        str(d),
        name='Jane Doe',
        filename='actor.jane-doe_female.jpg',
        base='actor.jane-doe_female',
        orig_ext='.webp',
        upstream_url='https://up/j.webp',
        cropped=True,
    )

    entries = pcr._list_people(str(root))
    by_file = {e['filename']: e for e in entries}
    assert set(by_file) == {'actor.jane-doe_female.jpg', 'director.greg-lansky.png'}
    jane = by_file['actor.jane-doe_female.jpg']
    assert jane['relpath'] == 'actors/female/actor.jane-doe_female.jpg'
    assert jane['type'] == 'actors-female' and jane['role'] == 'actor' and jane['gender'] == 'female'
    assert jane['name'] == 'Jane Doe' and jane['cropped'] is True and jane['upstream_url'] == 'https://up/j.webp'
    assert jane['ts'] == face_crop_log.entry_for(str(d), 'actor.jane-doe_female.jpg')['ts'] and jane['mtime'] > 0  # type: ignore[index]
    greg = by_file['director.greg-lansky.png']
    assert greg['type'] == 'directors' and greg['name'] == 'Greg Lansky' and greg['cropped'] is False and greg['upstream_url'] == ''


def test_folder_derived_names_use_title_case_not_naive_title(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    from pathlib import Path

    from phoenixadult.routes import people_cache_routes as pcr

    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    root = Path(str(tmp_path)) / 'people'
    d = root / 'actors' / 'female'
    d.mkdir(parents=True)
    (d / 'actor.ashley-mccoy_female.jpg').write_bytes(b'x')
    (d / 'actor.whitney-oc_female.jpg').write_bytes(b'x')
    (d / 'actor.lasirena69_female.jpg').write_bytes(b'x')

    by_file = {e['filename']: e for e in pcr._list_people(str(root))}
    assert by_file['actor.ashley-mccoy_female.jpg']['name'] == 'Ashley McCoy'
    assert by_file['actor.whitney-oc_female.jpg']['name'] == 'Whitney OC'
    assert by_file['actor.lasirena69_female.jpg']['name'] == 'LaSirena69'


def test_a_stored_crop_log_name_is_recased_for_display(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    from pathlib import Path

    from phoenixadult.routes import people_cache_routes as pcr
    from phoenixadult.utils.images import face_crop_log

    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    root = Path(str(tmp_path)) / 'people'
    d = root / 'actors' / 'female'
    d.mkdir(parents=True)
    (d / 'actor.whitney-oc_female.jpg').write_bytes(b'x')
    face_crop_log.record(
        str(d),
        name='Whitney Oc',
        filename='actor.whitney-oc_female.jpg',
        base='actor.whitney-oc_female',
        orig_ext='.jpg',
        upstream_url='https://u/x.jpg',
        cropped=False,
    )

    entry = next(e for e in pcr._list_people(str(root)) if e['filename'] == 'actor.whitney-oc_female.jpg')
    assert entry['name'] == 'Whitney OC'


def test_listing_falls_back_to_files_when_the_index_is_empty(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    from pathlib import Path

    from phoenixadult.routes import people_cache_routes as pcr
    from phoenixadult.utils import db
    from phoenixadult.utils.people import cache as pcache

    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    d = Path(str(tmp_path)) / 'people' / 'actors' / 'male'
    d.mkdir(parents=True)
    (d / 'actor.bob_male.jpg').write_bytes(b'x')

    db.connect()
    monkeypatch.setattr(pcache._index, '_key', (pcache.env.people_cache_dir, pcache.env.state_db_path))
    entries = pcr._list_people(str(Path(str(tmp_path)) / 'people'))
    assert [e['relpath'] for e in entries] == ['actors/male/actor.bob_male.jpg']
    assert entries[0]['type'] == 'actors-male'


def test_cards_carry_cropped_flag_and_toggle_exists(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    from pathlib import Path

    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    d = Path(str(tmp_path)) / 'people' / 'actors' / 'female'
    d.mkdir(parents=True)
    (d / 'actor.jane-doe_female.jpg').write_bytes(b'x')

    page = authed_client().get('/people')
    assert authed_client().get('/people/api/entries').json()['entries'][0]['cropped'] is False
    assert 'id="cropToggle"' in page.text


def test_people_list_is_paged_like_the_metadata_cache() -> None:
    page = authed_client().get('/people')
    assert 'id="pager"' in page.text
    assert 'id="prevBtn"' in page.text and 'id="nextBtn"' in page.text and 'id="pageInfo"' in page.text
    assert 'var PAGE_SIZE = 200;' in page.text
    assert 'function prevPage()' in page.text and 'function nextPage()' in page.text


def test_only_the_current_page_of_people_images_is_hydrated() -> None:
    page = authed_client().get('/people')
    assert "const shown = card.style.display === 'block';" in page.text
    assert "if(SFW || !shown) img.removeAttribute('src');" in page.text


def test_paging_reset_and_sfw_stay_visible_on_mobile_on_both_pages() -> None:
    client = authed_client()
    for path in ('/people', '/metadata'):
        shared = client.get(path).text.split('Shared top-of-page skeleton')[1]
        assert '.controls { display: block; }' in shared
        assert '.filters { display: none; grid-template-columns: 1fr; }' in shared
        assert '.tb-actions { display: none; }' in shared
        assert '.controls.actions-open .tb-actions { display: grid; gap: 8px; width: 100%; order: -3; }' in shared
        assert '.toolbar::before { content: ""; flex: 1 1 100%; order: -1;' in shared, 'the divider sits below both panels'
        assert '.controls.open .toolbar > .tb-filter-toggle { display: flex; }' in shared
        assert '#pager { width: 100%; justify-content: space-between; }' in shared


def test_the_shared_toolbar_partial_is_the_only_implementation() -> None:
    people = authed_client().get('/people').text
    metadata = authed_client().get('/metadata').text
    cluster = '<button class="pa-btn pa-btn--lg" id="resetBtn" onclick="resetFilters()">Reset Filters</button>'
    for body in (people, metadata):
        assert cluster in body
        assert body.index('id="resetBtn"') < body.index('id="sfwToggle"')
        assert '<button class="pa-btn pa-btn--lg" id="prevBtn" onclick="prevPage()">Previous</button>' in body
        assert body.count('    .pa-btn {\n') == 1, '.pa-btn belongs to base.html alone'
        assert 'height: 32px;' in body.split('    .pa-btn {\n')[1].split('}')[0]


def test_page_folds_tabs_and_filters_behind_one_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    page = authed_client().get('/people')
    assert 'filtersToggle' in page.text
    assert '<div class="controls" id="controls">' in page.text
    assert '.controls.open .filters { display: grid; }' in page.text
    assert 'controls.classList.toggle(cls)' in page.text
    assert 'controls.classList.remove(other);' in page.text, 'one panel at a time'
    assert "function toggleActions() { return paDisclosure('actions-open', 'actionsToggle'); }" in page.text
    assert 'updateFiltersToggle()' in page.text


def test_people_page_offers_sfw_mode_and_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    page = authed_client().get('/people')
    assert 'id="sfwToggle"' in page.text
    assert 'id="resetBtn"' in page.text
    assert "const SFW_KEY = 'metadata-sfw';" in page.text
    assert 'function resetFilters()' in page.text
    assert 'body.sfw .imgs { display: none; }' in page.text
    page_css = next(block for block in page.text.split('<style>') if '.card {' in block)
    assert '::after' not in page_css


def test_people_images_are_not_fetched_until_hydrated(monkeypatch: pytest.MonkeyPatch) -> None:
    import re

    page = authed_client().get('/people')
    assert not re.search(r'<img [^>]*\ssrc=', page.text)
    assert 'img.dataset.src' in page.text


def test_resetting_people_filters_leaves_sfw_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    page = authed_client().get('/people')
    body = page.text[page.text.index('function resetFilters()') :]
    assert 'SFW' not in body[: body.index('showTab(curTab)')]


def _seed_scene(title: str, cur: str, studio: str, tagline: str, date: str, cast: list[str]) -> None:
    from phoenixadult.utils.cache import scene_store

    md: dict[str, object] = {
        'type': 'movie',
        'ratingKey': 'rk',
        'guid': 'g',
        'title': title,
        'studio': studio,
        'originallyAvailableAt': date,
        'Role': [{'tag': name} for name in cast],
    }
    if tagline:
        md['tagline'] = tagline
    scene_store.upsert(
        studio,
        cur,
        cache_layout.scene_hash_for(studio, cur),
        cache_layout.bundle_path(cache_layout.scene_hash_for(studio, cur)),
        {'MediaContainer': {'identifier': 'i', 'size': 1, 'Metadata': [md]}},
    )


@pytest.fixture
def _person_cache(monkeypatch: pytest.MonkeyPatch, tmp_path):  # type: ignore[no-untyped-def]
    from pathlib import Path

    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    headshot = Path(str(tmp_path)) / 'people' / 'actors' / 'female' / 'actor.jane-doe_female.jpg'
    headshot.parent.mkdir(parents=True, exist_ok=True)
    headshot.write_bytes(b'\xff\xd8\xff\xdb' + b'0' * 64)
    yield


def test_the_edit_page_lists_the_scenes_that_credit_the_person(_person_cache: None) -> None:
    _seed_scene('Later Scene', 'c1', 'Brazzers', 'Baby Got Boobs', '2024-06-01', ['Jane Doe'])
    _seed_scene('Earlier Scene', 'c2', 'Vixen', '', '2023-01-05', ['Jane Doe', 'Someone Else'])
    _seed_scene('Not Hers', 'c3', 'Vixen', '', '2025-01-05', ['Someone Else'])

    page = authed_client().get('/people/edit', params={'filename': 'actor.jane-doe_female.jpg'})

    assert page.status_code == 200
    body = page.text
    assert '<legend>Scenes</legend>' in body
    assert body.index('Later Scene') < body.index('Earlier Scene')
    assert 'Not Hers' not in body
    assert 'Baby Got Boobs' in body and 'Brazzers' in body and '2024-06-01' in body
    assert 'href="/metadata/edit?key=scenes/' in body


def test_the_edit_page_resolves_a_person_by_name(_person_cache: None) -> None:
    page = authed_client().get('/people/edit', params={'name': 'jane doe'})
    assert page.status_code == 200
    assert 'Jane Doe' in page.text

    missing = authed_client().get('/people/edit', params={'name': 'Nobody Here'})
    assert missing.status_code == 404


def test_the_edit_page_says_so_when_no_snapshot_credits_the_person(_person_cache: None) -> None:
    _seed_scene('Not Hers', 'c9', 'Vixen', '', '2025-01-05', ['Someone Else'])

    body = authed_client().get('/people/edit', params={'filename': 'actor.jane-doe_female.jpg'}).text

    assert 'No cached snapshot credits this person.' in body


def test_the_scene_list_is_skipped_when_the_cache_is_off(_person_cache: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'false')

    body = authed_client().get('/people/edit', params={'filename': 'actor.jane-doe_female.jpg'}).text

    assert 'The snapshot cache is off' in body


def test_cards_are_wide_enough_that_names_never_break(_person_cache: None) -> None:
    body = authed_client().get('/people').text
    assert 'minmax(460px, 1fr)' in body
    assert '.hd b { white-space: nowrap; }' in body
    assert 'flex-wrap: wrap' in body


def test_the_list_can_be_filtered_by_recorded_source(_person_cache: None) -> None:
    from pathlib import Path

    from phoenixadult.config.env import env
    from phoenixadult.utils.images import face_crop_log

    folder = str(Path(env.people_cache_dir) / 'actors' / 'female')
    face_crop_log.record(
        folder,
        name='Jane Doe',
        filename='actor.jane-doe_female.jpg',
        base='actor.jane-doe_female',
        orig_ext='.jpg',
        upstream_url='https://iafd.com/j.jpg',
        cropped=True,
        source='IAFD',
    )

    body = authed_client().get('/people').text

    assert 'id="sourceFilter"' in body
    assert '<option value="IAFD">IAFD</option>' in body
    assert '<option value="">Any Source</option>' in body
    listed = authed_client().get('/people/api/entries', params={'source': 'IAFD'}).json()
    assert listed['total'] == 1 and listed['entries'][0]['source'] == 'IAFD'
    assert 'IAFD' in authed_client().get('/people/api/entries').json()['sources']


def test_the_list_offers_a_generic_only_toggle(_person_cache: None) -> None:
    body = authed_client().get('/people').text
    assert 'id="genericToggle">Generic Only</button>' in body
    assert "params.set('generic', '1')" in body
    assert 'genericOnly' in body
    listed = authed_client().get('/people/api/entries', params={'generic': '1'}).json()
    assert all(e['source'] == 'Generic' for e in listed['entries'])


def test_the_edit_page_hides_its_previews_in_sfw_mode(_person_cache: None) -> None:
    body = authed_client().get('/people/edit', params={'filename': 'actor.jane-doe_female.jpg'}).text
    assert 'id="sfwToggle"' in body
    assert "const SFW_KEY = 'metadata-sfw';" in body
    assert 'body.sfw #previewCard { display: none; }' in body
    assert 'id="cachedImg" data-src=' in body
    assert 'id="cachedImg" src=' not in body


def test_the_edit_page_offers_every_known_source(_person_cache: None) -> None:
    from phoenixadult.utils.people.image_source import KNOWN_SOURCES

    body = authed_client().get('/people/edit', params={'filename': 'actor.jane-doe_female.jpg'}).text

    assert 'id="f-recorded"' in body
    assert all(f'"{name}"' in body for name in KNOWN_SOURCES)
    assert "var UNCROPPED_SOURCES = ['IAFD'];" in body
    assert "qs('f-cropped').checked = false;" in body


def test_saving_relabels_the_recorded_source_without_touching_the_image(_person_cache: None) -> None:
    from pathlib import Path

    from phoenixadult.config.env import env
    from phoenixadult.routes import people_cache_routes as pcr
    from phoenixadult.utils.images import face_crop_log

    folder = str(Path(env.people_cache_dir) / 'actors' / 'female')
    face_crop_log.record(
        folder,
        name='Jane Doe',
        filename='actor.jane-doe_female.jpg',
        base='actor.jane-doe_female',
        orig_ext='.jpg',
        upstream_url='https://cdn/j.jpg',
        cropped=False,
        source='Scene',
    )
    client = authed_client()
    body = {'filename': 'actor.jane-doe_female.jpg', 'upstream_url': 'https://cdn/j.jpg', 'cropped': False, 'recorded_source': 'IAFD'}

    r = client.post('/people/save', json=body)

    assert r.status_code == 200 and r.json() == {'ok': True, 'changed': True}
    assert pcr._find_entry('actor.jane-doe_female.jpg')['source'] == 'IAFD'

    again = client.post('/people/save', json=body)
    assert again.json() == {'ok': True, 'changed': False}


def test_saving_rejects_a_source_it_does_not_know(_person_cache: None) -> None:
    client = authed_client()
    body = {'filename': 'actor.jane-doe_female.jpg', 'upstream_url': 'https://cdn/j.jpg', 'cropped': False, 'recorded_source': 'Nowhere'}

    r = client.post('/people/save', json=body)

    assert r.status_code == 400 and 'Nowhere' in r.json()['error']


def test_the_list_offers_a_single_name_toggle(_person_cache: None, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from pathlib import Path

    from phoenixadult.config.env import env
    from phoenixadult.utils.images import face_crop_log

    folder = Path(env.people_cache_dir) / 'actors' / 'female'
    for slug in ('haley', 'kate-smith', 'la-sirena'):
        (folder / f'actor.{slug}_female.jpg').write_bytes(b'\xff\xd8\xff\xdb' + b'0' * 64)
    face_crop_log.record(
        str(folder),
        name='LaSirena69',
        filename='actor.la-sirena_female.jpg',
        base='actor.la-sirena_female',
        orig_ext='.jpg',
        upstream_url='',
        cropped=False,
    )

    body = authed_client().get('/people').text

    assert 'id="singleToggle">Single Name</button>' in body
    assert "params.set('single', '1')" in body
    client = authed_client()
    assert client.get('/people/api/entries', params={'single': '1'}).json()['total'] == 2
    everyone = client.get('/people/api/entries').json()['entries']
    assert sum(1 for e in everyone if not e['single']) == 2


def test_every_filter_toggle_has_an_active_style(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    body = authed_client().get('/people').text

    for css in ('.croptoggle.on', '.noupstream.on', '.genericonly.on', '.singleonly.on'):
        assert css in body, f'{css} has no active style'


def test_source_filter_is_narrowed_to_the_visible_tab(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    body = authed_client().get('/people').text

    assert 'function paintSourceOptions(present, blank)' in body
    assert 'paintSourceOptions(j.sources || [], !!j.has_unrecorded);' in body
    assert "if (cur && cur.hidden) picker.value = '';" in body


def test_mobile_shows_four_controls_with_the_rest_behind_two_disclosures() -> None:
    for path in ('/people', '/metadata'):
        page = authed_client().get(path).text
        assert 'id="filtersToggle"' in page and 'id="actionsToggle"' in page
        assert '<div class="tb-actions">' in page, f'{path} does not group its bulk actions'
        assert '.tb-actions { display: contents; }' in page, f'{path} would reflow on desktop'
        assert '.tb-actions { display: none; }' in page
        assert '.controls.actions-open .tb-actions { display: grid; gap: 8px; width: 100%; order: -3; }' in page
        assert "function toggleActions() { return paDisclosure('actions-open', 'actionsToggle'); }" in page

    metadata = authed_client().get('/metadata').text
    for button_id in ('dupToggle', 'potToggle'):
        rendered = metadata.split(f'id="{button_id}"')[0].rsplit('<button', 1)[1]
        assert 'tb-filter-toggle' in rendered, f'{button_id} should fold behind Filters, not Actions'
    for button_id in ('dupBtn', 'pruneBtn', 'exportBtn', 'refreshAllBtn', 'purgeAllBtn'):
        assert button_id in metadata.split('<div class="tb-actions">')[1].split('</div>')[0]

    people = authed_client().get('/people').text
    actions = people.split('<div class="tb-actions">')[1].split('{% endif %}')[0]
    assert 'id="bulkBtn"' in actions


def test_the_control_strip_is_one_button_size() -> None:
    import re

    for path in ('/metadata', '/people', '/logos'):
        body = authed_client().get(path).text
        strip = body.split('<div class="toolbar">')[1].split('</div>\n  </div>')[0]
        plain = [m for m in re.findall(r'class="(pa-btn[^"]*)"', strip) if 'pa-btn--lg' not in m and 'pa-btn--sm' not in m]
        assert not plain, f'{path} still has small control buttons: {plain}'


def test_the_search_row_can_carry_its_own_filters() -> None:
    people = authed_client().get('/people').text
    row = people.split('<div class="searchbar">')[1].split('</div>\n  <div class="controls"')[0]
    assert 'id="sourceFilter"' in row, 'Source sits beside the search box'

    logos = authed_client().get('/logos').text
    row = logos.split('<div class="searchbar">')[1].split('<div class="controls"')[0]
    assert 'id="unmatched"' in row and 'id="bgBtn"' in row, 'Registry and Backdrop sit beside the search box'
    assert '.searchbar .sr-aux .pa-input { width: auto; min-width: 150px; }' in logos, 'aux controls size to content'
