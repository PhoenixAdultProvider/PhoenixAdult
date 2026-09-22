from __future__ import annotations

from phoenixadult.clients.base import Client
from phoenixadult.models.scrape import SearchResult


def _result(url: str) -> SearchResult:
    return SearchResult(title=url, scene_url=url, cur_id=url)


async def test_short_page_stops_pagination() -> None:
    client = Client()
    fetched: list[int] = []

    async def fetch_rows(page: int) -> list[str] | None:
        fetched.append(page)
        return [f'p{page}-{i}' for i in range(9)] if page == 1 else ['p2-0']

    results = await client.paginate_search(fetch_rows=fetch_rows, build_row=_result, max_pages=5, full_page=9)
    assert fetched == [1, 2]
    assert len(results) == 10


async def test_max_pages_cap() -> None:
    client = Client()
    fetched: list[int] = []

    async def fetch_rows(page: int) -> list[str]:
        fetched.append(page)
        return [f'p{page}']

    results = await client.paginate_search(fetch_rows=fetch_rows, build_row=_result, max_pages=3)
    assert fetched == [1, 2, 3]
    assert len(results) == 3


async def test_fetch_none_stops() -> None:
    client = Client()

    async def fetch_rows(page: int) -> list[str] | None:
        return ['a'] if page == 1 else None

    results = await client.paginate_search(fetch_rows=fetch_rows, build_row=_result, max_pages=5)
    assert [r.scene_url for r in results] == ['a']


async def test_skip_and_dedup() -> None:
    client = Client()

    async def fetch_rows(page: int) -> list[str] | None:
        return ['a', 'skip', 'a', 'b'] if page == 1 else None

    results = await client.paginate_search(
        fetch_rows=fetch_rows,
        build_row=lambda r: None if r == 'skip' else _result(r),
        max_pages=2,
    )
    assert [r.scene_url for r in results] == ['a', 'b']


async def test_stop_on_empty_page() -> None:
    client = Client()
    fetched: list[int] = []

    async def fetch_rows(page: int) -> list[str] | None:
        fetched.append(page)
        return ['a', 'b'] if page == 1 else ['skip', 'skip']

    results = await client.paginate_search(
        fetch_rows=fetch_rows,
        build_row=lambda r: None if r == 'skip' else _result(r),
        max_pages=5,
        stop_on_empty_page=True,
    )
    assert fetched == [1, 2]
    assert [r.scene_url for r in results] == ['a', 'b']


async def test_should_continue_stops_after_page() -> None:
    client = Client()
    fetched: list[int] = []

    async def fetch_rows(page: int) -> list[str]:
        fetched.append(page)
        return ['perfect'] if page == 1 else ['other']

    results = await client.paginate_search(
        fetch_rows=fetch_rows,
        build_row=lambda r: SearchResult(title=r, scene_url=r, cur_id=r, score=100 if r == 'perfect' else 1),
        max_pages=5,
        should_continue=lambda out: not any((r.score or 0) >= 100 for r in out),
    )
    assert fetched == [1]
    assert [r.scene_url for r in results] == ['perfect']


async def test_dedup_false_keeps_shared_scene_url() -> None:
    client = Client()

    async def fetch_rows(page: int) -> list[str] | None:
        return ['a', 'b'] if page == 1 else None

    results = await client.paginate_search(
        fetch_rows=fetch_rows,
        build_row=lambda r: SearchResult(title=r, scene_url='shared', cur_id=r),
        max_pages=2,
        dedup=False,
    )
    assert [r.cur_id for r in results] == ['a', 'b']


async def test_custom_dedup_key() -> None:
    client = Client()

    async def fetch_rows(page: int) -> list[str] | None:
        return ['a|1', 'a|2'] if page == 1 else None

    results = await client.paginate_search(
        fetch_rows=fetch_rows,
        build_row=lambda r: SearchResult(title=r, scene_url=r.split('|')[0], cur_id=r),
        max_pages=2,
        dedup_key=lambda r: r.cur_id,
    )
    assert [r.cur_id for r in results] == ['a|1', 'a|2']
