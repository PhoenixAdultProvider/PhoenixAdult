from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from app.clients.aggregators.data18 import Data18Client
from app.clients.base import ActorResult, Client, LoadedScene, SceneContext, SearchContext, SearchResult
from app.clients.networks._data.reptyle_subnetworks import resolve_reptyle_subnetwork
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, date_distance_score, iso_date, pack_cur_id, title_distance_score
from app.utils.logging.logger import logger
from app.utils.searchengines import SearchOptions, web_search

_RELEASE_DATE_XP = '(//span[contains(.,"Release date")])[1]/following-sibling::a//b[1]/text()'


def _site_anchor(sel: Any) -> str:
    return (sel.xpath('(//p[.//b[contains(.,"Site")]]//a)[1]/text()').get() or '').strip()


def _resolve_studio(sel: Any) -> str:
    queries = [('Studio', 'b'), ('Network', 'b'), ('Studio', 'a'), ('Network', 'a')]
    for label, nxt in queries:
        text = (sel.xpath(f'(//b[normalize-space(.)="{label}"])[1]/following-sibling::{nxt}[1]/text()').get() or '').strip()
        if text:
            return text
    return _site_anchor(sel)


def _resolve_tagline(sel: Any, studio: str) -> str:
    site_name = _site_anchor(sel)
    sub_site = (sel.xpath('(//p[.//b[contains(.,"Network")]]//a)[1]/text()').get() or '').strip()
    if sub_site.lower() in ('brazzers', 'bangbros'):
        candidate = (sel.xpath('(//b[contains(.,"Network")])[1]/..').xpath('normalize-space(.)').get() or '').split('|')[-1].strip()
        if re.search(r'Brazzers Exxtra|Brazzers Live|BangBros Clips', candidate):
            sub_site = candidate
    serie = (sel.xpath('(//p[contains(.,"Webserie:")] | //p[contains(.,"Miniserie:")])[1]//a[1]/text()').get() or '').strip()
    movie = (sel.xpath('(//p[contains(.,"Movie:")])[1]//a[1]/text()').get() or '').strip()
    if site_name:
        return site_name
    if sub_site and re.sub(r'\s+', '', sub_site).lower() != re.sub(r'\s+', '', studio).lower():
        return sub_site
    if serie:
        return serie
    if movie:
        return movie
    return ''


class Data18ScenesClient(Client):
    def __init__(self) -> None:
        super().__init__()
        self._data18 = Data18Client()

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        scene_id = ctx.scene_id if ctx.scene_id and ctx.scene_id.isdigit() and int(ctx.scene_id) > 100 else ''
        text = ctx.title.strip()

        scene_urls: set[str] = set()
        if scene_id:
            scene_urls.add(f'{base}/scenes/{scene_id}')

        candidates = []
        try:
            candidates = await self._data18.find_candidates(text or ctx.title, 'scenes', max_pages=50)
        except Exception as err:  # noqa: BLE001 - discovery failure is non-fatal
            logger.warn(ctx.site_info.name, f'find_candidates failed: {err}')

        try:
            host = urlsplit(ctx.site_info.base_url).hostname or ''
            for u in await web_search(SearchOptions(query=text or ctx.title, site=host, num=10)):
                cleaned = u.replace('/content/', '/scenes/').replace('http:', 'https:')
                if '/scenes/' in cleaned and '.html' not in cleaned:
                    scene_urls.add(cleaned)
        except Exception as err:  # noqa: BLE001
            logger.debug(ctx.site_info.name, f'webSearch threw: {err}')

        results: list[SearchResult] = []
        seen: set[str] = set()

        for c in candidates:
            if c.url in seen:
                continue
            seen.add(c.url)
            scene_urls.discard(c.url)
            direct_hit = scene_id != '' and scene_id == c.url_id
            title = c.title_raw
            if c.truncated:
                loaded = await self._data18.fetch_page(c.url)
                if loaded is not None:
                    title = (loaded.xpath('(//h1)[1]/text()').get() or '').strip() or title
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

        for scene_url in scene_urls:
            if scene_url in seen:
                continue
            seen.add(scene_url)
            loaded = await self._data18.fetch_page(scene_url)
            if loaded is None:
                continue
            title = (loaded.xpath('(//h1)[1]/text()').get() or '').strip()
            if not title or 'Error 404' in title:
                continue
            url_id = re.sub(r'.*/', '', scene_url)
            direct_hit = scene_id != '' and scene_id == url_id
            date_raw = (loaded.xpath(_RELEASE_DATE_XP).get() or '').strip()
            release_date = iso_date(date_raw) or ''
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
                    scene_url=scene_url,
                    query=text or ctx.title,
                    display_date=release_date or None,
                    search_date=ctx.search_date,
                    score=score,
                    cur_id=pack_cur_id([p for p in (scene_url, release_date) if p]),
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
        studio = _resolve_studio(loaded)
        tagline = _resolve_tagline(loaded, studio)
        if studio and studio.lower() in ('teamskeet', 'mylf'):
            sub = resolve_reptyle_subnetwork(tagline)
            if sub:
                studio = sub['network']
                tagline = sub['subsite']
        same = not tagline or re.sub(r'\s+', '', tagline).lower() == re.sub(r'\s+', '', studio).lower()
        collections = [tagline] if tagline and not same else ([studio] if studio else [])
        return LoadedScene(
            url=url,
            site=site,
            scene_date=fallback_date or None,
            capture=ctx.capture if ctx else None,
            sel=loaded,
            extra={'studio': studio, 'tagline': '' if same else tagline, 'collections': collections},
        )

    def _extra(self, scene: LoadedScene) -> dict[str, Any]:
        return scene.extra if isinstance(scene.extra, dict) else {}

    # ── Field hooks ─────────────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        title = (scene.sel.xpath('(//h1)[1]/text()').get() or '').strip()
        m = re.match(r'^Scene[^:-]*(?::|-)', title)
        if m:
            scene_num = re.sub(r'[^A-Za-z0-9\s]+', '', m.group(0)).strip()
            title = f'{title[len(m.group(0)) :].strip()} - {scene_num}'
        return title or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        tries = [
            ('//div[contains(@class,"gen12")]//div[contains(.,"Story")]', 'Story -'),
            ('//div[contains(@class,"gen12")]//div[contains(@class,"hideContent") and contains(@class,"boxdesc") and contains(.,"Description")]', '---'),
            ('//div[contains(@class,"gen12")]//div[contains(.,"Movie Description")]', '--'),
        ]
        for xp, split_on in tries:
            nodes = scene.sel.xpath(xp)
            if not nodes:
                continue
            raw = nodes[0].xpath('string(.)').get() or ''
            summary = raw.split(split_on)[-1].strip()
            if summary:
                return summary.replace('\xa0', ' ')
        return None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return self._extra(scene).get('studio') or None

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return self._extra(scene).get('tagline') or None

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        c = self._extra(scene).get('collections') or []
        return c or None

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath(_RELEASE_DATE_XP).get() or '').strip()
        return iso_date(raw) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//div[.//b[contains(.,"Categories")]]//a')]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()

        def add(name: str) -> None:
            n = (name or '').strip().replace('\xa0', ' ')
            if n and n not in seen:
                seen.add(n)
                actors.append(ActorResult(name=n))

        base = '(//h3[contains(.,"Cast")])[1]/following-sibling::*'
        for el in scene.sel.xpath(f'{base}//div//p[contains(.,"No Profile")]//span'):
            add(el.xpath('normalize-space(.)').get() or '')
        for el in scene.sel.xpath(f'{base}//a[contains(@href,"/name/")]//img'):
            add(el.xpath('@alt').get() or '')
        no_profile = scene.sel.xpath('(//h3[contains(.,"Cast")])[1]/following-sibling::p[contains(.,"No profile")]//b[1]')
        if no_profile:
            for n in (no_profile[0].xpath('normalize-space(.)').get() or '').split(','):
                add(n)
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        return await self._data18.fetch_images(scene.url)
