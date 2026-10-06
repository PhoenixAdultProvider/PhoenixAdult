from __future__ import annotations

import re


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
    for marker in ('data-label="\' + esc(T.col_admin)', 'data-label="\' + esc(T.col_api_key)', 'data-label="\' + esc(T.col_connections)', '.u-admin::before'):
        assert marker in config, marker


def test_the_theme_pickers_read_light_then_dark_and_stay_inline(pages: dict[str, str]) -> None:
    config = pages['config']
    light, dark = config.index('id="themeLight"'), config.index('id="themeDark"')
    assert light < dark, 'the Light picker should come first, matching the Light/Dark preview pair'
    assert config.index('box(light, T.preview_light)') < config.index('box(dark, T.preview_dark)')
    assert '.theme-picker label span { white-space: nowrap; }' in config, 'the labels should not wrap mid-phrase'

    mobile = ''.join(re.findall(r'@media \(max-width:\s*\d+px\)\s*\{(.*?)\n\s{0,6}\}\n', config, re.DOTALL))
    assert '.theme-picker { display: grid; grid-template-columns: 1fr 1fr;' in mobile, 'both pickers should stay side by side on phones'
    assert '.theme-picker select { flex: 1 1 auto; width: 100%; min-width: 0; }' in mobile, 'the selects must shrink out of their 160px desktop floor'


def test_the_account_sessions_table_labels_its_cells(pages: dict[str, str]) -> None:
    account = pages['account']
    for marker in ('data-label="${T.signed_in}"', 'data-label="${T.last_seen}"', 'data-label="${T.device}"', '.s-seen::before'):
        assert marker in account, marker


def test_the_queue_lists_are_columns_on_desktop_and_tabs_on_phones(pages: dict[str, str]) -> None:
    queue = pages['queue']
    assert '.queues { display: grid; grid-template-columns: 1fr 1fr;' in queue, 'Searches and Updates should be two columns on desktop'
    assert '.queue-tabs { display: none; }' in queue, 'the tab bar stays hidden on desktop'
    assert queue.index('id="searches"') < queue.index('id="updates"')

    mobile = ''.join(re.findall(r'@media \(max-width:\s*\d+px\)\s*\{(.*?)\n\s{0,6}\}\n', queue, re.DOTALL))
    assert '.queue-tabs { display: flex;' in mobile, 'phones get the Searches/Updates tab bar'
    assert ".queues[data-active='search'] #updates-col { display: none; }" in mobile, 'only the active list shows on phones'
    assert ".queues[data-active='update'] #searches-col { display: none; }" in mobile
    assert 'data-active="search"' in queue, 'Searches is the default tab'
    assert "showQueue('update')" in queue and 'function showQueue' in queue
