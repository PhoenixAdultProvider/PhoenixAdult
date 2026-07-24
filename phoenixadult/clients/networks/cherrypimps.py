from __future__ import annotations

from typing import Any

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from phoenixadult.utils.helpers.helpers import absolute_url, iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr

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
    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        base = search_data.site_info.base_url.rstrip('/')
        slug = '+'.join(search_data.title.split())
        sources: list[Any] = []
        for p in range(1, _SEARCH_PAGES + 1):
            url = base + search_data.site_info.search_path.replace('{query}', slug) + f'&page={p}'
            search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {url}')
            if not search_results:
                continue

            sources.extend(search_results['sel'].xpath('//div[contains(@class,"item-updates")]//div[contains(@class,"item-update")]'))

        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath(f'({_SEARCH_TITLE_XP})[1]').xpath('string(.)').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = (source.xpath(f'({_SEARCH_TITLE_XP})[1]/@href').get() or '').strip()
        return absolute_url(href, loaded.site.base_url) if href else ''

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        tok = (source.xpath(f'({_SEARCH_DATE_XP})[1]').xpath('string(.)').get() or '').split('|')[-1].strip()
        return iso_date(tok) if tok else None

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = (details_page_elements.xpath(f'({_DETAIL_TITLE_XP})[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = (details_page_elements.xpath(f'({_DETAIL_SUMMARY_XP})[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = details_page_elements.xpath(f'({_DETAIL_DATE_XP})[1]').xpath('string(.)').get() or ''
        if not date:
            return

        tok = date.split('|')[0].replace('Added', '').replace(':', '').strip()

        metadata.release_date = iso_date(tok) if tok else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres = self.dedup_strings([first_attr(genre_link, 'normalize-space(.)') for genre_link in details_page_elements.xpath(_DETAIL_GENRES_XP)])
        count = len(details_page_elements.xpath(_DETAIL_ACTORS_XP))
        if (group := self.group_genre_for(count)) and group not in genres:
            genres.append(group)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        actors: list[ActorResult] = []
        seen: set[str] = set()
        for actor_link in details_page_elements.xpath(_DETAIL_ACTORS_XP):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            if not actor_name:
                actor_name = (actor_link.xpath('(.//span)[1]').xpath('normalize-space(.)').get() or '').strip()

            if not actor_name or actor_name in seen:
                continue

            seen.add(actor_name)
            photo = first_attr(actor_link, '(.//img)[1]/@src0_1x')
            if not photo:
                href = first_attr(actor_link, '@href')
                if href:
                    actor_url = absolute_url(href, scene.site.base_url)
                    model_page_elements = await self.fetch_and_load(actor_url, None, f'[{scene.site.name}] actor {actor_name}')
                    if model_page_elements:
                        raw = (
                            model_page_elements['sel'].xpath('(//img[contains(@class,"model_bio_thumb")])[1]/@src').get()
                            or model_page_elements['sel'].xpath('(//img[contains(@class,"model_bio_thumb")])[1]/@src0_1x').get()
                            or ''
                        ).strip()
                        if raw:
                            photo = f'https:{raw}' if raw.startswith('//') else raw

            actors.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector()
        for row in details_page_elements.xpath('//img[contains(@class,"update_thumb")]'):
            for attr in ('@src', '@src0_1x'):
                raw = (row.xpath(attr).get() or '').strip()
                if raw.startswith('http'):
                    images['push'](raw)

        metadata.art = images['list']
