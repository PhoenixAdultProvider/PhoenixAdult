from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_attr

STUDIO = 'Cherry Pimps'
_SEARCH_PAGES = 2

_SEARCH_TITLE_XP = './/p[contains(@class,"text-thumb")]//a | .//div[contains(@class,"item-title")]//a'
_SEARCH_DATE_XP = './/span[contains(@class,"date")] | .//div[contains(@class,"item-date")]'
_DETAIL_TITLE_XP = '//*[contains(@class,"trailer-block_title")] | //h1'
_DETAIL_SUMMARY_XP = '//div[contains(@class,"info-block")]//p[contains(@class,"text")] | //div[contains(@class,"update-info-block")]//p'
_DETAIL_DATE_XP = '//div[contains(@class,"info-block_data")]//p[contains(@class,"text")] | //div[contains(@class,"update-info-row")]'
_DETAIL_GENRES_XP = '//div[contains(@class,"info-block")]//a | //ul[contains(@class,"tags")]//a'
_DETAIL_ACTORS_XP = '//div[contains(@class,"info-block_data")]//a | //div[contains(@class,"model-list-item")]//a'


class CherryPimpsClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        slug = '+'.join(ctx.title.split())
        sources: list[Any] = []
        for p in range(1, _SEARCH_PAGES + 1):
            url = base + ctx.site_info.search_path.replace('{query}', slug) + f'&page={p}'
            loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {url}')
            if not loaded:
                continue
            sources.extend(loaded['sel'].xpath('//div[contains(@class,"item-updates")]//div[contains(@class,"item-update")]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath(f'({_SEARCH_TITLE_XP})[1]').xpath('string(.)').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = (source.xpath(f'({_SEARCH_TITLE_XP})[1]/@href').get() or '').strip()
        return absolute_url(href, loaded.site.base_url) if href else ''

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        tok = (source.xpath(f'({_SEARCH_DATE_XP})[1]').xpath('string(.)').get() or '').split('|')[-1].strip()
        return iso_date(tok) if tok else None

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath(f'({_DETAIL_TITLE_XP})[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath(f'({_DETAIL_SUMMARY_XP})[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = scene.sel.xpath(f'({_DETAIL_DATE_XP})[1]').xpath('string(.)').get() or ''
        if not raw:
            return None
        tok = raw.split('|')[0].replace('Added', '').replace(':', '').strip()
        return iso_date(tok) if tok else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres: list[str] = []
        for el in scene.sel.xpath(_DETAIL_GENRES_XP):
            g = first_attr(el, 'normalize-space(.)')
            if g and g not in genres:
                genres.append(g)
        count = len(scene.sel.xpath(_DETAIL_ACTORS_XP))
        if count == 3 and 'Threesome' not in genres:
            genres.append('Threesome')
        elif count == 4 and 'Foursome' not in genres:
            genres.append('Foursome')
        elif count > 4 and 'Orgy' not in genres:
            genres.append('Orgy')
        return genres or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath(_DETAIL_ACTORS_XP):
            name = first_attr(el, 'normalize-space(.)')
            if not name:
                name = (el.xpath('(.//span)[1]').xpath('normalize-space(.)').get() or '').strip()
            if not name or name in seen:
                continue
            seen.add(name)
            photo = first_attr(el, '(.//img)[1]/@src0_1x')
            if not photo:
                href = first_attr(el, '@href')
                if href:
                    actor_url = absolute_url(href, scene.site.base_url)
                    page = await self.fetch_and_load(actor_url, None, f'[{scene.site.name}] actor {name}')
                    if page:
                        raw = (
                            page['sel'].xpath('(//img[contains(@class,"model_bio_thumb")])[1]/@src').get()
                            or page['sel'].xpath('(//img[contains(@class,"model_bio_thumb")])[1]/@src0_1x').get()
                            or ''
                        ).strip()
                        if raw:
                            photo = f'https:{raw}' if raw.startswith('//') else raw
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []
        for el in scene.sel.xpath('//img[contains(@class,"update_thumb")]'):
            for attr in ('@src', '@src0_1x'):
                raw = (el.xpath(attr).get() or '').strip()
                if raw.startswith('http') and raw not in images:
                    images.append(raw)
        return images or None
