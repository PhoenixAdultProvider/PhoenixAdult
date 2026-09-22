from __future__ import annotations

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import absolute_first_attr, first_attr, first_text
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.helpers.urls import absolute_url

_LI_XP = '//div[contains(@class,"videoContent")]//ul/li'


class MeanaWolfClient(Client):
    title_xpath = '//div[contains(@class,"trailerArea")]//h3'
    summary_xpath = '//div[contains(@class,"trailerContent")]//p'

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        url = search_data.search_url()
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"')
        if not search_results:
            return

        for search_result in search_results['sel'].xpath('//div[contains(@class,"videoBlock")]'):
            anchor = search_result.xpath('(.//p/a)[1]')
            title = first_attr(anchor, 'normalize-space(.)')
            href = first_attr(anchor, '@href')
            if not title or not href:
                continue

            scene_url = absolute_url(href, search_data.site_info.base_url)
            poster = first_attr(search_result, '(.//img[contains(@class,"video_placeholder")]/@src)[1]')

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([scene_url, poster]),
                )
            )

    # ── Context Loader (curID packs the search-card poster) ───────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        return await self.load_scene_with_extra_tail(payload, site, ctx, 'poster')

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, f'({_LI_XP})[2]').replace('ADDED:', '').strip()

        metadata.release_date = iso_date(date, '%B %d, %Y') if date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [genre_link.xpath('normalize-space(.)').get() for genre_link in details_page_elements.xpath(f'({_LI_XP})[last()]//a')]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            return absolute_first_attr(sel, '(//div[contains(@class,"modelBioPic")]//img/@src0_3x)[1]', base)

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath(f'({_LI_XP})[3]//a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name:
                refs.append((actor_name, absolute_url(href, base) if href else ''))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture, label='actor')

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        poster = scene.extra.get('poster', '') if isinstance(scene.extra, dict) else ''
        if not poster:
            return

        metadata.art = [absolute_url(poster, scene.site.base_url)]
