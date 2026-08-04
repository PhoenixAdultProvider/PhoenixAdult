from __future__ import annotations

from phoenixadult.clients.networks.reptyle_subnetworks import resolve_reptyle_subnetwork
from phoenixadult.registry import find_site
from phoenixadult.registry.selectors.networks.reptyle_networks import reptyle_aliases, reptyle_subnetworks


def test_mylf_x_collabs_alias_to_teamskeet_but_display_as_mylf() -> None:
    site = find_site('MYLF X Bang')
    assert site is not None and site.name == 'TeamSkeet'
    hit = resolve_reptyle_subnetwork('MYLF X Bang')
    assert hit == {'network': 'MYLF', 'subsite': 'MYLF X Bang'}


def test_self_names_resolve_as_subnetworks_without_alias_entries() -> None:
    assert resolve_reptyle_subnetwork('TeamSkeet') == {'network': 'TeamSkeet', 'subsite': 'TeamSkeet'}
    assert 'TeamSkeet' not in reptyle_aliases()['TeamSkeet']


def test_hussie_pass_is_a_subnetwork_but_not_a_teamskeet_alias() -> None:
    hit = resolve_reptyle_subnetwork('Hussie Pass')
    assert hit == {'network': 'TeamSkeet', 'subsite': 'Hussie Pass'}
    site = find_site('Hussie Pass')
    assert site is not None and site.name != 'TeamSkeet'


def test_series_labels_are_alias_only() -> None:
    assert resolve_reptyle_subnetwork('TeamSkeet X Series') is None
    site = find_site('TeamSkeet X Series')
    assert site is not None and site.name == 'TeamSkeet'


def test_rub_a_teen_casing_is_unified() -> None:
    hit = resolve_reptyle_subnetwork('rub a teen')
    assert hit == {'network': 'TeamSkeet', 'subsite': 'Rub a Teen'}
    from phoenixadult.registry import canonical_site_display

    assert canonical_site_display('Rub A Teen') == 'Rub a Teen'


def test_registry_only_networks_are_not_subnetworks() -> None:
    assert 'Family Strokes' not in reptyle_subnetworks()
    assert resolve_reptyle_subnetwork('Dad Crush') is None
    site = find_site('Dad Crush')
    assert site is not None and site.name == 'Family Strokes'
