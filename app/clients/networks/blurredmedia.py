from __future__ import annotations

import re
from typing import Any

from app.clients.base import (
    ActorResult,
    Client,
    FetchCtx,
    LoadedScene,
    LoadedSearch,
    SceneContext,
    SearchContext,
)
from app.registry import ResolvedSiteInfo
from app.utils.cookies.site_cookies import get_site_cookies
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_attr

_SESSION_COOKIES: dict[str, str] = {'Hot Guys Fuck': 'SPSI'}


__testing__ = {'SESSION_COOKIES': _SESSION_COOKIES}


class BlurredMediaClient(Client):
    async def _session_cookie(self, site: ResolvedSiteInfo) -> str | None:
        name = _SESSION_COOKIES.get(site.name)
        if not name:
            return None
        jar = await get_site_cookies(site.base_url)
        return f'{name}={jar[name]}' if jar.get(name) else None

    # ── Search (orchestrator) ───────────────────────────────────────────────────

    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        slug = re.sub(r'\s+', '+', ctx.title.strip())
        url = base + ctx.site_info.search_path.replace('{query}', slug)
        cookie = await self._session_cookie(ctx.site_info)
        headers = {'Cookie': cookie} if cookie else None
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture, headers=headers), f'[{ctx.site_info.name}] search {url}')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//article[contains(@class,"video grid-element")]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture, sel=loaded['sel'])

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath('(.//h3[contains(@class,"video__title")])[1]').xpath('string(.)').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//a)[1]/@href')
        return absolute_url(href, loaded.site.base_url) if href else ''

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        tok = (source.xpath('(.//p[contains(@class,"video__stats")])[1]').xpath('string(.)').get() or '').split('|')[0].strip()
        return iso_date(tok) if tok else None

    # ── Detail (cookie-aware context + field hooks) ─────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        cookie = await self._session_cookie(site)
        if not cookie:
            return await super().load_scene_context(payload, site, ctx)
        pipe = payload.find('|')
        url = payload[:pipe] if pipe >= 0 else payload
        fallback = payload[pipe + 1 :].strip() if pipe >= 0 else None
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture if ctx else None, headers={'Cookie': cookie}), f'[{site.name}] detail {url}')
        if not loaded:
            return None
        return LoadedScene(
            url=url,
            site=site,
            scene_date=fallback or None,
            capture=ctx.capture if ctx else None,
            sel=loaded['sel'],
            html=loaded['html'],
            raw_image_cookie=cookie,
        )

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//h1[contains(@class,"title")])[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//section[@name="descriptionIntro"]/p)[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_attr(scene.sel, '(//time[contains(@class,"video__date")])[1]/@datetime')
        return iso_date(raw) if raw else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('string(.)').get() or '' for a in scene.sel.xpath('//a[contains(@class,"video__tag")]')]
        return self.dedup_strings(values) or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        entries: list[ActorResult] = []
        for fig in scene.sel.xpath('//section[@name="modelsBio"]/article/figure'):
            name = (fig.xpath('(.//p//a)[1]').xpath('string(.)').get() or '').strip()
            raw = first_attr(fig, '(.//img)[1]/@src')
            entries.append(ActorResult(name=name, photo_url=absolute_url(raw, base) if raw else ''))
        return self.dedup_people(entries) or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        coll = self.image_collector(lambda raw: absolute_url(raw, base))
        xpaths = (
            '//div[contains(@class,"loading-video")]//img/@src',
            '//ul[contains(@class,"thumbnails__gallery")]//li//a/@href',
        )
        for xpath in xpaths:
            for raw in scene.sel.xpath(xpath).getall():
                coll['push'](raw)
        images: list[str] = coll['list']
        return images or None
