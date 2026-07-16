from __future__ import annotations

import re
from typing import Any

from app.clients.aggregators.data18 import Data18Client, squash, strip_reptyle_suffix, xp_first_ns, xp_ns
from app.clients.base import ActorResult, Client, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from app.clients.networks.reptyle_subnetworks import resolve_reptyle_subnetwork
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import iso_date

_TITLE_XP = '(//h1)[1]'
_RELEASE_DATE_XP = '(//b[normalize-space(.)="Release date"])[1]/following-sibling::a[1]/b[1]'
_SITE_XP = '(//p[b[normalize-space(.)="Site"]]/a)[1]'
_NETWORK_XP = '(//p[b[normalize-space(.)="Network"]]//a)[1]'
_BARE_SUBSITE_XP = '(//b[normalize-space(.)="Network"])[1]/following-sibling::text()'

_STUDIO_XPATHS = (
    '(//b[normalize-space(.)="Studio"])[1]/following-sibling::b[1]',
    '(//b[normalize-space(.)="Network"])[1]/following-sibling::b[1]',
    '(//b[normalize-space(.)="Studio"])[1]/following-sibling::a[1]',
    '(//b[normalize-space(.)="Network"])[1]/following-sibling::a[1]',
    _SITE_XP,
)
_SUBSITE_XPATHS = ('(//p[b[normalize-space(.)="Network"]]/a[@class="bold"])[1]',)
_SERIE_XPATHS = (
    '(//span[contains(@class,"listwebserie") or contains(@class,"listminiserie")]/u)[1]',
    '(//text()[contains(.,"Webserie:") or contains(.,"Miniserie:")])[1]/following-sibling::a[1]',
)
_MOVIE_XPATHS = ('(//p[b[normalize-space(.)="Movie:"]]/a)[1]',)
_REPTYLE_NETWORKS = ('teamskeet', 'mylf')


def _resolve_studio(sel: Any) -> str:
    return xp_first_ns(sel, _STUDIO_XPATHS)


def _resolve_subsite(sel: Any) -> str:
    if bold := xp_first_ns(sel, _SUBSITE_XPATHS):
        return bold

    texts: list[str] = sel.xpath(_BARE_SUBSITE_XP).getall()
    for text in texts:
        stripped = text.strip()
        if stripped.startswith('|') and (bare := stripped.lstrip('|').strip()) and not bare.endswith(':'):
            return bare

    return ''


def _resolve_tagline(sel: Any, studio: str) -> str:
    if not xp_ns(sel, _NETWORK_XP):
        return ''

    if site_name := xp_ns(sel, _SITE_XP):
        return site_name

    sub_site = _resolve_subsite(sel)
    if sub_site and squash(sub_site) != squash(studio):
        return sub_site

    return xp_first_ns(sel, _SERIE_XPATHS) or xp_first_ns(sel, _MOVIE_XPATHS)


def _apply_reptyle(studio: str, tagline: str) -> tuple[str, str]:
    if strip_reptyle_suffix(studio).lower() not in _REPTYLE_NETWORKS:
        return studio, tagline

    sub = resolve_reptyle_subnetwork(tagline)
    return (sub['network'], sub['subsite']) if sub else (strip_reptyle_suffix(studio), tagline)


def _clean_ws_url(u: str) -> str | None:
    cleaned = u.replace('/content/', '/scenes/').replace('http:', 'https:')
    return cleaned if '/scenes/' in cleaned and '.html' not in cleaned else None


def _extract_detail(loaded: Any, url: str) -> tuple[str, str, str] | None:
    title = xp_ns(loaded, _TITLE_XP)
    if not title or 'Error 404' in title:
        return None

    release_date = iso_date(xp_ns(loaded, _RELEASE_DATE_XP)) or ''
    studio = _resolve_studio(loaded)
    subsite = _resolve_tagline(loaded, studio) or studio
    return title, release_date, subsite


class Data18ScenesClient(Client):
    def __init__(self) -> None:
        super().__init__()
        self._data18 = Data18Client()

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        await self._data18.data18_search(
            search_data,
            results,
            kind='scenes',
            ws_query=search_data.title.strip() or search_data.title,
            clean_ws_url=_clean_ws_url,
            extract_detail=_extract_detail,
            max_pages=50,
        )

    # ── Context loader ────────────────────────────────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        url, _, tail = payload.partition('|')
        fallback_date = tail.strip()
        loaded = await self._data18.fetch_page(url)
        if loaded is None:
            return None

        studio = _resolve_studio(loaded)
        tagline = _resolve_tagline(loaded, studio)
        if studio:
            studio, tagline = _apply_reptyle(studio, tagline)

        same = not tagline or squash(tagline) == squash(studio)
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

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        title = xp_ns(details_page_elements, _TITLE_XP)
        m = re.match(r'^Scene[^:-]*(?::|-)', title)
        if m:
            scene_num = re.sub(r'[^A-Za-z0-9\s]+', '', m.group(0)).strip()
            title = f'{title[len(m.group(0)) :].strip()} - {scene_num}'

        metadata.title = title or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        tries = [
            ('//div[contains(@class,"gen12")]//div[contains(.,"Story")]', 'Story -'),
            ('//div[contains(@class,"gen12")]//div[contains(@class,"hideContent") and contains(@class,"boxdesc") and contains(.,"Description")]', '---'),
            ('//div[contains(@class,"gen12")]//div[contains(.,"Movie Description")]', '--'),
        ]
        for xp, split_on in tries:
            nodes = details_page_elements.xpath(xp)
            if not nodes:
                continue

            raw = nodes[0].xpath('string(.)').get() or ''
            summary = raw.split(split_on)[-1].strip()
            if summary:
                metadata.summary = summary.replace('\xa0', ' ')
                return

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = self._extra(scene).get('studio') or ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._extra(scene).get('tagline') or None

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        c = self._extra(scene).get('collections') or []

        metadata.collections = c or None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.release_date = iso_date(xp_ns(details_page_elements, _RELEASE_DATE_XP)) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            genre_link.xpath('normalize-space(.)').get() for genre_link in details_page_elements.xpath('//div[./b[contains(.,"Categories")]]//a')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        actors: list[ActorResult] = []
        seen: set[str] = set()

        def add(name: str) -> None:
            n = (name or '').strip().replace('\xa0', ' ')
            if n and n not in seen:
                seen.add(n)
                actors.append(ActorResult(name=n))

        base = '(//h3[contains(.,"Cast")])[1]/following-sibling::*'
        for actor_link in details_page_elements.xpath(f'{base}//div//p[contains(.,"No Profile")]//span'):
            add(actor_link.xpath('normalize-space(.)').get() or '')

        for actor_link in details_page_elements.xpath(f'{base}//a[contains(@href,"/name/")]//img'):
            add(actor_link.xpath('@alt').get() or '')

        no_profile = details_page_elements.xpath('(//h3[contains(.,"Cast")])[1]/following-sibling::p[contains(.,"No profile")]//b[1]')
        if no_profile:
            for n in (no_profile[0].xpath('normalize-space(.)').get() or '').split(','):
                add(n)

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.data18_url = scene.url

        metadata.art = await self._data18.fetch_images(scene.url) or []
