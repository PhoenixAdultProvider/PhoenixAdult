from __future__ import annotations

import re
from typing import Any

from app.clients.aggregators.data18 import Data18Client, squash, strip_reptyle_suffix, xp_first_ns, xp_ns
from app.clients.base import ActorResult, Client, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import iso_date
from app.utils.helpers.html_helpers import first_attr

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


def _clean_ws_url(u: str) -> str | None:
    cleaned = u.split('-')[0].replace('http:', 'https:')
    return cleaned if '/movies/' in cleaned and '.html' not in cleaned else None


def _extract_detail(loaded: Any, url: str) -> tuple[str, str, str] | None:
    title = xp_ns(loaded, _TITLE_XP)
    if not title:
        return None
    release_date = _release_date(loaded) or ''
    studio = _resolve_studio(loaded)
    subsite = _resolve_series(loaded, studio) or studio
    return title, release_date, subsite


class Data18MoviesClient(Client):
    def __init__(self) -> None:
        super().__init__()
        self._data18 = Data18Client()

    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        await self._data18.data18_search(
            ctx,
            results,
            kind='movies',
            ws_query=ctx.title,
            clean_ws_url=_clean_ws_url,
            extract_detail=_extract_detail,
        )

    # ── Context loader ────────────────────────────────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        url, _, tail = payload.partition('|')
        fallback_date = tail.strip()
        loaded = await self._data18.fetch_page(url)
        if loaded is None:
            return None
        return LoadedScene(url=url, site=site, scene_date=fallback_date or None, capture=ctx.capture if ctx else None, sel=loaded)

    # ── Field hooks ─────────────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = xp_ns(scene.sel, _TITLE_XP)
        metadata.title = raw or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        for div in scene.sel.xpath('//div[contains(@class,"gen12")]//div'):
            t = div.xpath('string(.)').get() or ''
            if 'Description' in t and re.search(r'Studio|Network', t):
                summary = t.split('---')[-1].split('Description -')[-1].strip()
                metadata.summary = summary.replace('\xa0', ' ') if len(summary) > 1 else ''
                return

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.studio = _resolve_studio(scene.sel) or ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.tagline = _resolve_series(scene.sel, _resolve_studio(scene.sel)) or None

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        studio = _resolve_studio(scene.sel)
        series = _resolve_series(scene.sel, studio)
        out: list[str] = []
        if studio:
            out.append(studio)
        if series and series not in out:
            out.append(series)
        metadata.collections = out or None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.release_date = _release_date(scene.sel) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//p[./b[contains(.,"Categories")]]//a')]
        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
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
        metadata.actors = actors

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        block = scene.sel.xpath('(//p[./b[contains(.,"Director")]])[1]')
        if not block:
            return
        raw = (block[0].xpath('string(.)').get() or '').split(':')[-1].split('-')[0].strip()
        if not raw or raw == 'Unknown':
            return
        metadata.directors = [ActorResult(name=raw)]

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.raw_image_urls = await self._data18.fetch_movie_images(scene.url, scene.sel) or []
