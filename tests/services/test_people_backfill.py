from __future__ import annotations

from typing import Any

import pytest

from phoenixadult.models.metadata import PlexMetadataResponse
from phoenixadult.models.scrape import ActorResult, SceneDetail
from phoenixadult.utils.cache import people_backfill
from phoenixadult.utils.people import PeopleResolver
from phoenixadult.utils.people.types import ResolvedPerson


def _response(**people: list[dict[str, Any]]) -> PlexMetadataResponse:
    md = {'type': 'movie', 'ratingKey': 'k', 'guid': 'g', 'title': 'T', 'studio': 'S', **people}
    return PlexMetadataResponse.model_validate({'MediaContainer': {'identifier': 'p', 'size': 1, 'Metadata': [md]}})


@pytest.fixture
def resolved(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, list[str]]]:
    calls: list[dict[str, list[str]]] = []

    async def fake_resolve_all(self: PeopleResolver, **_kw: Any) -> dict[str, list[ResolvedPerson]]:
        names = {key: [p.name for p in getattr(self, f'_{key}')] for key in ('actors', 'directors', 'producers')}
        calls.append(names)
        return {
            key: [ResolvedPerson(name=n, photo=f'https://img.example/{n}.jpg', role='', gender='', type='actor') for n in found] for key, found in names.items()
        }

    monkeypatch.setattr(PeopleResolver, 'resolve_all', fake_resolve_all)
    return calls


async def test_nothing_happens_when_everyone_has_a_thumb(resolved: list[dict[str, list[str]]]) -> None:
    response = _response(Role=[{'tag': 'Jane', 'thumb': 'https://img.example/jane.jpg'}])
    assert await people_backfill.backfill_people_images(response, 'Site') is False
    assert resolved == []


async def test_imageless_people_are_looked_up_by_role(resolved: list[dict[str, list[str]]]) -> None:
    response = _response(Role=[{'tag': 'Jane'}], Director=[{'tag': 'Dee'}], Producer=[{'tag': 'Pro'}, {'tag': ''}])
    assert await people_backfill.backfill_people_images(response, 'Site') is True
    assert resolved == [{'actors': ['Jane'], 'directors': ['Dee'], 'producers': ['Pro']}]
    md = response.MediaContainer.Metadata[0]
    assert all(person.thumb for person in [*(md.Role or []), *(md.Director or []), (md.Producer or [])[0]])


async def test_the_scene_refetch_fills_first_and_sources_only_get_the_rest(resolved: list[dict[str, list[str]]]) -> None:
    async def refetch() -> SceneDetail:
        return SceneDetail(title='T', actors=[ActorResult(name='Jane', photo_url='https://scene.example/jane.jpg')])

    response = _response(Role=[{'tag': 'Jane'}, {'tag': 'Ann'}])
    assert await people_backfill.backfill_people_images(response, 'Site', fetch_detail=refetch) is True
    assert resolved == [{'actors': ['Jane'], 'directors': [], 'producers': []}, {'actors': ['Ann'], 'directors': [], 'producers': []}]


@pytest.mark.parametrize('failure', ['raises', 'empty'])
async def test_a_failed_refetch_falls_back_to_sources(resolved: list[dict[str, list[str]]], failure: str) -> None:
    async def refetch() -> SceneDetail | None:
        if failure == 'raises':
            raise RuntimeError('down')
        return None

    response = _response(Role=[{'tag': 'Jane'}])
    assert await people_backfill.backfill_people_images(response, 'Site', fetch_detail=refetch) is True
    assert resolved == [{'actors': ['Jane'], 'directors': [], 'producers': []}]


async def test_a_resolver_failure_never_breaks_the_serve(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(self: PeopleResolver, **_kw: Any) -> None:
        raise RuntimeError('resolver down')

    monkeypatch.setattr(PeopleResolver, 'resolve_all', boom)
    assert await people_backfill.backfill_people_images(_response(Role=[{'tag': 'Jane'}]), 'Site') is False
