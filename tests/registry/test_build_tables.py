from __future__ import annotations

import dataclasses

import pytest

from phoenixadult.registry import PROVIDER_DEFINITIONS, SITE_DEFINITIONS, _build_tables, find_site

_BASE = SITE_DEFINITIONS[0]


def _site(name: str, **changes: object) -> object:
    return dataclasses.replace(_BASE, **{'name': name, 'aliases': (), 'token_prefixes': (), **changes})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ('sites', 'message'),
    [
        ([_site('Alpha', provider_id='nobody')], 'unknown providerId "nobody"'),
        ([_site('Alpha'), _site('Beta', aliases=('alpha',))], 'token "alpha" claimed by both "Alpha" and "Beta"'),
        ([_site('Alpha', token_prefixes=(' ',))], 'declares an empty token prefix'),
        ([_site('Alpha', token_prefixes=('ab',)), _site('Beta', token_prefixes=('ab',))], 'token prefix "ab" declared twice'),
    ],
    ids=['unknown-provider', 'token-conflict', 'empty-prefix', 'duplicate-prefix'],
)
def test_a_bad_registry_is_refused(sites: list[object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _build_tables(PROVIDER_DEFINITIONS, sites)  # type: ignore[arg-type]


def test_tables_index_names_aliases_and_longest_prefix_first() -> None:
    tables = _build_tables(PROVIDER_DEFINITIONS, [_site('Alpha', aliases=('Alpha Two',), token_prefixes=('al', 'alph'))])  # type: ignore[list-item]
    assert set(tables.site_by_token) == {'alpha', 'alphatwo'}
    assert tables.display_by_token['alphatwo'] == 'Alpha Two'
    assert [prefix for prefix, _site in tables.prefix_table] == ['alph', 'al']
    assert tables.tokens_by_provider_name[_BASE.provider_name or 'Alpha'] == ['Alpha', 'Alpha Two']


def test_every_real_site_resolves_by_name() -> None:
    assert all(find_site(site.name) is not None for site in SITE_DEFINITIONS)
