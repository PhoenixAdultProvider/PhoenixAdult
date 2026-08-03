from __future__ import annotations

from pathlib import Path

import pytest

import phoenixadult.clients.aggregators.data18 as data18_module
import phoenixadult.clients.sites.manualnfo as mn_module
from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.sites.manualnfo import ManualNfoClient
from phoenixadult.registry import find_site

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
    results: list[SearchResult] = []
    await ManualNfoClient().search(results, _ctx(BASENAME))
    assert len(results) == 1
    assert results[0].title == 'Naughty Fantasy'
    assert results[0].release_date == '2024-03-15'
    assert results[0].score == 100
    assert results[0].thumb_url is not None and '/images/manual-nfo/' in results[0].thumb_url


async def test_search_no_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    _write_folder(tmp_path, BASENAME)
    results: list[SearchResult] = []
    await ManualNfoClient().search(results, _ctx('no.such.basename'))
    assert results == []


async def test_search_miss_driven_refresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    monkeypatch.setattr(mn_module, '_MISS_THROTTLE_S', 0.0)
    _write_folder(tmp_path, BASENAME)
    client = ManualNfoClient()
    await client.search([], _ctx(BASENAME))
    _write_folder(tmp_path, 'latecomer.basename')
    results: list[SearchResult] = []
    await client.search(results, _ctx('latecomer.basename'))
    assert len(results) == 1
    assert results[0].title == 'Naughty Fantasy'


async def test_search_flat_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    (tmp_path / 'flat.example.nfo').write_text(SAMPLE_NFO, encoding='utf-8')
    results: list[SearchResult] = []
    await ManualNfoClient().search(results, _ctx('flat.example'))
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
    results: list[SearchResult] = []
    await ManualNfoClient().search(results, _ctx(BASENAME))
    assert results[0].title == 'Shallow Winner'


async def test_search_nested_thumb_url_encoded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    nested = tmp_path / 'Studios' / 'Paradise Films' / BASENAME
    nested.mkdir(parents=True)
    (nested / f'{BASENAME}.nfo').write_text(SAMPLE_NFO, encoding='utf-8')
    (nested / f'{BASENAME}-poster.jpg').write_text('', encoding='utf-8')
    results: list[SearchResult] = []
    await ManualNfoClient().search(results, _ctx(BASENAME))
    assert results[0].thumb_url is not None
    assert '/images/manual-nfo/Studios/Paradise%20Films/' in results[0].thumb_url
    assert f'{BASENAME}-poster.jpg' in results[0].thumb_url


async def test_detail_full_map(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    monkeypatch.delenv('DATA18_ENABLE', raising=False)
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
    assert len(detail.art) == 2
    assert f'{BASENAME}-poster.jpg' in detail.art[0]
    assert f'{BASENAME}-fanart.jpg' in detail.art[1]


async def test_detail_url_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    monkeypatch.delenv('DATA18_ENABLE', raising=False)
    _write_folder(tmp_path, BASENAME)
    detail = await ManualNfoClient().fetch_scene_detail(BASENAME, SITE)
    assert detail is not None
    assert detail.art == ['https://example.com/poster.jpg', 'https://example.com/fanart.jpg']


async def test_detail_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    assert await ManualNfoClient().fetch_scene_detail('missing.basename', SITE) is None


async def test_detail_data18_enrichment_appends_images(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    monkeypatch.setenv('DATA18_ENABLE', 'true')
    _write_folder(tmp_path, BASENAME)
    calls: dict[str, object] = {}

    class FakeData18(data18_module.Data18Client):
        async def find_scene_url(
            self, scene_id: str | None, query: str, providers: list[str], scene_date: object, kind: str = 'scene', search: bool = True
        ) -> str:
            calls['providers'] = providers
            calls['query'] = query
            return 'https://www.data18.com/scenes/123'

        async def fetch_images(self, scene_url: str) -> list[str]:
            return ['https://cdn.data18.com/a.jpg', 'https://example.com/poster.jpg']

    monkeypatch.setattr(data18_module, 'Data18Client', FakeData18)
    detail = await ManualNfoClient().fetch_scene_detail(BASENAME, SITE)
    assert detail is not None
    assert detail.art == ['https://example.com/poster.jpg', 'https://example.com/fanart.jpg', 'https://cdn.data18.com/a.jpg']
    assert calls['query'] == 'Naughty Fantasy'
    assert calls['providers'] == ['Paradise Films', 'Naughty Series']


async def test_detail_data18_enrichment_no_match_is_quiet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    monkeypatch.setenv('DATA18_ENABLE', 'true')
    _write_folder(tmp_path, BASENAME)
    queries: list[str] = []

    class FakeData18(data18_module.Data18Client):
        async def find_scene_url(
            self, scene_id: str | None, query: str, providers: list[str], scene_date: object, kind: str = 'scene', search: bool = True
        ) -> None:
            queries.append(query)
            return None

        async def fetch_images(self, scene_url: str) -> list[str]:
            raise AssertionError('fetch_images must not be called without a match')

    monkeypatch.setattr(data18_module, 'Data18Client', FakeData18)
    detail = await ManualNfoClient().fetch_scene_detail(BASENAME, SITE)
    assert detail is not None
    assert queries == ['Naughty Fantasy']
    assert detail.art == ['https://example.com/poster.jpg', 'https://example.com/fanart.jpg']


async def test_detail_data18_enrichment_off_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    monkeypatch.delenv('DATA18_ENABLE', raising=False)
    _write_folder(tmp_path, BASENAME)

    def _boom() -> None:
        raise AssertionError('Data18Client must not be constructed when DATA18_ENABLE is off')

    monkeypatch.setattr(data18_module, 'Data18Client', _boom)
    detail = await ManualNfoClient().fetch_scene_detail(BASENAME, SITE)
    assert detail is not None
    assert detail.art == ['https://example.com/poster.jpg', 'https://example.com/fanart.jpg']


async def test_detail_year_only_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    monkeypatch.delenv('DATA18_ENABLE', raising=False)
    _write_folder(tmp_path, 'year.only.case', nfo='<?xml version="1.0"?><movie><title>YO</title><year>2019</year></movie>')
    detail = await ManualNfoClient().fetch_scene_detail('year.only.case', SITE)
    assert detail is not None
    assert detail.release_date == '2019-01-01'


_NFO_WITH_DATA18 = SAMPLE_NFO.replace('</movie>', '  <data18>1150700</data18>\n</movie>')


def test_parse_nfo_reads_data18_tag() -> None:
    assert mn_module.__testing__['parse_nfo'](_NFO_WITH_DATA18).data18 == '1150700'
    assert mn_module.__testing__['parse_nfo'](SAMPLE_NFO).data18 is None


def test_parse_nfo_reads_nested_data18_tag() -> None:
    parse_nfo = mn_module.__testing__['parse_nfo']
    nested = SAMPLE_NFO.replace('</movie>', '  <data18>\n    <id>1209186</id>\n    <type>scene</type>\n  </data18>\n</movie>')
    assert parse_nfo(nested).data18 == 'scenes/1209186'
    movie = SAMPLE_NFO.replace('</movie>', '  <data18>\n    <id>1227431</id>\n    <type>movie</type>\n  </data18>\n</movie>')
    assert parse_nfo(movie).data18 == 'movies/1227431'
    untyped = SAMPLE_NFO.replace('</movie>', '  <data18>\n    <id>1209186</id>\n  </data18>\n</movie>')
    assert parse_nfo(untyped).data18 == 'scenes/1209186'


async def test_detail_nested_data18_movie_fetches_movie_images(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    monkeypatch.setenv('DATA18_ENABLE', 'true')
    nfo = SAMPLE_NFO.replace('</movie>', '  <data18>\n    <id>1227431</id>\n    <type>movie</type>\n  </data18>\n</movie>')
    _write_folder(tmp_path, BASENAME, nfo=nfo)
    fetched: list[str] = []

    class FakeData18(data18_module.Data18Client):
        async def find_scene_url(
            self, scene_id: str | None, query: str, providers: list[str], scene_date: object, kind: str = 'scene', search: bool = True
        ) -> None:
            raise AssertionError('an explicit <data18> ref must not run the data18 search')

        async def fetch_images(self, scene_url: str) -> list[str]:
            raise AssertionError('a movie ref must use fetch_movie_images')

        async def fetch_movie_images(self, movie_url: str, page_sel: object = None, covers: list[str] | None = None) -> list[str]:
            fetched.append(movie_url)
            return ['https://cdn.data18.com/movie.jpg']

    monkeypatch.setattr(data18_module, 'Data18Client', FakeData18)
    detail = await ManualNfoClient().fetch_scene_detail(BASENAME, SITE)
    assert detail is not None
    assert fetched == ['https://www.data18.com/movies/1227431']
    assert 'https://cdn.data18.com/movie.jpg' in detail.art


@pytest.mark.parametrize(
    'ref',
    ['1150700', 'scenes/1150700', '/scenes/1150700', 'https://www.data18.com/scenes/1150700', '  1150700  '],
)
async def test_detail_data18_tag_bypasses_search(ref: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    monkeypatch.setenv('DATA18_ENABLE', 'true')
    _write_folder(tmp_path, BASENAME, nfo=SAMPLE_NFO.replace('</movie>', f'  <data18>{ref}</data18>\n</movie>'))
    fetched: list[str] = []

    class FakeData18(data18_module.Data18Client):
        async def find_scene_url(
            self, scene_id: str | None, query: str, providers: list[str], scene_date: object, kind: str = 'scene', search: bool = True
        ) -> None:
            raise AssertionError('an explicit <data18> ref must not run the data18 search')

        async def fetch_images(self, scene_url: str) -> list[str]:
            fetched.append(scene_url)
            return ['https://cdn.data18.com/a.jpg']

    monkeypatch.setattr(data18_module, 'Data18Client', FakeData18)
    detail = await ManualNfoClient().fetch_scene_detail(BASENAME, SITE)
    assert detail is not None
    assert fetched == ['https://www.data18.com/scenes/1150700']
    assert 'https://cdn.data18.com/a.jpg' in detail.art


async def test_detail_data18_tag_unusable_value_falls_back_to_search(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    monkeypatch.setenv('DATA18_ENABLE', 'true')
    _write_folder(tmp_path, BASENAME, nfo=SAMPLE_NFO.replace('</movie>', '  <data18>https://evil.com/scenes/1</data18>\n</movie>'))
    queries: list[str] = []

    class FakeData18(data18_module.Data18Client):
        async def find_scene_url(
            self, scene_id: str | None, query: str, providers: list[str], scene_date: object, kind: str = 'scene', search: bool = True
        ) -> None:
            queries.append(query)
            return None

        async def fetch_images(self, scene_url: str) -> list[str]:
            raise AssertionError('no match -> no fetch')

    monkeypatch.setattr(data18_module, 'Data18Client', FakeData18)
    assert await ManualNfoClient().fetch_scene_detail(BASENAME, SITE) is not None
    assert queries == ['Naughty Fantasy']


async def test_detail_data18_tag_still_respects_kill_switch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    monkeypatch.delenv('DATA18_ENABLE', raising=False)
    _write_folder(tmp_path, BASENAME, nfo=_NFO_WITH_DATA18)

    def _boom() -> None:
        raise AssertionError('DATA18_ENABLE=off must suppress enrichment even with a <data18> tag')

    monkeypatch.setattr(data18_module, 'Data18Client', _boom)
    assert await ManualNfoClient().fetch_scene_detail(BASENAME, SITE) is not None


def test_parse_nfo_repairs_bare_ampersand_preserving_text() -> None:
    nfo = '<movie><title>Big & Bad</title><genre>Pantyhose & Stockings</genre><genre>Anal</genre></movie>'
    parsed = mn_module.__testing__['parse_nfo'](nfo)
    assert parsed.title == 'Big & Bad'
    assert parsed.genres == ['Pantyhose & Stockings', 'Anal']


@pytest.mark.parametrize(
    ('nfo', 'title'),
    [
        ('<movie><title>3 < 4</title></movie>', '3 < 4'),
        ('<movie><title>a&nbsp;b</title></movie>', 'a\xa0b'),
        ('<movie><title>a\x0cb</title></movie>', 'ab'),
        ('<movie><title>x</movie>', 'x'),
        ('<movie><title><b>x</title></b></movie>', ''),
        ('<movie><title>x</title></movie>trailing', 'x'),
        ('<?xml version="1.0" encoding="utf-8"?><movie><title>caf\xe9 & bar</title></movie>', 'caf\xe9 & bar'),
    ],
)
def test_parse_nfo_recovers_from_malformed_xml(nfo: str, title: str) -> None:
    parsed = mn_module.__testing__['parse_nfo'](nfo)
    assert parsed is not None
    assert parsed.title == title


def test_parse_nfo_leaves_valid_xml_untouched() -> None:
    nfo = '<movie><title>x &amp; y</title><plot>caf\xe9 &#233;</plot><uniqueid type="tmdb">9</uniqueid></movie>'
    parsed = mn_module.__testing__['parse_nfo'](nfo)
    assert parsed.title == 'x & y'
    assert parsed.plot == 'caf\xe9 \xe9'


def test_parse_nfo_returns_none_when_unsalvageable() -> None:
    assert mn_module.__testing__['parse_nfo']('') is None


async def test_detail_reads_nfo_with_bare_ampersand(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    monkeypatch.delenv('DATA18_ENABLE', raising=False)
    _write_folder(tmp_path, 'amp.case', nfo='<movie><title>A & B</title><genre>Pantyhose & Stockings</genre></movie>')
    detail = await ManualNfoClient().fetch_scene_detail('amp.case', SITE)
    assert detail is not None
    assert detail.title == 'A & B'


async def test_a_miss_walks_the_tree_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MANUAL_NFO_PATH', str(tmp_path))
    _write_folder(tmp_path, BASENAME)
    builds = 0
    real_build = mn_module._build_index

    def counted(root: str):  # noqa: ANN202
        nonlocal builds
        builds += 1
        return real_build(root)

    monkeypatch.setattr(mn_module, '_build_index', counted)
    results: list[SearchResult] = []
    await ManualNfoClient().search(results, _ctx('absent.basename'))
    assert results == []
    assert builds == 1
