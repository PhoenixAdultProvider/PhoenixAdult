from __future__ import annotations

from pathlib import Path

import pytest

import app.clients.sites.manualnfo as mn_module
from app.clients.base import SearchContext
from app.clients.sites.manualnfo import ManualNfoClient
from app.registry import find_site

SITE = find_site('Manual NFO')
assert SITE is not None

SAMPLE_NFO = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<movie>
  <title>Naughty Fantasy</title>
  <set>Naughty Series</set>
  <year>2024</year>
  <plot>A long plot describing the scene.</plot>
  <outline>Short outline.</outline>
  <tagline>The best fantasy yet</tagline>
  <releasedate>2024-03-15</releasedate>
  <studio>Paradise Films</studio>
  <thumb>https://example.com/poster.jpg</thumb>
  <fanart><thumb>https://example.com/fanart.jpg</thumb></fanart>
  <genre>Brunette</genre>
  <genre>Solo</genre>
  <actor><name>Jane Doe</name><role>Lead</role><thumb>https://example.com/jane.jpg</thumb><gender>Female</gender></actor>
  <actor><name>John Smith</name><role>Support</role><gender>male</gender></actor>
  <actor><name>Pat Roe</name><gender>nonsense</gender></actor>
</movie>"""

BASENAME = 'paradisefilms.27885.naughty.fantasy'


@pytest.fixture(autouse=True)
def _reset() -> None:
    mn_module._reset_index_cache()


def _write_folder(root: Path, basename: str, *, poster: bool = False, fanart: bool = False, nfo: str = SAMPLE_NFO) -> None:
    d = root / basename
    d.mkdir(parents=True, exist_ok=True)
    (d / f'{basename}.nfo').write_text(nfo, encoding='utf-8')
    if poster:
        (d / f'{basename}-poster.jpg').write_text('', encoding='utf-8')
    if fanart:
        (d / f'{basename}-fanart.jpg').write_text('', encoding='utf-8')


def _ctx(title: str) -> SearchContext:
    return SearchContext(title=title, encoded=title, search_site=SITE.name, site_info=SITE)


async def test_search_folder_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    _write_folder(tmp_path, BASENAME, poster=True, fanart=True)
    results = await ManualNfoClient().search(_ctx(BASENAME))
    assert len(results) == 1
    assert results[0].title == 'Naughty Fantasy'
    assert results[0].release_date == '2024-03-15'
    assert results[0].score == 100
    assert results[0].thumb_url is not None and '/images/manual-nfo/' in results[0].thumb_url


async def test_search_no_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    _write_folder(tmp_path, BASENAME)
    assert await ManualNfoClient().search(_ctx('no.such.basename')) == []


async def test_search_miss_driven_refresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    monkeypatch.setattr(mn_module, '_MISS_THROTTLE_S', 0.0)
    _write_folder(tmp_path, BASENAME)
    client = ManualNfoClient()
    await client.search(_ctx(BASENAME))  # warm cache
    _write_folder(tmp_path, 'latecomer.basename')
    results = await client.search(_ctx('latecomer.basename'))
    assert len(results) == 1
    assert results[0].title == 'Naughty Fantasy'


async def test_search_flat_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    (tmp_path / 'flat.example.nfo').write_text(SAMPLE_NFO, encoding='utf-8')
    results = await ManualNfoClient().search(_ctx('flat.example'))
    assert len(results) == 1
    assert results[0].title == 'Naughty Fantasy'


async def test_search_nested_and_shallowest_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    nested = tmp_path / 'Studios' / 'Paradise Films' / BASENAME
    nested.mkdir(parents=True)
    (nested / f'{BASENAME}.nfo').write_text(SAMPLE_NFO, encoding='utf-8')
    (nested / f'{BASENAME}-poster.jpg').write_text('', encoding='utf-8')
    shallow = tmp_path / BASENAME
    shallow.mkdir()
    (shallow / f'{BASENAME}.nfo').write_text('<?xml version="1.0"?><movie><title>Shallow Winner</title></movie>', encoding='utf-8')
    results = await ManualNfoClient().search(_ctx(BASENAME))
    assert results[0].title == 'Shallow Winner'


async def test_search_nested_thumb_url_encoded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    nested = tmp_path / 'Studios' / 'Paradise Films' / BASENAME
    nested.mkdir(parents=True)
    (nested / f'{BASENAME}.nfo').write_text(SAMPLE_NFO, encoding='utf-8')
    (nested / f'{BASENAME}-poster.jpg').write_text('', encoding='utf-8')
    results = await ManualNfoClient().search(_ctx(BASENAME))
    assert results[0].thumb_url is not None
    assert '/images/manual-nfo/Studios/Paradise%20Films/' in results[0].thumb_url
    assert f'{BASENAME}-poster.jpg' in results[0].thumb_url


async def test_detail_full_map(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    _write_folder(tmp_path, BASENAME, poster=True, fanart=True)
    detail = await ManualNfoClient().fetch_scene_detail(BASENAME, SITE)
    assert detail is not None
    assert detail.title == 'Naughty Fantasy'
    assert detail.summary == 'A long plot describing the scene.'
    assert detail.tagline == 'The best fantasy yet'
    assert detail.studio == 'Paradise Films'
    assert detail.release_date == '2024-03-15'
    assert detail.collections == ['Naughty Series']
    assert detail.genres == ['Brunette', 'Solo']
    assert [(a.name, a.photo_url, a.gender) for a in detail.actors] == [
        ('Jane Doe', 'https://example.com/jane.jpg', 'female'),
        ('John Smith', '', 'male'),
        ('Pat Roe', '', ''),
    ]
    assert len(detail.raw_image_urls) == 2
    assert f'{BASENAME}-poster.jpg' in detail.raw_image_urls[0]
    assert f'{BASENAME}-fanart.jpg' in detail.raw_image_urls[1]


async def test_detail_url_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    _write_folder(tmp_path, BASENAME)  # no sibling images
    detail = await ManualNfoClient().fetch_scene_detail(BASENAME, SITE)
    assert detail is not None
    assert detail.raw_image_urls == ['https://example.com/poster.jpg', 'https://example.com/fanart.jpg']


async def test_detail_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    assert await ManualNfoClient().fetch_scene_detail('missing.basename', SITE) is None


async def test_detail_year_only_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    _write_folder(tmp_path, 'year.only.case', nfo='<?xml version="1.0"?><movie><title>YO</title><year>2019</year></movie>')
    detail = await ManualNfoClient().fetch_scene_detail('year.only.case', SITE)
    assert detail is not None
    assert detail.release_date == '2019-01-01'
