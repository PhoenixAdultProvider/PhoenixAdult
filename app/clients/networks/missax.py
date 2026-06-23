from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date

_SEARCH_DATE_XP = (
    './/span[@class="update_thumb_date"] | .//span[@class="date"] | .//div[contains(@class,"updateDetails")]/p/span[2] | .//div[contains(@class,"update_date")]'
)
_CAST_XP = '//div[contains(@class,"update_block")]/span[@class="tour_update_models"]//a | //p[@class="dvd-scenes__data"][1]//a'


class MissaXClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {url}')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//div[@class="updateItem"] | //div[@class="photo-thumb video-thumb"] | //div[@class="update_details"]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath('(.//h4//a | .//p[@class="thumb-title"] | ./a[./preceding-sibling::a])[1]').xpath('string(.)').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = (source.xpath('(.//a)[1]/@href').get() or '').strip()
        return absolute_url(href, loaded.site.base_url) if href else ''

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        return iso_date((source.xpath(f'({_SEARCH_DATE_XP})[1]').xpath('string(.)').get() or '').strip())

    # ── Detail field hooks ────────────────────────────────────────────────────

    def _cast_names(self, sel: Any) -> list[str]:
        return [n for n in ((a.xpath('normalize-space(.)').get() or '').strip() for a in sel.xpath(_CAST_XP)) if n]

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        title = (scene.sel.xpath('(//span[@class="update_title"] | //p[@class="raiting-section__title"])[1]').xpath('string(.)').get() or '').strip()
        if scene.site.name == 'House of Fyre':
            for name in self._cast_names(scene.sel):
                suffix = f': {name}'
                if title.endswith(suffix):
                    title = title[: -len(suffix)]
                    break
        return title or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        parts: list[str] = []
        for el in scene.sel.xpath('//span[@class="latest_update_description"] | //div[@class="container"]//p[@class="dvd-scenes__title"]/following-sibling::p'):
            t = (el.xpath('string(.)').get() or '').replace('\xa0', '').strip()
            if t:
                parts.append(t)
        if not parts:
            return None
        joined = '\n'.join(parts).replace('Includes:', '').replace('Synopsis:', '').split('You Might Also Like')[0].strip()
        return joined or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        update = (
            (scene.sel.xpath('(//span[@class="update_date"] | //span[contains(@class,"availdate")])[1]').xpath('string(.)').get() or '')
            .replace('Available to Members Now', '')
            .strip()
        )
        if update:
            return iso_date(update) or scene.scene_date or None
        dvd_text = scene.sel.xpath('(//p[@class="dvd-scenes__data"])[1]').xpath('string(.)').get() or ''
        parts = dvd_text.split('|')
        dvd = parts[1].replace('Added:', '').strip() if len(parts) > 1 else ''
        return (iso_date(dvd) if dvd else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [
            a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//span[contains(@class,"update_tags")]//a | //p[@class="dvd-scenes__data"][2]//a')
        ]
        return self.dedup_strings(values) or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath(_CAST_XP):
            name = (el.xpath('normalize-space(.)').get() or '').strip()
            if not name or name in seen:
                continue
            seen.add(name)
            photo = ''
            href = (el.xpath('@href').get() or '').strip()
            if href:
                page = await self.fetch_and_load(absolute_url(href, base), None, f'GET {href} (actor)')
                raw = (page['sel'].xpath('(//img[contains(@class,"model_bio_thumb")])[1]/@src0_1x').get() or '').strip() if page else ''
                if raw:
                    photo = raw if raw.startswith('http') else absolute_url(raw, base)
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        images: list[str] = []

        def push(raw: str) -> None:
            if not raw:
                return
            abs_url = raw if raw.startswith('http') else absolute_url(raw, base)
            if abs_url and abs_url not in images:
                images.append(abs_url)

        xpaths = (
            '//img[contains(@class,"update_thumb")]/@src0_4x',
            '//img[contains(@class,"update_thumb")]/@src0_1x',
        )
        for xpath in xpaths:
            for raw in scene.sel.xpath(xpath).getall():
                push(raw)
        return images or None
