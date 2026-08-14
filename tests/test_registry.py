from __future__ import annotations

from phoenixadult.registry import canonical_site_display, find_site
from phoenixadult.utils.processors.filename_parser import get_site_name_from_registry


def test_x_series_prefixes_resolve_to_teamskeet_without_an_alias() -> None:
    for token in ('mylfxsomethingnew', 'teamskeetxbrandnewcollab', 'MYLFxDanteColle'):
        site = find_site(token)
        assert site is not None and site.name == 'TeamSkeet'
    assert canonical_site_display('mylfxsomethingnew') == 'TeamSkeet'


def test_exact_aliases_still_win_over_the_prefix() -> None:
    site = find_site('MYLF X Bang')
    assert site is not None and site.name == 'TeamSkeet'
    assert canonical_site_display('TeamSkeet X Reislin') == 'TeamSkeet X Reislin'


def test_a_prefix_never_matches_a_multi_token_join() -> None:
    assert find_site('mylfxdantecolle 23') is None
    assert find_site('teamskeetxreislin 21 07') is None


def test_x_series_filenames_parse_site_date_and_title() -> None:
    lookup = lambda t: find_site(t) is not None  # noqa: E731

    parsed = get_site_name_from_registry('mylfxdantecolle.23.08.22.ryan.keely.two.is.her.lucky.number.mp4', lookup)
    assert parsed is not None
    assert (parsed.site_token, parsed.date, parsed.content) == ('mylfxdantecolle', '2023-08-22', 'ryan keely two is her lucky number')

    parsed = get_site_name_from_registry('teamskeetxreislin.21.07.10.reislin.surprise.in.the.kitchen.mp4', lookup)
    assert parsed is not None
    assert (parsed.site_token, parsed.date, parsed.content) == ('teamskeetxreislin', '2021-07-10', 'reislin surprise in the kitchen')


def test_search_url_joins_a_relative_path_to_the_base() -> None:
    from phoenixadult.registry import SITE_DEFINITIONS

    site = next(s for s in SITE_DEFINITIONS if not s.search_path.startswith('http') and '{query}' in s.search_path)
    assert site.search_url('abc') == site.base_url.rstrip('/') + site.search_path.replace('{query}', 'abc')
    assert '{query}' not in site.search_url('abc')


def test_search_url_returns_an_absolute_search_path_unchanged() -> None:
    from phoenixadult.registry import SITE_DEFINITIONS

    absolute = [s for s in SITE_DEFINITIONS if s.search_path.startswith(('http://', 'https://'))]
    assert absolute, 'expected at least one site with an absolute search_path'
    for site in absolute:
        url = site.search_url('abc')
        assert url.startswith(site.search_path.split('{query}')[0])
        assert site.base_url.rstrip('/') not in url or site.search_path.startswith(site.base_url.rstrip('/'))


def test_search_context_search_url_defaults_to_the_encoded_query() -> None:
    from phoenixadult.clients.base import SearchContext
    from phoenixadult.registry import SITE_DEFINITIONS

    site = next(s for s in SITE_DEFINITIONS if '{query}' in s.search_path and not s.search_path.startswith('http'))
    ctx = SearchContext(title='Some Title', encoded='some+title', search_site=site.name, site_info=site)
    assert ctx.search_url() == site.search_url('some+title')
    assert ctx.search_url('other') == site.search_url('other')
