from __future__ import annotations

import pathlib

import pytest

from phoenixadult.models.site_info import SiteInfo
from phoenixadult.registry import SITE_DEFINITIONS
from phoenixadult.registry.selectors import _MERGED_SEPARATELY, _discover, _site_lists
from phoenixadult.registry.selectors import SITE_DEFINITIONS as SELECTOR_SITES

_SELECTORS = pathlib.Path(__file__).resolve().parent.parent / 'phoenixadult' / 'registry' / 'selectors'


def test_the_site_table_is_the_size_we_expect() -> None:
    assert len(SELECTOR_SITES) == 1236
    assert len(SITE_DEFINITIONS) == 1286, 'selector sites plus the archive merge'


def test_no_site_name_is_registered_twice() -> None:
    names = [site.name for site in SITE_DEFINITIONS]
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, f'a duplicate name means one selector shadows another: {dupes}'


def test_every_selector_module_exports_sites_or_none_at_all() -> None:
    assert _MERGED_SEPARATELY == {'phoenixadult.registry.selectors.aggregators.archive'}, 'the only module allowed to opt out'
    missing = []
    for path in sorted(_SELECTORS.rglob('*.py')):
        if path.name.startswith('_') or '_data' in path.parts:
            continue
        dotted = 'phoenixadult.registry.selectors.' + '.'.join(path.relative_to(_SELECTORS).with_suffix('').parts)
        if dotted in _MERGED_SEPARATELY:
            continue
        module = __import__(dotted, fromlist=['SITES'])
        if getattr(module, 'SITES', None) is None and _site_lists(module):
            missing.append(path.name)
    assert not missing, f'these define site lists that discovery would never collect: {missing}'


def test_a_module_with_sites_but_no_export_is_a_hard_error(tmp_path: pathlib.Path) -> None:
    stray = _SELECTORS / 'sites' / 'zz_discovery_probe.py'
    stray.write_text(
        'from __future__ import annotations\n\n'
        'from phoenixadult.registry.selectors._factory import make_site\n\n'
        "FORGOTTEN = [make_site(name='Discovery Probe', scraper_type='manualnfo', base_url='https://probe.test')]\n",
        encoding='utf-8',
    )
    try:
        with pytest.raises(RuntimeError, match='exports no SITES'):
            _discover()
    finally:
        stray.unlink()


def test_intermediate_lists_cannot_be_double_registered() -> None:
    from phoenixadult.registry.selectors.networks import fuckyoucash

    assert isinstance(fuckyoucash.PORN_PROS_SITES[0], SiteInfo), 'still a real intermediate list'
    assert fuckyoucash.SITES is not fuckyoucash.PORN_PROS_SITES
    names = [s.name for s in SELECTOR_SITES]
    for site in fuckyoucash.PORN_PROS_SITES:
        assert names.count(site.name) == 1, f'{site.name} was registered twice'
