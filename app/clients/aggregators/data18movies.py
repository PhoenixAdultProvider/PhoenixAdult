from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from app.clients.aggregators.data18 import Data18Client, squash, strip_reptyle_suffix, swap_article, url_id, xp_first_ns, xp_ns
from app.clients.base import ActorResult, Client, LoadedScene, SceneContext, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id, sceneid_distance_score
from app.utils.helpers.html_helpers import first_attr
from app.utils.logging.best_effort import best_effort
from app.utils.searchengines import SearchOptions, web_search

_TITLE_XP = '(//h1)[1]'
_DATE_ATTR_XP = '(//*[@datetime])[1]/@datetime'
_DATE_TEXT_XP = '(//text()[contains(.,"Release date:")])[1]'
_SERIES_XP = '(//p[contains(.,"Movie Series")]//a[@title])[1]'

_STUDIO_XPATHS = (
    '(//b[normalize-space(.)="Network"])[1]/following-sibling::b[1]',
    '(//b[normalize-space(.)="Studio"])[1]/following-sibling::b[1]',
    '(//b[normalize-space(.)="Network"])[1]/following-sibling::a[1]',
    '(//b[normalize-space(.)="Studio"])[1]/following-sibling::a[1]',
    '(//p[contains(.,"Site:")]//a[contains(@class,"bold")])[1]',
)
_SUBSITE_XP = '(//p[b[normalize-space(.)="Network"] or b[normalize-space(.)="Studio"]]/a)[1]'
_ACTOR_XPATHS = (
    '(//h3[contains(.,"Cast")])[1]/following::a[contains(@href,"/name/")]//img',
    '(//b[contains(.,"Cast")])[1]/following::div//a[contains(@href,"/pornstars/")]//img',
    '(//b[contains(.,"Cast")])[1]/following::div//img[contains(@data-original,"user")]',
)


def _resolve_studio(sel: Any) -> str:
    return strip_reptyle_suffix(xp_first_ns(sel, _STUDIO_XPATHS))


def _resolve_series(sel: Any, studio: str) -> str:
    if series := xp_ns(sel, _SERIES_XP):
        return series
    sub_site = strip_reptyle_suffix(xp_ns(sel, _SUBSITE_XP))
    return sub_site if sub_site and squash(sub_site) != squash(studio) else ''


def _release_date(sel: Any) -> str | None:
    if attr := xp_ns(sel, _DATE_ATTR_XP):
        if iso := iso_date(attr):
            return iso
    raw = xp_ns(sel, _DATE_TEXT_XP)
    text = re.sub(r'.*Release date:\s*', '', raw).strip()
    if not text or text.lower() == 'unknown':
        return None
    return iso_date(text, '%B, %Y') or iso_date(text)


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
        with best_effort(ctx.site_info.name, 'find_candidates'):
            candidates = await self._data18.find_candidates(text or ctx.title, 'movies')

        with best_effort(ctx.site_info.name, 'webSearch', level='debug'):
            host = urlsplit(ctx.site_info.base_url).hostname or ''
            for u in await web_search(SearchOptions(query=ctx.title, site=host, num=10)):
                cleaned = u.split('-')[0].replace('http:', 'https:')
                if '/movies/' in cleaned and '.html' not in cleaned:
                    movie_urls.add(cleaned)

        results: list[SearchResult] = []
        seen: set[str] = set()

        for c in candidates:
            if c.url in seen:
                continue
            seen.add(c.url)
            movie_urls.discard(c.url)
            title = c.title_raw
            if c.truncated:
                loaded = await self._data18.fetch_page(c.url)
                if loaded is not None:
                    title = swap_article(xp_ns(loaded, _TITLE_XP) or title)
            score = sceneid_distance_score(scene_id, c.url_id) if scene_id else None
            results.append(
                build_search_result(
                    title=title,
                    scene_url=c.url,
                    query=text or ctx.title,
                    display_date=c.release_date,
                    search_date=ctx.search_date,
                    score=score,
                    cur_id=pack_cur_id([p for p in (c.url, c.release_date) if p]),
                    subsite=c.provider or None,
                )
            )

        for movie_url in movie_urls:
            if movie_url in seen:
                continue
            seen.add(movie_url)
            loaded = await self._data18.fetch_page(movie_url)
            if loaded is None:
                continue
            title = swap_article(xp_ns(loaded, _TITLE_XP))
            if not title:
                continue
            release_date = _release_date(loaded) or ''
            studio = _resolve_studio(loaded)
            subsite = _resolve_series(loaded, studio) or studio
            score = sceneid_distance_score(scene_id, url_id(movie_url)) if scene_id else None
            results.append(
                build_search_result(
                    title=title,
                    scene_url=movie_url,
                    query=text or ctx.title,
                    display_date=release_date or None,
                    search_date=ctx.search_date,
                    score=score,
                    cur_id=pack_cur_id([p for p in (movie_url, release_date) if p]),
                    subsite=subsite or None,
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
        raw = xp_ns(scene.sel, _TITLE_XP)
        return swap_article(raw) if raw else None

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
        return _resolve_series(scene.sel, _resolve_studio(scene.sel)) or None

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        studio = _resolve_studio(scene.sel)
        series = _resolve_series(scene.sel, studio)
        out: list[str] = []
        if studio:
            out.append(studio)
        if series and series not in out:
            out.append(series)
        return out or None

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return _release_date(scene.sel) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//p[./b[contains(.,"Categories")]]//a')]
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

        for xpath in _ACTOR_XPATHS:
            imgs = scene.sel.xpath(xpath)
            if not imgs:
                continue
            for img in imgs:
                add(img.xpath('@alt').get() or '', first_attr(img, '@data-src'))
            break
        return actors

    async def fetch_directors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        block = scene.sel.xpath('(//p[./b[contains(.,"Director")]])[1]')
        if not block:
            return None
        raw = (block[0].xpath('string(.)').get() or '').split(':')[-1].split('-')[0].strip()
        if not raw or raw == 'Unknown':
            return None
        return [ActorResult(name=raw)]

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        return await self._data18.fetch_movie_images(scene.url, scene.sel)
