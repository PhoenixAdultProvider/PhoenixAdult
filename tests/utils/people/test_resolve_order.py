from __future__ import annotations

from typing import Any

import pytest

import phoenixadult.utils.people as people_module
from phoenixadult.utils.http.bypass_types import BypassResponse
from phoenixadult.utils.people import PeopleResolver
from phoenixadult.utils.people.sources import iafd
from phoenixadult.utils.people.types import PhotoHit


@pytest.fixture(autouse=True)
def _no_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PEOPLE_CACHE_ENABLE', 'false')

    async def keep(self: PeopleResolver, name: str, type: str, gender: str) -> str:
        return gender

    async def scene_photo(self: PeopleResolver, name: str, entry: Any, type: str, gender: str, ctx: Any) -> tuple[str, str]:
        return entry.photo, gender

    monkeypatch.setattr(PeopleResolver, '_detect_gender', keep)
    monkeypatch.setattr(PeopleResolver, '_resolve_scene_photo', scene_photo)


def _sources(monkeypatch: pytest.MonkeyPatch, url: str, gender: str = '') -> None:
    async def find(name: str, ctx: Any) -> PhotoHit:
        return PhotoHit(url=url, gender=gender, source='Src')  # type: ignore[arg-type]

    monkeypatch.setattr(people_module, 'find_photo', find)


async def _resolve(gender: str = '', photo: str = 'https://scene.example/jane.jpg') -> tuple[str, str]:
    people = PeopleResolver()
    people.add_actor('Jane Doe', photo, gender)  # type: ignore[arg-type]
    resolved = (await people.resolve_all(studio='S', site_name='Site'))['actors'][0]
    return resolved.photo, resolved.gender


@pytest.mark.parametrize(
    ('scene_first', 'photo', 'gender'), [(True, 'https://scene.example/jane.jpg', ''), (False, 'https://source.example/jane.jpg', 'female')]
)
async def test_the_scene_image_preference_orders_scene_and_sources(monkeypatch: pytest.MonkeyPatch, scene_first: bool, photo: str, gender: str) -> None:
    monkeypatch.setattr(people_module, 'scene_image_pref', lambda: (True, scene_first))
    _sources(monkeypatch, 'https://source.example/jane.jpg', 'female')
    assert await _resolve() == (photo, gender)


async def test_the_scene_image_is_skipped_when_scene_images_are_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(people_module, 'scene_image_pref', lambda: (False, True))
    _sources(monkeypatch, '')
    assert await _resolve() == ('', '')


@pytest.mark.parametrize(('enabled', 'gender', 'generic'), [(True, 'female', True), (True, '', False), (False, 'female', False)])
async def test_a_generic_image_is_the_last_resort(monkeypatch: pytest.MonkeyPatch, enabled: bool, gender: str, generic: bool) -> None:
    monkeypatch.setenv('GENERIC_IMAGE_ENABLE', 'true' if enabled else 'false')
    monkeypatch.setattr(people_module, 'scene_image_pref', lambda: (False, False))
    _sources(monkeypatch, '')
    photo, _gender = await _resolve(gender=gender, photo='')
    assert (photo == people_module.generic_image_url(gender)) if generic else photo == ''  # type: ignore[arg-type]


_IAFD_PAGE = """<html><body>
<table id="tblFem"><tbody>
  <tr><td></td><td><a href="/person.rme/id=1">Jane Doe</a></td><td class="text-left">Brazzers</td></tr>
  <tr><td></td><td><a href="/person.rme/id=2">Jane Doh</a></td><td class="text-left">Vixen</td></tr>
  <tr><td></td><td><a></a></td><td class="text-left">blank</td></tr>
</tbody></table>
<table id="tblMal"><tbody>
  <tr><td></td><td><a href="/person.rme/id=3">John Roe</a></td><td class="text-left">Studio X</td></tr>
</tbody></table></body></html>"""


@pytest.mark.parametrize(
    ('name', 'studio', 'expected'),
    [
        ('Jane Doe', '', ('/person.rme/id=1', 'female')),
        ('Jane Do', '', ('/person.rme/id=1', 'female')),
        ('Jane Do', 'Vixen', ('/person.rme/id=2', 'female')),
        ('John Roe', '', ('/person.rme/id=3', 'male')),
    ],
)
async def test_iafd_picks_the_closest_name_unless_a_studio_matches(monkeypatch: pytest.MonkeyPatch, name: str, studio: str, expected: tuple[str, str]) -> None:
    async def fake_get(url: str, **_kw: Any) -> BypassResponse:
        return BypassResponse(status=200, body=_IAFD_PAGE)

    monkeypatch.setattr(iafd, 'bypass_get', fake_get)
    assert await iafd.iafd_best_match(name, studio) == expected


@pytest.mark.parametrize('response', [None, BypassResponse(status=503, body=''), BypassResponse(status=200, body='<html></html>')])
async def test_iafd_returns_nothing_without_a_usable_result(monkeypatch: pytest.MonkeyPatch, response: BypassResponse | None) -> None:
    async def fake_get(url: str, **_kw: Any) -> BypassResponse | None:
        return response

    monkeypatch.setattr(iafd, 'bypass_get', fake_get)
    assert await iafd.iafd_best_match('Jane Doe') is None
