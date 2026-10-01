from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from phoenixadult.utils.images import logo_cache
from tests.support import authed_client


@pytest.fixture()
def _cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    root = tmp_path / 'logos'
    (root / 'brazzers').mkdir(parents=True)
    (root / 'brazzers' / 'logo.baby-got-boobs.png').write_bytes(b'png')
    logo_cache.invalidate()
    return root


def test_requires_auth_and_lists_with_site_names(_cache: Path) -> None:
    assert TestClient(create_app()).get('/logos', headers={'accept': 'application/json'}).status_code == 401
    client = authed_client()
    page = client.get('/logos')
    assert page.status_code == 200 and 'Logo Cache' in page.text

    data = client.get('/logos/api/list').json()
    assert data['logos'][0]['slug'] == 'babygotboobs'
    assert data['logos'][0]['site'] == 'Baby Got Boobs'
    assert data['logos'][0]['url'].startswith('/images/local/logos/brazzers/logo.baby-got-boobs.png?v=')


def test_purge_endpoints(_cache: Path) -> None:
    client = authed_client()
    assert client.post('/logos/api/purge', json={}).status_code == 400
    assert client.post('/logos/api/purge', json={'rel': 'nope.png'}).status_code == 404
    assert client.post('/logos/api/purge', json={'rel': 'brazzers/logo.baby-got-boobs.png'}).status_code == 200
    assert client.post('/logos/api/purge-all').json()['purged'] == 0


def test_local_route_serves_logo_cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    (tmp_path / 'logos' / 'brazzers').mkdir(parents=True)
    (tmp_path / 'logos' / 'brazzers' / 'logo.brazzers.png').write_bytes(b'pngbytes')
    client = authed_client()
    r = client.get('/images/local/logos/brazzers/logo.brazzers.png')
    assert r.status_code == 200 and r.content == b'pngbytes'
    assert client.get('/images/local/logos/../secrets.png').status_code in (400, 404)


def _logo(path: Path, ink: tuple[int, int, int]) -> None:
    from PIL import Image, ImageDraw

    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new('RGBA', (300, 100), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((14, 40), 'BRAND', fill=(*ink, 255))
    im.save(path)


def _well(path: Path) -> str:
    from phoenixadult.utils.images.logo_cache import preferred_well

    st = path.stat()
    return preferred_well(path, st.st_mtime, st.st_size)


def test_the_well_is_the_one_that_keeps_the_ink_visible(tmp_path: Path) -> None:
    for ink, expected in (((255, 255, 255), 'dark'), ((245, 240, 225), 'dark'), ((18, 18, 20), 'light'), ((20, 30, 90), 'light')):
        f = tmp_path / f'logo.{ink[0]}-{ink[2]}.png'
        _logo(f, ink)
        assert _well(f) == expected, f'{ink} landed on the wrong well'


def test_the_rgba_readback_matches_pillows_own_pixels() -> None:
    from PIL import Image

    im = Image.new('RGBA', (5, 3))
    for x in range(5):
        for y in range(3):
            im.putpixel((x, y), (x * 10, y * 20, 7, 255 - x))
    px = im.load()
    assert px is not None
    raw = im.tobytes()
    expected = [px[x, y] for y in range(im.height) for x in range(im.width)]
    assert [tuple(raw[i : i + 4]) for i in range(0, len(raw), 4)] == expected, 'the stride or channel order of the ink readback drifted'


def test_a_dim_mid_tone_never_outvotes_ink_that_would_vanish(tmp_path: Path) -> None:
    from PIL import Image, ImageDraw

    f = tmp_path / 'logo.mixed.png'
    im = Image.new('RGBA', (300, 100), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    draw.rectangle((0, 0, 299, 60), fill=(150, 90, 140, 255))
    draw.text((14, 70), 'BRAND', fill=(255, 255, 255, 255))
    im.save(f)
    assert _well(f) == 'dark', 'white text vanishes on light; the mid-tone block is only dim on dark'


def test_downscaling_never_discards_every_pixel(tmp_path: Path) -> None:
    f = tmp_path / 'logo.wide.png'
    _logo(f, (255, 255, 255))
    assert _well(f) == 'dark', 'alpha averaging must not blank the sample'


def test_the_well_colors_match_the_stylesheet() -> None:
    import re

    from phoenixadult.routes import __file__ as routes_file
    from phoenixadult.utils.images.logo_cache import DARK_WELL_RGB, LIGHT_WELL_RGB

    theme = (Path(routes_file).parent / 'html' / 'themes' / 'midnight.css').read_text(encoding='utf-8')
    for token, rgb in (('logo-proof-light-a', LIGHT_WELL_RGB), ('logo-proof-dark-a', DARK_WELL_RGB)):
        found = re.search(rf'--{token}:\s*#([0-9a-fA-F]{{6}})', theme)
        assert found, f'{token} is missing from the theme'
        assert tuple(int(found.group(1)[i : i + 2], 16) for i in (0, 2, 4)) == rgb, f'{token} drifted from the Python constant'


def test_cards_drop_the_slug_and_the_file_details() -> None:
    page = authed_client().get('/logos').text
    assert 'fmtSize' not in page, 'the file size line is gone'
    assert 'class="meta"' not in page
    assert 'text-align: center' in page.split('.site {')[1].split('}')[0]
    assert '.purge-btn { align-self: center; margin-top: auto; }' in page
    assert 'id="bgBtn"' in page and 'Backdrop: Auto' in page


def test_add_page_is_admin_only_and_offers_both_sources() -> None:
    from phoenixadult.utils.auth import user_store

    user_store.create_user('boss', 'pw-boss', is_admin=True)
    uid = user_store.create_user('member', 'pw-member', is_admin=False)
    member = TestClient(create_app())
    member.cookies.set('pa_session', user_store.create_session(uid, 'pytest'))
    assert member.get('/logos/add').status_code == 403
    assert member.get('/logos/api/expand', params={'studio': 'Vixen', 'template': 'https://x/y.png'}).status_code == 403
    page = authed_client().get('/logos/add').text
    assert 'id="studio"' in page
    assert 'data-drop' in page and "addEventListener('drop'" in page, 'each row takes a dropped file'
    assert 'data-url' in page and 'data-fetch' in page, 'each row has its own URL field and button'
    assert 'add-upload' in page and 'add-url' in page


def test_the_add_page_stays_put_and_works_a_studio_at_a_time() -> None:
    page = authed_client().get('/logos/add').text
    assert 'window.location.href' not in page, 'adding a logo must not navigate away'
    assert 'id="fetchAll"' in page and 'for (const r of queued) await fromUrl(r.alias);' in page
    assert 'markDone(alias, j.url, how)' in page, 'a finished row shows what landed'


def test_upload_files_the_logo_under_the_studio_and_alias(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / 'src.png'
    _logo(src, (255, 255, 255))
    client = authed_client()

    r = client.post('/logos/api/add-upload', data={'studio': 'Naughty America', 'alias': ''}, files={'file': ('brand.png', src.read_bytes(), 'image/png')})
    assert r.status_code == 200 and r.json()['ok'] is True
    assert r.json()['rel'] == 'naughtyamerica/logo.naughtyamerica.png'

    r = client.post(
        '/logos/api/add-upload', data={'studio': 'Naughty America', 'alias': '2 Chicks Same Time'}, files={'file': ('b.png', src.read_bytes(), 'image/png')}
    )
    assert r.json()['rel'] == 'naughtyamerica/logo.2chickssametime.png'

    r = client.post('/logos/api/add-upload', data={'studio': '', 'alias': ''}, files={'file': ('b.png', src.read_bytes(), 'image/png')})
    assert r.status_code == 400 and 'studio' in r.json()['error'].lower()


def test_add_url_rejects_a_non_http_address() -> None:
    r = authed_client().post('/logos/api/add-url', json={'studio': 'Vixen', 'url': 'ftp://x/y.png'})
    assert r.status_code == 400 and 'http' in r.json()['error']


def test_add_url_falls_back_to_the_impersonate_bypass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import phoenixadult.utils.images.image_fetcher as fetcher

    src = tmp_path / 'src.png'
    _logo(src, (255, 255, 255))
    seen: list[str] = []

    async def blocked(*_a: object, **_kw: object) -> tuple[bytes, str]:
        raise ValueError('403 Forbidden')

    async def impersonated(url: str, headers: object = None, **_kw: object) -> tuple[bytes, str]:
        seen.append(url)
        return src.read_bytes(), 'image/png'

    monkeypatch.setattr(fetcher, '_get_once', blocked)
    monkeypatch.setattr(fetcher, '_get_once_pinned', blocked)
    monkeypatch.setattr(fetcher, 'impersonate_get_bytes', impersonated)

    r = authed_client().post('/logos/api/add-url', json={'studio': 'Vixen', 'alias': '', 'url': 'https://blocked.example/logo.png'})
    assert r.status_code == 200 and r.json()['ok'] is True, r.json()
    assert seen == ['https://blocked.example/logo.png'], 'a blocked host must reach the bypass backend'
    assert r.json()['rel'] == 'vixen/logo.vixen.png'


def test_the_studio_list_is_the_whole_sitelist_not_just_scraped_studios() -> None:
    from phoenixadult.routes.logo_routes import _site_catalog

    catalog = _site_catalog()
    assert len(catalog) > 100, 'every supported site should be offered, not only studios with metadata'
    assert 'Naughty America' in catalog
    assert '2 Chicks Same Time' in catalog['Naughty America']

    page = authed_client().get('/logos/add').text
    assert '"Naughty America"' in page, 'the registry studio is offered without any cached scene'


def _fake_catalog(monkeypatch: pytest.MonkeyPatch, catalog: dict[str, list[str]]) -> None:
    import phoenixadult.routes.logo_routes as lr

    monkeypatch.setattr(lr, '_site_catalog', lambda: catalog)


def test_sub_sites_that_already_have_a_logo_drop_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_catalog(monkeypatch, {'Vixen': ['Blacked', 'Tushy', 'Deeper']})
    src = tmp_path / 'src.png'
    _logo(src, (255, 255, 255))
    client = authed_client()
    client.post('/logos/api/add-upload', data={'studio': 'Vixen', 'alias': 'Tushy'}, files={'file': ('a.png', src.read_bytes(), 'image/png')})

    j = client.get('/logos/api/aliases', params={'studio': 'Vixen'}).json()
    assert j['aliases'] == ['Blacked', 'Deeper'], 'Tushy already has a logo'
    assert j['studioTaken'] is False
    assert 'Vixen' in client.get('/logos/add').text


def test_a_studio_drops_out_once_it_and_every_sub_site_are_covered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_catalog(monkeypatch, {'Vixen': ['Tushy'], 'Bang': ['Bang Confessions']})
    src = tmp_path / 'src.png'
    _logo(src, (255, 255, 255))
    client = authed_client()
    for alias in ('', 'Tushy'):
        client.post('/logos/api/add-upload', data={'studio': 'Vixen', 'alias': alias}, files={'file': ('a.png', src.read_bytes(), 'image/png')})

    from phoenixadult.routes.logo_routes import _add_state

    studios = _add_state()['studios']
    assert 'Vixen' not in studios, 'the studio and its only sub-site are both covered'
    assert 'Bang' in studios

    j = client.get('/logos/api/aliases', params={'studio': 'Bang'}).json()
    assert j['studioTaken'] is False and j['aliases'] == ['Bang Confessions']


def test_state_groups_logos_by_studio_with_counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.routes.logo_routes import _state

    root = tmp_path / 'images' / 'logos'
    for folder, names in (('naughty-america', ('the-spa', 'anal-college')), ('vixen', ('tushy',))):
        (root / folder).mkdir(parents=True)
        for n in names:
            _logo(root / folder / f'logo.{n}.png', (255, 255, 255))
    logo_cache.invalidate()
    logo_cache.reconcile()

    state = _state()
    assert [s['name'] for s in state['studios']] == ['Naughty America', 'Vixen'], 'folders resolve to studio names'
    assert {s['name']: s['count'] for s in state['studios']} == {'Naughty America': 2, 'Vixen': 1}
    assert {e['studio'] for e in state['logos']} == {'Naughty America', 'Vixen'}


def test_the_logo_page_has_a_studio_rail_that_survives_a_refresh() -> None:
    page = authed_client().get('/logos').text
    assert '<nav class="studios" id="studios"' in page
    assert "var STUDIO_KEY = 'pa-logo-studio';" in page
    assert 'localStorage.getItem(STUDIO_KEY)' in page and 'localStorage.setItem(STUDIO_KEY, name)' in page
    assert "[{ name: '', count: total }].concat(list)" in page, 'All sits at the top of the rail'
    assert 'if (studio && l.studio !== studio) return false;' in page
    assert "if (studio && !list.some((s) => s.name === studio)) studio = '';" in page, 'a vanished studio falls back to All'


def test_hyphens_and_casing_never_split_a_logo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / 'images' / 'logos'
    (root / 'caramel-cash').mkdir(parents=True)
    _logo(root / 'caramel-cash' / 'logo.vr-pmv-bay.png', (255, 255, 255))
    (root / 'blurredmedia').mkdir(parents=True)
    _logo(root / 'blurredmedia' / 'logo.bi-guys-fuck.png', (255, 255, 255))
    logo_cache.invalidate()
    logo_cache.reconcile()

    for spelling in ('VR PMV Bay', 'vr-pmv-bay', 'vrpmvbay', 'VRPMVBay', 'Vr Pmv Bay'):
        assert logo_cache.find_logo(spelling, None) is not None, f'{spelling} should find the same logo'
    for spelling in ('Bi Guys Fuck', 'bi-guys-fuck', 'biguysfuck'):
        assert logo_cache.find_logo(spelling, None) is not None, f'{spelling} should find the same logo'


def test_a_folder_resolves_however_it_is_punctuated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / 'images' / 'logos'
    (root / 'blurred-media').mkdir(parents=True)
    _logo(root / 'blurred-media' / 'logo.biguysfuck.png', (255, 255, 255))
    logo_cache.invalidate()
    logo_cache.reconcile()

    assert logo_cache._folder_dir('blurredmedia') == root / 'blurred-media'
    assert logo_cache.find_logo(None, 'Bi Guys Fuck') is not None


def test_saving_writes_a_squashed_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / 'src.png'
    _logo(src, (255, 255, 255))
    client = authed_client()
    r = client.post('/logos/api/add-upload', data={'studio': 'Caramel Cash', 'alias': 'VR PMV Bay'}, files={'file': ('a.png', src.read_bytes(), 'image/png')})
    assert r.json()['rel'] == 'caramelcash/logo.vrpmvbay.png'


def test_sfw_mode_keeps_the_logo_artwork_off_the_page() -> None:
    page = authed_client().get('/logos').text
    assert 'var SFW = readSfw();' in page
    assert "${SFW ? '' : `<div class=\"logo-box" in page, 'SFW must skip the img entirely, not just hide it'
    assert "paintSfwButton(SFW, 'Logo artwork is hidden and never downloaded'" in page


def test_the_logo_page_uses_the_shared_toolbar_with_a_reset() -> None:
    page = authed_client().get('/logos').text
    assert '<button class="pa-btn pa-btn--lg" id="resetBtn" onclick="resetFilters()">Reset Filters</button>' in page
    assert 'id="sfwToggle"' in page
    assert '<div class="controls" id="controls">' in page and '<div class="toolbar">' in page
    assert 'id="filtersToggle"' in page and 'id="actionsToggle"' in page
    assert "document.getElementById('filter').value = '';" in page
    assert "pickStudio('');" in page, 'reset returns the studio rail to All'


def test_the_backdrop_verdict_survives_a_restart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    root = tmp_path / 'images' / 'logos' / 'studio'
    for name, ink in (('white', (255, 255, 255)), ('black', (18, 18, 20))):
        _logo(root / f'logo.{name}.png', ink)
    logo_cache.invalidate()
    logo_cache.reconcile()

    first = {e['rel']: e['well'] for e in logo_cache.entries()}
    assert set(first.values()) == {'dark', 'light'}
    store = logo_cache._well_store()
    assert store.exists(), 'the verdict must outlive the process or every restart rescans every logo'
    assert len(json.loads(store.read_text(encoding='utf-8'))) == 2

    logo_cache._WELL_CACHE.clear()
    logo_cache._WELL_LOADED = False

    import PIL.Image

    def _no_decoding(*_a: object, **_kw: object) -> object:
        raise AssertionError('a cached logo must not be opened and rescanned')

    monkeypatch.setattr(PIL.Image, 'open', _no_decoding)
    assert {e['rel']: e['well'] for e in logo_cache.entries()} == first, 'a restart must read the stored verdicts'


def test_a_changed_logo_is_rescanned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    root = tmp_path / 'images' / 'logos' / 'studio'
    _logo(root / 'logo.brand.png', (255, 255, 255))
    logo_cache.invalidate()
    logo_cache.reconcile()
    assert [e['well'] for e in logo_cache.entries()] == ['dark']

    _logo(root / 'logo.brand.png', (18, 18, 20))
    logo_cache.invalidate()
    logo_cache.reconcile()
    assert [e['well'] for e in logo_cache.entries()] == ['light'], 'a repainted logo must not keep the old verdict'
    assert len(json.loads(logo_cache._well_store().read_text(encoding='utf-8'))) == 1, 'stale keys must be pruned'


def test_expand_fills_every_missing_sub_site_but_never_the_whole_studio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_catalog(monkeypatch, {'Czech AV': ['Czech Streets', 'Czech Casting']})
    params = {'studio': 'Czech AV', 'template': 'https://static.hqmediago.com/media/{subsiteclean}.com/images/site-logo.svg'}

    rows = authed_client().get('/logos/api/expand', params=params).json()['rows']
    assert [r['alias'] for r in rows] == ['Czech Streets', 'Czech Casting'], 'the whole-studio row must be left out'
    assert rows[0]['urls'] == ['https://static.hqmediago.com/media/czechstreets.com/images/site-logo.svg']


def test_expand_names_a_placeholder_it_does_not_know(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_catalog(monkeypatch, {'Czech AV': ['Czech Streets']})
    r = authed_client().get('/logos/api/expand', params={'studio': 'Czech AV', 'template': 'https://x/{subsitclean}.png'})
    assert r.status_code == 400 and '{subsitclean}' in r.json()['error']


def test_expand_asks_for_a_studio_and_a_template() -> None:
    client = authed_client()
    assert client.get('/logos/api/expand', params={'template': 'https://x/y.png'}).status_code == 400
    assert client.get('/logos/api/expand', params={'studio': 'Vixen', 'template': '  '}).status_code == 400


def test_a_working_template_is_remembered_and_offered_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_catalog(monkeypatch, {'Czech AV': ['Czech Streets']})
    client = authed_client()
    assert client.get('/logos/api/aliases', params={'studio': 'Czech AV'}).json()['template'] == ''

    client.post('/logos/api/template', json={'studio': 'Czech AV', 'template': 'https://cdn/{domain}/logo.svg'})
    assert client.get('/logos/api/aliases', params={'studio': 'Czech AV'}).json()['template'] == 'https://cdn/{domain}/logo.svg'


def test_add_url_walks_the_candidates_until_one_is_an_image(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import phoenixadult.utils.images.image_fetcher as fetcher

    src = tmp_path / 'src.png'
    _logo(src, (255, 255, 255))
    tried: list[str] = []

    async def only_png(*args: object, **_kw: object) -> tuple[bytes, str]:
        url = next(a for a in args if isinstance(a, str) and a.startswith('http'))
        tried.append(url)
        if not url.endswith('.png'):
            raise ValueError('404 Not Found')
        return src.read_bytes(), 'image/png'

    monkeypatch.setattr(fetcher, '_get_once', only_png)
    monkeypatch.setattr(fetcher, '_get_once_pinned', only_png)
    monkeypatch.setattr(fetcher, 'impersonate_get_bytes', only_png)

    urls = ['https://cdn.example/logo.svg', 'https://cdn.example/logo.png', 'https://cdn.example/logo.webp']
    r = authed_client().post('/logos/api/add-url', json={'studio': 'Vixen', 'alias': '', 'urls': urls})
    assert r.status_code == 200 and r.json()['rel'] == 'vixen/logo.vixen.png', r.json()
    assert tried[0].endswith('.svg') and tried[-1].endswith('.png'), 'candidates are tried in order and stop at the winner'
    assert not any(u.endswith('.webp') for u in tried), 'the walk stops once one succeeds'


def test_add_url_refuses_to_reach_a_private_host() -> None:
    r = authed_client().post('/logos/api/add-url', json={'studio': 'Vixen', 'alias': '', 'url': 'http://10.0.0.1/logo.png'})
    assert r.status_code == 502 and 'blocked host' in r.json()['error']


def test_the_add_page_advertises_the_placeholders_it_supports() -> None:
    from phoenixadult.utils.images.logo_template import PLACEHOLDERS

    page = authed_client().get('/logos/add').text
    for token, _note in PLACEHOLDERS:
        assert f'>{token}</code>' in page, f'{token} is supported but never offered on the page'
    assert 'Try All Subsites' in page
