from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.routes import render_nav
from tests.conftest import authed_client

PAGES = (('/metadata', 'Metadata'), ('/people', 'People'), ('/logos', 'Logos'), ('/queue', 'Queue'), ('/dev', 'Dev'), ('/config', 'Config'))


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv('NODE_ENV', 'development')
    return authed_client()


@pytest.mark.parametrize(('path', 'label'), PAGES)
def test_every_page_carries_the_nav_with_its_own_tab_active(client: TestClient, path: str, label: str) -> None:
    body = client.get(path).text
    assert '__NAV__' not in body
    assert body.count('class="app-nav"') == 1
    for _, other in PAGES:
        assert f'>{other}</a>' in body
    assert body.count('class="active" aria-current="page"') == 1
    assert f'<a href="{path}" class="active" aria-current="page">{label}</a>' in body


def test_edit_subpages_highlight_their_parent(client: TestClient) -> None:
    people = client.get('/people/edit?filename=nobody.jpg')
    assert people.status_code == 404
    assert '<a href="/people" class="active"' in render_nav('people')
    assert '<a href="/metadata" class="active"' in render_nav('metadata')


def test_config_sits_at_the_end_of_the_nav(monkeypatch: pytest.MonkeyPatch) -> None:
    import re

    monkeypatch.setenv('NODE_ENV', 'development')
    labels = re.findall(r'>([^<]+)</a>', render_nav('metadata'))
    assert [x for x in labels if x != 'Log Out'][:6] == ['Metadata', 'People', 'Logos', 'Queue', 'Dev', 'Config']
    monkeypatch.setenv('NODE_ENV', 'production')
    labels = re.findall(r'>([^<]+)</a>', render_nav('metadata'))
    assert [x for x in labels if x != 'Log Out'][:5] == ['Metadata', 'People', 'Logos', 'Queue', 'Config']


def test_dev_link_hidden_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('NODE_ENV', 'production')
    nav = render_nav('config')
    assert '>Dev</a>' not in nav and '>Config</a>' in nav


def test_nav_shows_the_user_menu_and_logout(client: TestClient) -> None:
    body = client.get('/queue').text
    assert 'class="nav-user"' in body and 'href="/account"' in body
    assert 'nav-logout' in body and 'Log Out' in body
    assert "URLSearchParams(location.search).get('token')" not in body


def test_nav_without_a_username_has_no_user_menu() -> None:
    nav = render_nav('config')
    assert 'class="nav-user"' not in nav and '<button type="button" class="nav-logout"' not in nav


def test_every_page_carries_the_theme_loader_and_toggle(client: TestClient) -> None:
    body = client.get('/queue').text
    assert '<link id="pa-theme-css" rel="stylesheet" href="/themes/midnight.css">' in body
    assert 'prefers-color-scheme: light' in body
    assert 'localStorage.getItem' in body and 'pa-theme' in body
    assert "dark: ['midnight', 'forest'], light: ['day', 'meadow']" in body
    for mode in ('light', 'auto', 'dark'):
        assert f'data-set="{mode}"' in body


def test_theme_stylesheets_are_served_and_unknown_names_404(client: TestClient) -> None:
    for name in ('midnight', 'day', 'forest', 'meadow'):
        r = client.get(f'/themes/{name}.css')
        assert r.status_code == 200 and r.headers['content-type'].startswith('text/css')
        assert f'data-theme-name="{name}"' in r.text
    assert client.get('/themes/nope.css').status_code == 404


def test_pages_reference_theme_variables_never_raw_colors() -> None:
    import re
    from pathlib import Path

    import phoenixadult.routes as routes

    html_dir = Path(routes.__file__).parent / 'html'
    sources = [*html_dir.glob('*.html'), Path(routes.__file__).parent / 'people_cache_routes.py']
    for f in sources:
        hexes = set(re.findall(r'#[0-9a-fA-F]{3,8}\b', f.read_text(encoding='utf-8'))) - {'#000'}
        assert not hexes, f'{f.name} has raw colors: {sorted(hexes)}'


def test_every_template_variable_is_defined_in_every_theme() -> None:
    import re
    from pathlib import Path

    import phoenixadult.routes as routes

    html_dir = Path(routes.__file__).parent / 'html'
    refs: set[str] = set()
    for f in [*html_dir.glob('*.html'), Path(routes.__file__).parent / 'people_cache_routes.py']:
        refs.update(re.findall(r'var\((--[a-z0-9-]+)\)', f.read_text(encoding='utf-8')))
    refs.discard('--app-nav-h')
    themes = list((html_dir / 'themes').glob('*.css'))
    assert len(themes) == 4
    for theme in themes:
        defined = set(re.findall(r'^\s*(--[a-z0-9-]+):', theme.read_text(encoding='utf-8'), re.M))
        missing = sorted(refs - defined)
        assert not missing, f'{theme.name} is missing: {missing}'
