from __future__ import annotations

from typing import Any

from parsel import Selector

from phoenixadult.clients.base import FetchCtx
from phoenixadult.clients.networks.intersec import IntersecClient
from phoenixadult.registry import find_site


async def _page(self: Any, url: str, ctx: FetchCtx | None = None, label: str | None = None, form: dict[str, str] | None = None) -> dict[str, Any]:
    html = '<html><body></body></html>'
    return {'status': 200, 'html': html, 'sel': Selector(text=html)}


async def test_the_packed_cover_never_leaks_into_the_release_date(monkeypatch: Any) -> None:
    client = IntersecClient()
    monkeypatch.setattr(IntersecClient, 'fetch_and_load', _page)
    site = find_site('Insex')
    assert site is not None
    detail = await client._scene_detail_flow('https://x.test/scene/1|2024-01-05|aHR0cHM6Ly94LnRlc3QvYy5qcGc', site)
    assert detail is not None
    assert detail.release_date == '2024-01-05'
    assert 'https://x.test/c.jpg' in detail.art
