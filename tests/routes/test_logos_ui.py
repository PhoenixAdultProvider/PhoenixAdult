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


def test_the_well_contrasts_with_the_logos_own_ink(tmp_path: Path) -> None:
    from phoenixadult.utils.images.logo_cache import ink_is_light

    for ink, expected in (((255, 255, 255), True), ((245, 240, 225), True), ((18, 18, 20), False), ((200, 60, 60), False)):
        f = tmp_path / f'logo.{ink[0]}.png'
        _logo(f, ink)
        st = f.stat()
        assert ink_is_light(f, st.st_mtime, st.st_size) is expected, f'{ink} landed on the wrong well'


def test_downscaling_never_discards_every_pixel(tmp_path: Path) -> None:
    from phoenixadult.utils.images.logo_cache import ink_is_light

    f = tmp_path / 'logo.wide.png'
    _logo(f, (255, 255, 255))
    st = f.stat()
    assert ink_is_light(f, st.st_mtime, st.st_size) is True, 'alpha averaging must not blank the sample'


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
    assert 'id="studio"' in page and 'id="alias"' in page
    assert 'id="drop"' in page and "addEventListener('drop'" in page
    assert 'add-upload' in page and 'add-url' in page


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
