from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date, load_site_json
from app.utils.helpers.html_helpers import first_text

_GROUP_GENRES: dict[str, str] = load_site_json(__file__, 'fuckingawesome_group_genres')

STUDIO = 'FuckingAwesome'
_ACTOR_XP = '//div[contains(@class,"pornstarnames")]//ul//li//a[contains(@href,"pornstars")]'


class FuckingAwesomeClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//div[contains(@class,"gallery")]/div'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/div[contains(@class,"video-title") and contains(@class,"truncate")]/a')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = (source.xpath('(.//div[contains(@class,"video-title") and contains(@class,"truncate")]/a/@href)[1]').get() or '').strip()
        if not href:
            return ''
        return href if href.startswith('http') else absolute_url(href, loaded.site.base_url)

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = first_text(source, './/span[contains(@class,"small") and contains(@class,"date")]')
        return iso_date(raw) if raw else None

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//h1') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"more") and contains(@class,"text-justify")]') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//div[contains(@class,"videodate")]//strong')
        return iso_date(raw, '%B %d, %Y') or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath(_ACTOR_XP):
            name = (el.xpath('normalize-space(.)').get() or '').strip()
            href = (el.xpath('@href').get() or '').strip()
            if not name or not href or name in seen:
                continue
            seen.add(name)
            actor_url = href if href.startswith('http') else absolute_url(href, scene.site.base_url)
            actor_page = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
            photo = ''
            if actor_page:
                src = (actor_page['sel'].xpath('(//div[contains(@class,"pornstar-pic")]//img/@src)[1]').get() or '').strip()
                photo = absolute_url(src, scene.site.base_url) if src else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres: list[str] = []
        for a in scene.sel.xpath('//div[contains(@class,"tags")]//ul//li//a'):
            g = (a.xpath('normalize-space(.)').get() or '').strip().lower()
            if g and g not in genres:
                genres.append(g)
        count = len(scene.sel.xpath(_ACTOR_XP))
        count_genre = _GROUP_GENRES.get(str(count))
        if count_genre and count_genre not in genres:
            genres.append(count_genre)
        if count > 4 and 'Orgy' not in genres:
            genres.append('Orgy')
        return genres

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        images: list[str] = []

        def add(raw: str) -> None:
            raw = (raw or '').strip()
            if not raw:
                return
            abs_url = raw if raw.startswith('http') else absolute_url(raw, base)
            if abs_url not in images:
                images.append(abs_url)

        for raw in scene.sel.xpath('//span[contains(@class,"et_pb_image_wrap")]//img/@content').getall():
            add(raw)

        photos_href = (scene.sel.xpath('(//li[contains(@class,"photos")]//a/@href)[1]').get() or '').strip()
        if photos_href:
            photos_url = photos_href if photos_href.startswith('http') else absolute_url(photos_href, scene.site.base_url)
            photos_page = await self.fetch_and_load(photos_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] photos page')
            if photos_page:
                for raw in photos_page['sel'].xpath('//div[contains(@class,"my-gallery")]//a/@href').getall():
                    add(raw)
        return images
