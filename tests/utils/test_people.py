from __future__ import annotations

import httpx
import pytest
import respx

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


async def test_silhouette_from_discovered_gender(monkeypatch: pytest.MonkeyPatch) -> None:
    # A director with no input gender, found by a source that knows the gender but
    # has no image (IAFD placeholder), still gets the gendered silhouette.
    import app.utils.people.sources as sources
    from app.utils.people.types import PhotoHit

    class _GenderOnly:
        name = 'GenderOnly'

        async def find(self, _name: str, _ctx: object) -> PhotoHit:
            return PhotoHit(url='', gender='male')

    monkeypatch.setenv('GENERIC_IMAGE_ENABLE', 'true')
    monkeypatch.setattr(sources, '_configured_order', lambda: [_GenderOnly()])
    pm = PeopleManager()
    pm.add_director('Ken Shiro', '')
    res = await pm.resolve_all(studio='', site_name='')
    assert res['directors'][0].gender == 'male'
    assert res['directors'][0].photo.endswith('.jpg')


@respx.mock
async def test_silhouette_is_cached(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    # The gendered silhouette is cached under the person so the next lookup is a
    # local-cache hit rather than another full source-chain run.
    import app.utils.people.sources as sources
    from app.utils.people.types import PhotoHit

    class _GenderOnly:
        name = 'GenderOnly'

        async def find(self, _name: str, _ctx: object) -> PhotoHit:
            return PhotoHit(url='', gender='male')

    monkeypatch.setenv('GENERIC_IMAGE_ENABLE', 'true')
    monkeypatch.setenv('PEOPLE_CACHE_ENABLE', 'true')
    monkeypatch.setenv('PEOPLE_CACHE_DIR', str(tmp_path))
    monkeypatch.setenv('GENERIC_MALE_URL', 'https://cdn.example/silhouette-m.jpg')
    monkeypatch.setattr(sources, '_configured_order', lambda: [_GenderOnly()])
    respx.get('https://cdn.example/silhouette-m.jpg').mock(return_value=httpx.Response(200, content=b'SILHOUETTE', headers={'content-type': 'image/jpeg'}))

    pm = PeopleManager()
    pm.add_director('Ken Shiro', '')
    res = await pm.resolve_all(studio='', site_name='')

    assert res['directors'][0].photo.endswith('/images/local/director.ken-shiro_male.jpg')
    assert (tmp_path / 'director.ken-shiro_male.jpg').read_bytes() == b'SILHOUETTE'


def test_to_plex_roles_proxies_photo() -> None:
    people = [ResolvedPerson(name='Jane Doe', photo='https://cdn.example.com/j.jpg', gender='female', role='actor')]
    roles = to_plex_roles(people, 'http://localhost:3000')
    assert roles[0].tag == 'Jane Doe'
    assert roles[0].thumb is not None
    assert roles[0].thumb.startswith('http://localhost:3000/images/proxy?url=')
    assert roles[0].gender == 'female'
