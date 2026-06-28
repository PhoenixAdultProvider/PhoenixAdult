from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_attr, first_text

_CARD_XP = '//li[contains(concat(" ", normalize-space(@class), " "), " thumb ")]'
_MODELS_XP = '//ul[contains(.,"Models:")]//li//a'


class FirstAnalQuestClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath(_CARD_XP))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/span[contains(@class,"thumb-title")]')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//a[contains(@class,"thumb-img")]/@href)[1]')
        if not href:
            return ''
        return absolute_url(href, loaded.site.base_url)

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = first_text(source, './/span[contains(@class,"thumb-added")]')
        return iso_date(raw) if raw else None

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        xp = '//div[contains(@class,"container") and contains(@class,"content")]//div[contains(@class,"page-header")]//span[contains(@class,"title")]'
        return first_text(scene.sel, xp) or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"text-desc")]') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'Pioneer'

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        return scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres = self.dedup_strings(
            [first_attr(a, 'normalize-space(.)') for a in scene.sel.xpath('//div[contains(@class,"media-body")]//ul[contains(.,"Categories")]//a')]
        )
        if 'porn-movie' not in scene.url:
            count = len(scene.sel.xpath(_MODELS_XP))
            if count == 3 and 'Threesome' not in genres:
                genres.append('Threesome')
            elif count == 4 and 'Foursome' not in genres:
                genres.append('Foursome')
            elif count > 4 and 'Orgy' not in genres:
                genres.append('Orgy')
        return genres

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath(_MODELS_XP):
            name = first_attr(el, 'normalize-space(.)')
            href = first_attr(el, '@href')
            if not name or not href or name in seen:
                continue
            seen.add(name)
            actor_url = absolute_url(href, scene.site.base_url)
            actor_page = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
            photo = ''
            if actor_page:
                raw = first_attr(actor_page['sel'], '(//div[contains(@class,"model-box")]//img/@src)[1]')
                photo = (absolute_url(raw, scene.site.base_url)) if raw else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []

        def push(raw: str) -> None:
            raw = (raw or '').strip()
            if not raw:
                return
            abs_url = absolute_url(raw, scene.site.base_url)
            if abs_url not in images:
                images.append(abs_url)

        for raw in scene.sel.xpath('//img[contains(@class,"player-preview")]/@src').getall():
            push(raw)
        for raw in scene.sel.xpath('//a[contains(@class,"fancybox") and contains(@class,"img-album")]/@href').getall():
            push(raw)
        for raw in scene.sel.xpath('//a[@data-fancybox-group="gallery"]/@href').getall():
            push(raw)
        return images
