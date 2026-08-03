from __future__ import annotations

from phoenixadult.registry import canonical_site_display, find_site
from phoenixadult.utils.processors.filename_parser import get_site_name_from_registry


def test_x_series_prefixes_resolve_to_teamskeet_without_an_alias() -> None:
    for token in ('mylfxsomethingnew', 'teamskeetxbrandnewcollab', 'MYLFxDanteColle'):
        site = find_site(token)
        assert site is not None and site.name == 'TeamSkeet'
    assert canonical_site_display('mylfxsomethingnew') == 'TeamSkeet'


def test_exact_aliases_still_win_over_the_prefix() -> None:
    site = find_site('MYLF X Dante Colle')
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
