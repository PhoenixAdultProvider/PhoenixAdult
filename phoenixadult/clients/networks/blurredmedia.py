from __future__ import annotations

import re
from typing import Any

from phoenixadult.clients.base import (
    ActorResult,
    Client,
    FetchCtx,
    LoadedScene,
    LoadedSearch,
    SceneContext,
    SceneDetail,
    SearchContext,
)
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.cookies.site_cookies import get_site_cookies
from phoenixadult.utils.helpers.helpers import absolute_url, iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr

_SESSION_COOKIES: dict[str, str] = {'Hot Guys Fuck': 'SPSI'}


__testing__ = {'SESSION_COOKIES': _SESSION_COOKIES}


class BlurredMediaClient(Client):
    # ── Search Field Hooks ──────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        slug = re.sub(r'\s+', '+', search_data.title.strip())
        url = search_data.search_url(slug)
        cookie = await self._session_cookie(search_data.site_info)
        headers = {'Cookie': cookie} if cookie else None
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture, headers=headers), f'[{search_data.site_info.name}] search {url}')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath('//article[contains(@class,"video grid-element")]'))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture, sel=search_results['sel'])

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath('(.//h3[contains(@class,"video__title")])[1]').xpath('string(.)').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//a)[1]/@href')
        return absolute_url(href, loaded.site.base_url) if href else ''

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        tok = (source.xpath('(.//p[contains(@class,"video__stats")])[1]').xpath('string(.)').get() or '').split('|')[0].strip()
        return iso_date(tok) if tok else None

    # ── Context Loader (cookie-aware context + field hooks) ─────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        cookie = await self._session_cookie(site)
        if not cookie:
            return await super().load_scene_context(payload, site, ctx)

        pipe = payload.find('|')
        url = payload[:pipe] if pipe >= 0 else payload
        fallback = payload[pipe + 1 :].strip() if pipe >= 0 else None
        details_page_elements = await self.fetch_and_load(
            url, FetchCtx(capture=ctx.capture if ctx else None, headers={'Cookie': cookie}, use_bypass=site.use_bypass), f'[{site.name}] detail {url}'
        )
        if not details_page_elements:
            return None

        return LoadedScene(
            url=url,
            site=site,
            scene_date=fallback or None,
            capture=ctx.capture if ctx else None,
            sel=details_page_elements['sel'],
            html=details_page_elements['html'],
            art_cookie=cookie,
        )

    # ── Update Field Hook Helpers ───────────────────────────────────────────────

    async def _session_cookie(self, site: ResolvedSiteInfo) -> str | None:
        name = _SESSION_COOKIES.get(site.name)
        if not name:
            return None

        jar = await get_site_cookies(site.base_url)
        return f'{name}={jar[name]}' if jar.get(name) else None

    # ── Update Field Hooks ──────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = (details_page_elements.xpath('(//h1[contains(@class,"title")])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = (details_page_elements.xpath('(//section[@name="descriptionIntro"]/p)[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_attr(details_page_elements, '(//time[contains(@class,"video__date")])[1]/@datetime')

        metadata.release_date = iso_date(date) if date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            genre_link.xpath('string(.)').get() or '' for genre_link in details_page_elements.xpath('//a[contains(@class,"video__tag")]')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        entries: list[ActorResult] = []
        for fig in details_page_elements.xpath('//section[@name="modelsBio"]/article/figure'):
            actor_name = (fig.xpath('(.//p//a)[1]').xpath('string(.)').get() or '').strip()
            raw = first_attr(fig, '(.//img)[1]/@src')
            entries.append(ActorResult(name=actor_name, photo_url=absolute_url(raw, base) if raw else ''))

        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        images = self.image_collector(lambda image: absolute_url(image, base))
        xpaths = (
            '//div[contains(@class,"loading-video")]//img/@src',
            '//ul[contains(@class,"thumbnails__gallery")]//li//a/@href',
        )
        for xpath in xpaths:
            for image_url in details_page_elements.xpath(xpath).getall():
                images.push(image_url)

        metadata.art = images.items
