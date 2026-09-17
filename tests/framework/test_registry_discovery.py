from __future__ import annotations

import importlib
import pathlib
import sys

import pytest

from phoenixadult.clients import CLIENT_REGISTRY
from phoenixadult.clients import _discover as _discover_clients
from phoenixadult.models.site_info import SiteInfo
from phoenixadult.registry import SITE_DEFINITIONS, find_site
from phoenixadult.registry.selectors import _MERGED_SEPARATELY, _discover, _site_lists
from phoenixadult.registry.selectors import SITE_DEFINITIONS as SELECTOR_SITES
from phoenixadult.registry.selectors.aggregators.archive import ARCHIVE_SITES

_ROOT = pathlib.Path(__file__).resolve().parents[2] / 'phoenixadult'
_SELECTORS = _ROOT / 'registry' / 'selectors'
_CLIENTS = _ROOT / 'clients'


def test_the_site_table_only_ever_grows() -> None:
    assert len(SELECTOR_SITES) >= 1236, 'sites disappeared; if you removed them on purpose, lower this floor in the same commit'
    assert len(SITE_DEFINITIONS) >= len(SELECTOR_SITES), 'the archive merge can only add to the selector table'


def test_no_site_name_is_registered_twice() -> None:
    names = [site.name for site in SITE_DEFINITIONS]
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, f'a duplicate name means one selector shadows another: {dupes}'


def test_every_selector_on_disk_was_reached_by_discovery() -> None:
    collected = {id(site) for site in SELECTOR_SITES}
    unreached: list[str] = []
    for path in sorted(_SELECTORS.rglob('*.py')):
        if path.name.startswith('_') or '_data' in path.parts:
            continue

        dotted = 'phoenixadult.registry.selectors.' + '.'.join(path.relative_to(_SELECTORS).with_suffix('').parts)
        if dotted in _MERGED_SEPARATELY:
            continue

        module = importlib.import_module(dotted)
        for site in getattr(module, 'SITES', None) or []:
            if id(site) not in collected:
                unreached.append(f'{path.name} -> {site.name}')

    assert not unreached, f'these live on disk but the package walk never collected them: {unreached}'


def test_every_package_directory_can_be_descended() -> None:
    missing: list[str] = []
    for root in (_SELECTORS, _CLIENTS):
        for path in sorted(root.rglob('*')):
            if not path.is_dir() or any(part.startswith('_') for part in path.relative_to(_ROOT).parts):
                continue

            if not (path / '__init__.py').exists():
                missing.append(path.relative_to(_ROOT).as_posix())

    assert not missing, f'walk_packages cannot descend into a namespace package, so everything under these is invisible: {missing}'


def test_clients_and_selectors_agree_in_both_directions() -> None:
    selector_types = {site.scraper_config.type for site in SITE_DEFINITIONS}
    orphan_sites = sorted(selector_types - CLIENT_REGISTRY.keys())
    assert not orphan_sites, f'selector scraper_type(s) with no client: {orphan_sites}'
    dead_clients = sorted(CLIENT_REGISTRY.keys() - selector_types)
    assert not dead_clients, f'client(s) no site uses: {dead_clients}'


def test_every_archived_site_still_resolves() -> None:
    unresolved = sorted(site.name for site in ARCHIVE_SITES if find_site(site.name) is None)
    assert not unresolved, f'archived sites the registry cannot look up: {unresolved}'


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


def test_a_client_module_with_a_stray_class_is_a_hard_error() -> None:
    stray = _CLIENTS / 'sites' / 'zz_client_probe.py'
    dotted = 'phoenixadult.clients.sites.zz_client_probe'
    stray.write_text('from __future__ import annotations\n\n\nclass ProbeClient:\n    pass\n', encoding='utf-8')
    try:
        importlib.invalidate_caches()
        with pytest.raises(RuntimeError, match='do not subclass Client'):
            _discover_clients()
    finally:
        stray.unlink()
        sys.modules.pop(dotted, None)
        importlib.invalidate_caches()


def test_intermediate_lists_cannot_be_double_registered() -> None:
    from phoenixadult.registry.selectors.networks import fuckyoucash

    assert isinstance(fuckyoucash.PORN_PROS_SITES[0], SiteInfo), 'still a real intermediate list'
    assert fuckyoucash.SITES is not fuckyoucash.PORN_PROS_SITES
    names = [s.name for s in SELECTOR_SITES]
    for site in fuckyoucash.PORN_PROS_SITES:
        assert names.count(site.name) == 1, f'{site.name} was registered twice'
