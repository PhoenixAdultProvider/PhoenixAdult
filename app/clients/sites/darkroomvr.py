from __future__ import annotations

import re
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_attr, first_text

_READ_LESS_RE = re.compile(r'\s*Read less\s*$', re.IGNORECASE)


class DarkRoomVRClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//a[contains(@class,"video-card__item")]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/div[contains(@class,"video-card__title")]')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '@href')
        if not href:
            return ''
        return absolute_url(href, loaded.site.base_url)

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//h1') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//div[@data-id="description" and contains(@class,"hidden")]')
        if not raw:
            return None
        return _READ_LESS_RE.sub('', raw).strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'DarkRoomVR'

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//div[contains(@class,"video-info__time")]')
        if not raw:
            return None
        after = raw.split(' • ')[-1].strip()
        return iso_date(after) or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//a[contains(@class,"tags__item")]')]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath('//div[contains(@class,"video-info__text")]//a'):
            name = first_attr(el, 'normalize-space(.)')
            href = first_attr(el, '@href')
            if not name or not href or name in seen:
                continue
            seen.add(name)
            actor_url = absolute_url(href, scene.site.base_url)
            actor_page = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
            photo = ''
            if actor_page:
                raw = first_attr(actor_page['sel'], '(//img[contains(@class,"pornstar-detail__picture")]/@src)[1]')
                photo = (absolute_url(raw, scene.site.base_url)) if raw else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []
        for href in scene.sel.xpath('//div[contains(@class,"video-detail__gallery-item")]//a/@href').getall():
            href = (href or '').strip()
            if not href:
                continue
            abs_url = absolute_url(href, scene.site.base_url)
            if abs_url not in images:
                images.append(abs_url)
        return images
