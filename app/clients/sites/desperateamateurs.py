from __future__ import annotations

import re
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_text

_TITLE_LINK_XP = '(.//a[contains(@class,"update_title")])[2]'
_ADDED_PREFIX = re.compile(r'^Added:\s*', re.IGNORECASE)


class DesperateAmateursClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//div[@align="left"]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, _TITLE_LINK_XP)

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = (source.xpath(f'({_TITLE_LINK_XP}/@href)[1]').get() or '').strip()
        if not href:
            return ''
        return href if href.startswith('http') else absolute_url(href, loaded.site.base_url)

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = first_text(source, './/span[contains(@class,"date")]')
        stripped = _ADDED_PREFIX.sub('', raw).strip()
        return iso_date(stripped) if stripped else None

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"title_bar")]') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"gallery_description")]') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'Desperate Amateurs'

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//td[contains(@class,"date")]')
        if not raw:
            return None
        after = raw.split('Added:')[-1].strip()
        return iso_date(after) if after else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//a[starts-with(@href,"category")]')]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath('//a[starts-with(@href,"sets")]'):
            name = (el.xpath('normalize-space(.)').get() or '').strip()
            href = (el.xpath('@href').get() or '').strip()
            if not name or not href or name in seen:
                continue
            seen.add(name)
            actor_url = href if href.startswith('http') else absolute_url(href, scene.site.base_url)
            actor_page = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
            photo = ''
            if actor_page:
                raw = (actor_page['sel'].xpath('(//img[contains(@class,"thumbs")]/@src)[1]').get() or '').strip()
                photo = (raw if raw.startswith('http') else absolute_url(raw, scene.site.base_url)) if raw else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []
        for el in scene.sel.xpath('//div[contains(@class,"gal")]//img'):
            raw = (el.xpath('@src').get() or '').strip()
            if not raw:
                continue
            abs_url = raw if raw.startswith('http') else absolute_url(raw, scene.site.base_url)
            if abs_url not in images:
                images.append(abs_url)
        return images
