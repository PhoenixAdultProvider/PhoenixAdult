from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from phoenixadult.routes import render_nav

TOKEN = 'navtoken'
PAGES = (('/metadata', 'Metadata'), ('/people', 'People'), ('/logos', 'Logos'), ('/queue', 'Queue'), ('/dev', 'Dev'), ('/config', 'Config'))


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv('NODE_ENV', 'development')
    monkeypatch.setenv('ADMIN_TOKEN', TOKEN)
    return TestClient(create_app())


@pytest.mark.parametrize(('path', 'label'), PAGES)
def test_every_page_carries_the_nav_with_its_own_tab_active(client: TestClient, path: str, label: str) -> None:
    body = client.get(path, headers={'x-admin-token': TOKEN}).text
    assert '__NAV__' not in body
    assert body.count('class="app-nav"') == 1
    for _, other in PAGES:
        assert f'>{other}</a>' in body
    assert body.count('class="active" aria-current="page"') == 1
    assert f'<a href="{path}" class="active" aria-current="page">{label}</a>' in body


def test_edit_subpages_highlight_their_parent(client: TestClient) -> None:
    people = client.get('/people/edit?filename=nobody.jpg', headers={'x-admin-token': TOKEN})
    assert people.status_code == 404
    assert '<a href="/people" class="active"' in render_nav('people')
    assert '<a href="/metadata" class="active"' in render_nav('metadata')


def test_config_sits_at_the_end_of_the_nav(monkeypatch: pytest.MonkeyPatch) -> None:
    import re

    monkeypatch.setenv('NODE_ENV', 'development')
    assert re.findall(r'>([^<]+)</a>', render_nav('metadata')) == ['Metadata', 'People', 'Logos', 'Queue', 'Dev', 'Config']
    monkeypatch.setenv('NODE_ENV', 'production')
    assert re.findall(r'>([^<]+)</a>', render_nav('metadata')) == ['Metadata', 'People', 'Logos', 'Queue', 'Config']


def test_dev_link_hidden_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('NODE_ENV', 'production')
    nav = render_nav('config')
    assert '>Dev</a>' not in nav and '>Config</a>' in nav


def test_nav_carries_the_admin_token_to_the_other_pages(client: TestClient) -> None:
    body = client.get('/queue', headers={'x-admin-token': TOKEN}).text
    assert "URLSearchParams(location.search).get('token')" in body
