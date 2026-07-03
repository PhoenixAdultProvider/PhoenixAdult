from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from app.utils.people import PeopleManager, to_plex_roles
from app.utils.people.data import actor_rules
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
    rules = actor_rules()
    assert len(rules.replace) > 300
    assert len(rules.studio_indexes) > 50


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


async def test_male_actor_resolved_not_dropped_at_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    # Male actors are always resolved + cached (faster future gender resolution); they are
    # hidden at serve time by filter_male_actors, not dropped here.
    monkeypatch.setenv('GENDER_SKIP_MALE_ENABLE', 'true')
    pm = PeopleManager()
    pm.add_actor('John Q Smith', '', 'male')
    res = await pm.resolve_all(studio='', site_name='')
    assert [a.gender for a in res['actors']] == ['male']


def _response_with_roles(roles: list[dict[str, str]]) -> Any:
    from app.models.metadata import PlexMetadataResponse

    return PlexMetadataResponse.model_validate(
        {'MediaContainer': {'identifier': 'id', 'size': 1, 'Metadata': [{'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': 'T', 'Role': roles}]}}
    )


def test_filter_male_actors_noop_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('GENDER_SKIP_MALE_ENABLE', 'false')
    from app.utils.people import filter_male_actors

    resp = _response_with_roles([{'tag': 'A', 'gender': 'male'}, {'tag': 'B', 'gender': 'female'}])
    assert filter_male_actors(resp) == 0
    assert [r.tag for r in resp.MediaContainer.Metadata[0].Role] == ['A', 'B']


def test_filter_male_actors_drops_male_by_field_and_filename(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('GENDER_SKIP_MALE_ENABLE', 'true')
    from app.utils.people import filter_male_actors

    resp = _response_with_roles(
        [
            {'tag': 'Male Field', 'gender': 'male'},
            {'tag': 'Female', 'gender': 'female'},
            {'tag': 'Male Filename', 'thumb': '/images/local/actor.male-filename_male.jpg'},
            {'tag': 'Unknown', 'gender': ''},
        ]
    )
    assert filter_male_actors(resp) == 2
    assert [r.tag for r in resp.MediaContainer.Metadata[0].Role] == ['Female', 'Unknown']


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

    assert '/images/local/directors/director.ken-shiro_male.jpg?v=' in res['directors'][0].photo  # subfolder + cache-bust
    assert (tmp_path / 'directors' / 'director.ken-shiro_male.jpg').read_bytes() == b'SILHOUETTE'  # type: ignore[operator]


@pytest.mark.parametrize(
    ('order', 'expected'),
    [
        (None, (True, True)),  # unset -> scene image first, then providers
        ('Local Storage', (False, False)),  # set without 'Scene' -> skip the scene image
        ('Local Storage,Scene,AdultDVDEmpire', (True, True)),  # default shape -> scene before providers
        ('Scene,Freeones', (True, True)),  # scene ahead of a provider -> first
        ('Freeones,Scene', (True, False)),  # a provider ahead of scene -> scene is a fallback
        ('Local Storage,Scene', (True, True)),  # cache isn't a provider -> still scene-first
    ],
)
def test_scene_image_pref(monkeypatch: pytest.MonkeyPatch, order: str | None, expected: tuple[bool, bool]) -> None:
    from app.utils.people.sources import scene_image_pref

    if order is None:
        monkeypatch.delenv('PEOPLE_SOURCE_ORDER', raising=False)
    else:
        monkeypatch.setenv('PEOPLE_SOURCE_ORDER', order)
    assert scene_image_pref() == expected


@respx.mock
async def test_scene_image_used_when_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    # 'Scene' present -> the scene's own actor image is used (HEAD-checked), not skipped.
    monkeypatch.setenv('PEOPLE_SOURCE_ORDER', 'Scene,Local Storage')
    respx.head('https://cdn.example/scene.jpg').mock(return_value=httpx.Response(200))
    pm = PeopleManager()
    pm.add_actor('Jane Roe', 'https://cdn.example/scene.jpg', 'female')
    res = await pm.resolve_all(studio='', site_name='')
    assert res['actors'][0].photo == 'https://cdn.example/scene.jpg'


async def test_scene_image_skipped_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    # 'Scene' absent from a set order -> the scene image is skipped entirely (no HEAD, no use).
    monkeypatch.setenv('PEOPLE_SOURCE_ORDER', 'Local Storage')
    pm = PeopleManager()
    pm.add_actor('Jane Roe', 'https://cdn.example/scene.jpg', 'female')
    res = await pm.resolve_all(studio='', site_name='')
    assert res['actors'][0].photo == ''


def test_to_plex_roles_proxies_photo() -> None:
    people = [ResolvedPerson(name='Jane Doe', photo='https://cdn.example.com/j.jpg', gender='female', role='actor')]
    roles = to_plex_roles(people, 'http://localhost:3000')
    assert roles[0].tag == 'Jane Doe'
    assert roles[0].thumb is not None
    assert roles[0].thumb.startswith('http://localhost:3000/images/proxy?url=')
    assert roles[0].gender == 'female'
