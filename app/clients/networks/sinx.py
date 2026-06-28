from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_attr

STUDIO = 'SinX'
_ANCHOR = './/div[contains(@class,"video_item--content")]//a'
_DATE_FMT = '%d %b %Y'


class SinXClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {url}')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//div[contains(@class,"view_grid--container")]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath(f'({_ANCHOR})[1]/@title').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = (source.xpath(f'({_ANCHOR})[1]/@href').get() or '').strip()
        return absolute_url(href, loaded.site.base_url) if href else ''

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//h1[contains(@class,"title--3")])[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//div[h5]//p)[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//tr[td[contains(.,"Date")]]/td[2])[1]').xpath('string(.)').get() or '').strip()
        if raw:
            return iso_date(raw, _DATE_FMT) or iso_date(raw)
        return (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres = self.dedup_strings(
            [(a.xpath('string(.)').get() or '').split('#')[-1].strip() for a in scene.sel.xpath('//div[contains(@class,"tags-wrap")]//a')]
        )
        cast = len(scene.sel.xpath('//figure[contains(@class,"girls-item")]'))
        if cast == 3 and 'Threesome' not in genres:
            genres.append('Threesome')
        elif cast == 4 and 'Foursome' not in genres:
            genres.append('Foursome')
        elif cast > 4 and 'Orgy' not in genres:
            genres.append('Orgy')
        return genres or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        figures = scene.sel.xpath('//figure[contains(@class,"girls-item")]')
        single = len(figures) == 1
        entries: list[ActorResult] = []
        for fig in figures:
            name = (fig.xpath('(.//h4)[1]').xpath('string(.)').get() or '').strip()
            photo = first_attr(fig, '(.//img)[1]/@src') if single else ''
            entries.append(ActorResult(name=name, photo_url=photo))
        return self.dedup_people(entries) or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        coll = self.image_collector(lambda raw: absolute_url(raw, scene.site.base_url))
        for src in scene.sel.xpath('//div[contains(@class,"video__block") and contains(@class,"video_item--player")]//img/@src').getall():
            coll['push'](src)
        images: list[str] = coll['list']
        return images or None
