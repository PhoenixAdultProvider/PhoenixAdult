from __future__ import annotations

import pytest

from app.utils.people import PeopleManager, to_plex_roles
from app.utils.people.data import ACTORS_REPLACE, ACTORS_STUDIO_INDEXES
from app.utils.people.types import ResolvedPerson


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    # No cache / IAFD / generic, and only the (offline) Local Storage source, so
    # the resolution pipeline never touches disk or the network.
    monkeypatch.setenv('PEOPLE_CACHE_ENABLE', 'false')
    monkeypatch.setenv('GENDER_DETECT_ENABLE', 'false')
    monkeypatch.setenv('GENERIC_IMAGE_ENABLE', 'false')
    monkeypatch.setenv('PEOPLE_SOURCE_ORDER', 'Local Storage')


def test_data_loaded() -> None:
    assert len(ACTORS_REPLACE) > 300
    assert len(ACTORS_STUDIO_INDEXES) > 50


async def test_alias_resolution() -> None:
    pm = PeopleManager()
    pm.add_actor('abby rains', '')  # alias of 'Abbey Rain' in the global table
    res = await pm.resolve_all(studio='SomeStudio', site_name='SomeSite')
    assert [p.name for p in res['actors']] == ['Abbey Rain']


async def test_skip_name() -> None:
    pm = PeopleManager()
    pm.add_actor('Bad Name', '')
    res = await pm.resolve_all(studio='', site_name='')
    assert res['actors'] == []


async def test_gender_drop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('GENDER_ENABLE', 'true')
    pm = PeopleManager()
    pm.add_actor('John Q Smith', '', 'male')
    res = await pm.resolve_all(studio='', site_name='')
    assert res['actors'] == []


async def test_generic_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('GENERIC_IMAGE_ENABLE', 'true')
    pm = PeopleManager()
    pm.add_actor('Jane Q Roe', '', 'female')
    res = await pm.resolve_all(studio='', site_name='')
    assert res['actors'][0].gender == 'female'
    assert res['actors'][0].photo.endswith('.jpg')


def test_to_plex_roles_proxies_photo() -> None:
    people = [ResolvedPerson(name='Jane Doe', photo='https://cdn.example.com/j.jpg', gender='female', role='actor')]
    roles = to_plex_roles(people, 'http://localhost:3000')
    assert roles[0].tag == 'Jane Doe'
    assert roles[0].thumb is not None
    assert roles[0].thumb.startswith('http://localhost:3000/images/proxy?url=')
    assert roles[0].gender == 'female'
