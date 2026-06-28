from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_attr, first_text


class BAMVisionsClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//div[contains(@class,"category_listing_wrapper_updates")]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/h3//a')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//h3//a/@href)[1]')
        if not href:
            return ''
        return absolute_url(href, loaded.site.base_url)

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"item-info")]//h4//a') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//p[contains(@class,"description")]') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'BAMVisions'

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return 'BAMVisions'

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return ['BAMVisions']

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        return ['Anal', 'Hardcore']

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        li = first_text(scene.sel, '//ul[contains(@class,"item-meta")]//li')
        if not li:
            return None
        after = li.split('Release Date:')[-1].strip()
        return iso_date(after, '%B %d, %Y') or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath('//div[contains(@class,"item-info")]//h5//a'):
            name = first_attr(el, 'normalize-space(.)')
            href = first_attr(el, '@href')
            if not name or not href or name in seen:
                continue
            seen.add(name)
            actor_url = absolute_url(href, scene.site.base_url)
            actor_page = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
            photo = ''
            if actor_page:
                raw = first_attr(actor_page['sel'], '(//div[contains(@class,"profile-pic")]//img/@src0_3x)[1]')
                photo = (absolute_url(raw, scene.site.base_url)) if raw else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []
        for el in scene.sel.xpath('//img[contains(@class,"update_thumb")]'):
            raw = first_attr(el, '@src0_3x')
            if not raw:
                continue
            abs_url = absolute_url(raw, scene.site.base_url)
            if abs_url not in images:
                images.append(abs_url)
        return images
