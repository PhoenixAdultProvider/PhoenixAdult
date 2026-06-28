from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from app.clients.aggregators.data18 import Data18Client
from app.clients.base import ActorResult, Client, LoadedScene, SceneContext, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, date_distance_score, iso_date, pack_cur_id, title_distance_score
from app.utils.helpers.html_helpers import first_attr
from app.utils.logging.logger import logger
from app.utils.searchengines import SearchOptions, web_search


def _swap_article(raw: str) -> str:
    lower = raw.lower()
    if lower.endswith(', the'):
        return f'The {raw[:-5]}'
    if lower.endswith(', a'):
        return f'A {raw[:-3]}'
    return raw


def _resolve_studio(sel: Any) -> str:
    node = sel.xpath('(//b[contains(.,"Studio") or contains(.,"Network")])[1]')
    if node:
        s = first_attr(node[0], 'following-sibling::b[1]/text()')
        if not s:
            s = first_attr(node[0], 'following-sibling::a[1]/text()')
        if s:
            return s
    return first_attr(sel, '(//p[contains(.,"Site:")]//a[contains(@class,"bold")])[1]/text()')


class Data18MoviesClient(Client):
    def __init__(self) -> None:
        super().__init__()
        self._data18 = Data18Client()

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        scene_id = ctx.scene_id if ctx.scene_id and ctx.scene_id.isdigit() and int(ctx.scene_id) > 100 else ''
        text = ctx.title.strip()

        movie_urls: set[str] = set()
        if scene_id:
            movie_urls.add(f'{base}/movies/{scene_id}')

        candidates = []
        try:
            candidates = await self._data18.find_candidates(text or ctx.title, 'movies')
        except Exception as err:  # noqa: BLE001
            logger.warn(ctx.site_info.name, f'find_candidates failed: {err}')

        try:
            host = urlsplit(ctx.site_info.base_url).hostname or ''
            for u in await web_search(SearchOptions(query=ctx.title, site=host, num=10)):
                cleaned = u.split('-')[0].replace('http:', 'https:')
                if '/movies/' in cleaned and '.html' not in cleaned:
                    movie_urls.add(cleaned)
        except Exception as err:  # noqa: BLE001
            logger.debug(ctx.site_info.name, f'webSearch threw: {err}')

        results: list[SearchResult] = []
        seen: set[str] = set()

        for c in candidates:
            if c.url in seen:
                continue
            seen.add(c.url)
            movie_urls.discard(c.url)
            direct_hit = scene_id != '' and scene_id == c.url_id
            title = c.title_raw
            if c.truncated:
                loaded = await self._data18.fetch_page(c.url)
                if loaded is not None:
                    title = _swap_article(first_attr(loaded, '(//h1)[1]/text()') or title)
            score = (
                100
                if direct_hit
                else (
                    date_distance_score(ctx.search_date, c.release_date)
                    if ctx.search_date and c.release_date
                    else title_distance_score(text or ctx.title, title)
                )
            )
            results.append(
                build_search_result(
                    title=title,
                    scene_url=c.url,
                    query=text or ctx.title,
                    display_date=c.release_date,
                    search_date=ctx.search_date,
                    score=score,
                    cur_id=pack_cur_id([p for p in (c.url, c.release_date) if p]),
                )
            )

        for movie_url in movie_urls:
            if movie_url in seen:
                continue
            seen.add(movie_url)
            loaded = await self._data18.fetch_page(movie_url)
            if loaded is None:
                continue
            title = _swap_article(first_attr(loaded, '(//h1)[1]/text()'))
            if not title:
                continue
            url_id = re.sub(r'.*/', '', movie_url)
            direct_hit = scene_id != '' and scene_id == url_id
            date_attr = first_attr(loaded, '(//*[@datetime])[1]/@datetime')
            release_date = iso_date(date_attr) or ''
            score = (
                100
                if direct_hit
                else (
                    date_distance_score(ctx.search_date, release_date) if ctx.search_date and release_date else title_distance_score(text or ctx.title, title)
                )
            )
            results.append(
                build_search_result(
                    title=title,
                    scene_url=movie_url,
                    query=text or ctx.title,
                    display_date=release_date or None,
                    search_date=ctx.search_date,
                    score=score,
                    cur_id=pack_cur_id([p for p in (movie_url, release_date) if p]),
                )
            )
        return results

    # ── Context loader ────────────────────────────────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        url, _, tail = payload.partition('|')
        fallback_date = tail.strip()
        loaded = await self._data18.fetch_page(url)
        if loaded is None:
            return None
        return LoadedScene(url=url, site=site, scene_date=fallback_date or None, capture=ctx.capture if ctx else None, sel=loaded)

    # ── Field hooks ─────────────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_attr(scene.sel, '(//h1)[1]/text()')
        return _swap_article(raw) if raw else None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        for div in scene.sel.xpath('//div[contains(@class,"gen12")]//div'):
            t = div.xpath('string(.)').get() or ''
            if 'Description' in t and re.search(r'Studio|Network', t):
                summary = t.split('---')[-1].split('Description -')[-1].strip()
                return summary.replace('\xa0', ' ') if len(summary) > 1 else None
        return None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return _resolve_studio(scene.sel) or None

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_attr(scene.sel, '(//p[contains(.,"Movie Series")]//a[@title])[1]/text()') or None

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        studio = _resolve_studio(scene.sel)
        series = first_attr(scene.sel, '(//p[contains(.,"Movie Series")]//a[@title])[1]/text()')
        out: list[str] = []
        if studio:
            out.append(studio)
        if series and series not in out:
            out.append(series)
        return out or None

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        attr = first_attr(scene.sel, '(//*[@datetime])[1]/@datetime')
        return iso_date(attr) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//p[.//b[contains(.,"Categories")]]//a')]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()

        def add(name: str, photo: str = '') -> None:
            n = (name or '').strip().replace('\xa0', ' ')
            if n and n not in seen:
                seen.add(n)
                actors.append(ActorResult(name=n, photo_url=photo))

        for img in scene.sel.xpath('//a[contains(@href,"/pornstars/")]//img'):
            add(img.xpath('@alt').get() or '', first_attr(img, '@data-src'))
        for img in scene.sel.xpath('//img[contains(@data-original,"user")]'):
            add(img.xpath('@alt').get() or '')
        return actors

    async def fetch_directors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        block = scene.sel.xpath('(//p[.//b[contains(.,"Director")]])[1]')
        if not block:
            return None
        raw = (block[0].xpath('string(.)').get() or '').split(':')[-1].split('-')[0].strip()
        if not raw or raw == 'Unknown':
            return None
        return [ActorResult(name=raw)]

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        return await self._data18.fetch_movie_images(scene.url, scene.sel)
