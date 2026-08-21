from __future__ import annotations

from phoenixadult.utils.http.client import shared_http


async def test_one_client_is_reused_per_tag() -> None:
    assert shared_http('people-image') is shared_http('people-image')


async def test_different_tags_get_different_clients() -> None:
    assert shared_http('people-image') is not shared_http('people-head')


async def test_a_shared_client_keeps_connections_alive() -> None:
    client = shared_http('people-image')
    assert not client.is_closed, 'a per-request client would be closed and force a new TLS handshake each time'
