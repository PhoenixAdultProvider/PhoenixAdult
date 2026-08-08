from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from tests.conftest import authed_client


def _snapshot_key() -> str:
    from phoenixadult.utils import cache as metadata_cache
    from phoenixadult.utils.cache import scene_store

    md = {'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': 'Scene', 'studio': 'Studio'}
    scene_hash = metadata_cache._hash('Studio', 'cur1')
    payload = {'MediaContainer': {'identifier': 'i', 'size': 1, 'Metadata': [md]}}
    scene_store.upsert('Studio', 'cur1', scene_hash, metadata_cache.bundle_path(scene_hash), payload)
    return str(scene_store.snapshot_state('Studio', 'cur1')['key'])


@pytest.fixture
def pages() -> dict[str, str]:
    rendered = {'setup': TestClient(create_app()).get('/setup').text}
    client = authed_client()
    key = _snapshot_key()
    paths = {
        'config': '/config',
        'metadata': '/metadata',
        'metadata-edit': f'/metadata/edit?key={key}',
        'people': '/people',
        'logos': '/logos',
        'queue': '/queue',
        'account': '/account',
        'dev': '/dev',
    }
    rendered.update({name: client.get(path).text for name, path in paths.items()})
    rendered['login'] = TestClient(create_app()).get('/login').text
    assert 'Create Admin Account' in rendered['setup'], 'the setup page must be captured before an account exists'
    return rendered


def test_every_page_declares_a_mobile_viewport(pages: dict[str, str]) -> None:
    for name, html in pages.items():
        assert '<meta name="viewport" content="width=device-width' in html, f'{name} renders at desktop width on phones'


def test_every_page_has_a_narrow_screen_breakpoint(pages: dict[str, str]) -> None:
    for name, html in pages.items():
        assert re.search(r'@media \(max-width:\s*\d+px\)', html), f'{name} has no mobile layout rules'


def test_pages_with_tables_collapse_them_on_phones(pages: dict[str, str]) -> None:
    for name in ('config', 'account', 'dev'):
        html = pages[name]
        mobile = ''.join(re.findall(r'@media \(max-width:\s*\d+px\)\s*\{(.*?)\n\s{0,6}\}\n', html, re.DOTALL))
        assert 'thead { display: none' in mobile, f'{name} keeps a wide table on phones'


def test_credential_and_account_inputs_avoid_ios_zoom(pages: dict[str, str]) -> None:
    for name in ('login', 'setup', 'account'):
        assert 'font-size: 16px' in pages[name], f'{name} has inputs under 16px, which makes iOS zoom on focus'


def test_the_users_tab_labels_its_cells_for_stacking(pages: dict[str, str]) -> None:
    config = pages['config']
    for marker in ('data-label="Admin"', 'data-label="API Key"', 'data-label="Connections"', '.u-admin::before'):
        assert marker in config, marker


def test_the_theme_pickers_read_light_then_dark_and_stay_inline(pages: dict[str, str]) -> None:
    config = pages['config']
    light, dark = config.index('id="themeLight"'), config.index('id="themeDark"')
    assert light < dark, 'the Light picker should come first, matching the Light/Dark preview pair'
    assert config.index("box(light, 'Light')") < config.index("box(dark, 'Dark')")
    assert '.theme-picker label span { white-space: nowrap; }' in config, 'the labels should not wrap mid-phrase'

    mobile = ''.join(re.findall(r'@media \(max-width:\s*\d+px\)\s*\{(.*?)\n\s{0,6}\}\n', config, re.DOTALL))
    assert '.theme-picker { display: grid; grid-template-columns: 1fr 1fr;' in mobile, 'both pickers should stay side by side on phones'
    assert '.theme-picker select { flex: 1 1 auto; width: 100%; min-width: 0; }' in mobile, 'the selects must shrink out of their 160px desktop floor'


def test_the_account_sessions_table_labels_its_cells(pages: dict[str, str]) -> None:
    account = pages['account']
    for marker in ('data-label="Signed In"', 'data-label="Last Seen"', 'data-label="Device"', '.s-seen::before'):
        assert marker in account, marker


def test_the_queue_lists_sit_side_by_side_and_stack_on_phones(pages: dict[str, str]) -> None:
    queue = pages['queue']
    assert '.queues { display: grid; grid-template-columns: 1fr 1fr;' in queue, 'Searches and Updates should be two columns'
    assert queue.index('id="searches"') < queue.index('id="updates"')
    mobile = ''.join(re.findall(r'@media \(max-width:\s*\d+px\)\s*\{(.*?)\n\s{0,6}\}\n', queue, re.DOTALL))
    assert '.queues { grid-template-columns: 1fr; }' in mobile, 'the columns must stack on phones'
