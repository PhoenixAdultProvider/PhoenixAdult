from __future__ import annotations

import json
from pathlib import Path

import pytest

from phoenixadult.utils.images import logo_template


@pytest.fixture(autouse=True)
def store(tmp_path: Path) -> Path:
    return tmp_path / 'logo-templates.json'


def _one(template: str, base_url: str = '') -> str:
    return logo_template.expand(template, 'Czech AV', 'Czech Streets', base_url)[0]


def test_the_documented_example_expands_to_the_real_url() -> None:
    got = _one('https://static.hqmediago.com/media/{subsiteclean}.com/images/site-logo.svg')
    assert got == 'https://static.hqmediago.com/media/czechstreets.com/images/site-logo.svg'


def test_every_name_form_of_the_subsite() -> None:
    assert _one('{subsiteclean}|{subsite-name}|{subsite_name}|{subsite}') == 'czechstreets|czech-streets|czech_streets|Czech%20Streets'


def test_every_name_form_of_the_studio() -> None:
    assert _one('{studioclean}|{studio-name}|{studio_name}|{studio}') == 'czechav|czech-av|czech_av|Czech%20AV'


def test_domain_comes_from_the_site_and_drops_www() -> None:
    assert _one('https://cdn/{domain}/logo.png', 'https://www.czechstreets.com/') == 'https://cdn/czechstreets.com/logo.png'


def test_domain_is_blank_when_the_row_is_only_a_sub_group_label() -> None:
    assert _one('https://cdn/{domain}/logo.png') == 'https://cdn//logo.png'


def test_ext_fans_out_in_priority_order() -> None:
    urls = logo_template.expand('https://cdn/logo{ext}', 'S', 'Sub')
    assert urls == ['https://cdn/logo.svg', 'https://cdn/logo.png', 'https://cdn/logo.webp', 'https://cdn/logo.jpg']


def test_a_template_without_ext_yields_exactly_one_url() -> None:
    assert len(logo_template.expand('https://cdn/logo.png', 'S', 'Sub')) == 1


def test_an_unknown_placeholder_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match=r'\{subsitclean\}'):
        logo_template.expand('https://cdn/{subsitclean}.png', 'S', 'Sub')


def test_accents_transliterate_instead_of_being_dropped() -> None:
    assert logo_template.expand('{subsiteclean}', 'S', 'Café X') == ['cafex'], 'a hostname needs cafex, not cafx'


def test_every_advertised_placeholder_actually_expands() -> None:
    for token, _note in logo_template.PLACEHOLDERS:
        assert '{' not in logo_template.expand(token, 'Czech AV', 'Czech Streets', 'https://x.com')[0]


def test_a_remembered_template_survives_a_round_trip(store: Path) -> None:
    logo_template.remember('Czech AV', 'https://cdn/{domain}/logo.svg')
    assert logo_template.templates() == {'Czech AV': 'https://cdn/{domain}/logo.svg'}
    assert json.loads(store.read_text(encoding='utf-8'))['Czech AV'] == 'https://cdn/{domain}/logo.svg'


def test_remember_keeps_the_other_studios(store: Path) -> None:
    logo_template.remember('Czech AV', 'a')
    logo_template.remember('Gamma', 'b')
    assert logo_template.templates() == {'Czech AV': 'a', 'Gamma': 'b'}


def test_a_corrupt_store_reads_as_empty_rather_than_raising(store: Path) -> None:
    store.write_text('{not json', encoding='utf-8')
    assert logo_template.templates() == {}


def test_a_blank_template_is_never_persisted(store: Path) -> None:
    logo_template.remember('Czech AV', '')
    assert not store.exists()
