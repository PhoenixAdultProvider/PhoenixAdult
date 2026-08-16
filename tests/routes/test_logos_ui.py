from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from phoenixadult.utils.images import logo_cache
from tests.conftest import authed_client


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
    assert data['logos'][0]['slug'] == 'baby-got-boobs'
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
    monkeypatch.setenv('IMAGE_DIR', str(tmp_path / 'images'))
    src = tmp_path / 'src.png'
    _logo(src, (255, 255, 255))
    client = authed_client()

    r = client.post('/logos/api/add-upload', data={'studio': 'Naughty America', 'alias': ''}, files={'file': ('brand.png', src.read_bytes(), 'image/png')})
    assert r.status_code == 200 and r.json()['ok'] is True
    assert r.json()['rel'] == 'naughty-america/logo.naughty-america.png'

    r = client.post(
        '/logos/api/add-upload', data={'studio': 'Naughty America', 'alias': '2 Chicks Same Time'}, files={'file': ('b.png', src.read_bytes(), 'image/png')}
    )
    assert r.json()['rel'] == 'naughty-america/logo.2-chicks-same-time.png'

    r = client.post('/logos/api/add-upload', data={'studio': '', 'alias': ''}, files={'file': ('b.png', src.read_bytes(), 'image/png')})
    assert r.status_code == 400 and 'studio' in r.json()['error'].lower()


def test_add_url_rejects_a_non_http_address() -> None:
    r = authed_client().post('/logos/api/add-url', json={'studio': 'Vixen', 'url': 'ftp://x/y.png'})
    assert r.status_code == 400 and 'http' in r.json()['error']


def test_add_url_falls_back_to_the_impersonate_bypass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import phoenixadult.utils.images.image_fetcher as fetcher

    monkeypatch.setenv('IMAGE_DIR', str(tmp_path / 'images'))
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
    monkeypatch.setenv('IMAGE_DIR', str(tmp_path / 'images'))
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
    monkeypatch.setenv('IMAGE_DIR', str(tmp_path / 'images'))
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

    monkeypatch.setenv('IMAGE_DIR', str(tmp_path / 'images'))
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
    assert "const STUDIO_KEY = 'pa-logo-studio';" in page
    assert 'localStorage.getItem(STUDIO_KEY)' in page and 'localStorage.setItem(STUDIO_KEY, name)' in page
    assert "[{ name: '', count: total }].concat(list)" in page, 'All sits at the top of the rail'
    assert 'if (studio && l.studio !== studio) return false;' in page
    assert "if (studio && !list.some((s) => s.name === studio)) studio = '';" in page, 'a vanished studio falls back to All'
