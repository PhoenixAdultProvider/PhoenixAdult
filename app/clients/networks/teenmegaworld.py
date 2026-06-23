from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.processors.title_case import title_case

STUDIO = 'Teen Mega World'
_SEARCH_PAGES = 2


class TeenMegaWorldClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        sources: list[Any] = []
        for p in range(1, _SEARCH_PAGES + 1):
            url = f'{base}{ctx.site_info.search_path.replace("{query}", ctx.encoded)}&page={p}'
            loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {url}')
            if loaded:
                sources.extend(loaded['sel'].xpath('//div[contains(@class,"thumb") and contains(@class,"thumb-video")]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath('(.//a[contains(@class,"thumb__title-link")])[1]').xpath('string(.)').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = (source.xpath('(.//a[contains(@class,"thumb__title-link")])[1]/@href').get() or '').strip()
        return absolute_url(href, loaded.site.base_url) if href else ''

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = (source.xpath('(.//time)[1]').xpath('string(.)').get() or '').strip()
        return (iso_date(raw) if raw else None) or loaded.ctx.search_date

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//h1[@id="video-title"])[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//p[contains(@class,"video-description-text")])[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    def _tagline(self, scene: LoadedScene) -> str:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//a[contains(@class,"video-site-link")])[1]').xpath('string(.)').get() or '').strip()
        return title_case(raw, site_name=scene.site.name) if raw else scene.site.name

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return self._tagline(scene)

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [self._tagline(scene)]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//span[@title="Video release date"])[1]').xpath('string(.)').get() or '').strip()
        if raw:
            return iso_date(raw)
        return (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//a[contains(@class,"video-tag-link")]')]
        return self.dedup_strings(values) or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath('//a[contains(@class,"video-actor-link") and contains(@class,"actor__link")]'):
            name = (el.xpath('normalize-space(.)').get() or '').strip()
            href = (el.xpath('@href').get() or '').strip()
            if not name or name in seen:
                continue
            seen.add(name)
            photo = ''
            if href:
                page = await self.fetch_and_load(href if href.startswith('http') else absolute_url(href, base), None, f'[{scene.site.name}] actor {name}')
                raw = (page['sel'].xpath('(//div[contains(@class,"model-profile-image-wrap")]//img)[1]/@src').get() or '').strip() if page else ''
                if raw:
                    photo = raw if raw.startswith('http') else absolute_url(raw, base)
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        coll = self.image_collector(lambda raw: raw if raw.startswith('http') else absolute_url(raw, scene.site.base_url))
        for raw in scene.sel.xpath('//img[@id="video-cover-image"]/@src').getall():
            coll['push'](raw)
        images: list[str] = coll['list']
        return images or None
