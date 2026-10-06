from __future__ import annotations

import pytest

from phoenixadult.routes import image_routes
from tests.support import authed_client


@pytest.fixture
def upstream(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    fetched: list[str] = []

    async def public(url: str) -> str:
        return url

    async def failing(url: str, *args: object, **kwargs: object) -> object:
        fetched.append(url)
        raise ValueError('403 from upstream')

    monkeypatch.setattr(image_routes, 'assert_fetchable_url', public)
    monkeypatch.setattr(image_routes, 'fetch_image', failing)
    return fetched


def test_a_failed_upstream_is_remembered_instead_of_refetched(upstream: list[str]) -> None:
    client = authed_client()
    for _ in range(3):
        assert client.get('/images/proxy', params={'url': 'https://cdn.example.com/a.jpg'}).status_code == 502
    assert upstream == ['https://cdn.example.com/a.jpg']
    assert client.get('/images/proxy', params={'url': 'https://cdn.example.com/b.jpg'}).status_code == 502
    assert len(upstream) == 2, 'other URLs still go out'


def test_failures_while_the_network_drops_are_not_remembered(monkeypatch: pytest.MonkeyPatch, upstream: list[str]) -> None:
    monkeypatch.setattr(image_routes, 'network_down', lambda: True)
    client = authed_client()
    for _ in range(2):
        client.get('/images/proxy', params={'url': 'https://cdn.example.com/a.jpg'})
    assert len(upstream) == 2
