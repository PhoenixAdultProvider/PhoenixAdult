from __future__ import annotations

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text, script_match, web_search_urls


class ExpliciteArtClient(Client):
    title_xpath = '//title'
    summary_xpath = '//div[contains(@class,"player-info-desc")]'
    genres_xpath = '//span[contains(@class,"tags")]//a'

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        slug = search_data.title.strip().lower().replace(' ', '-')
        search_url = f'{base}/visitor/search/videos/{slug}/page1.html'

        search_results = await self.fetch_and_load(
            search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"'
        )
        if search_results:
            sel: Selector = search_results['sel']
            for card in sel.xpath('//div[contains(@class,"content")]'):
                if not card.xpath('.//*[contains(@src,"video")]'):
                    continue

                title = first_text(card, './/div[contains(@class,"vtitle")]')
                href = card.xpath('(.//a/@href)[1]').get() or ''
                if not title or not href:
                    continue

                scene_url = absolute_url(href, search_data.site_info.base_url)

                results.append(
                    build_search_result(
                        site=search_data.site_info,
                        title=title,
                        scene_url=scene_url,
                        query=search_data.title,
                        search_date=search_data.search_date,
                        cur_id=pack_cur_id([scene_url]),
                    )
                )

        if not results:
            for scene_url, details_page_elements in await self.fetch_candidate_pages(
                await web_search_urls(search_data.title, search_data.site_info),
                FetchCtx(capture=search_data.capture),
                lambda scene_url: f'[{search_data.site_info.name}] web-search {scene_url}',
            ):
                if not details_page_elements:
                    continue

                title = first_text(details_page_elements['sel'], '//title')
                if not title:
                    continue

                results.append(
                    build_search_result(
                        site=search_data.site_info,
                        title=title,
                        scene_url=scene_url,
                        query=search_data.title,
                        search_date=search_data.search_date,
                        cur_id=pack_cur_id([scene_url]),
                    )
                )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            raw = sel.xpath('(//div[contains(@class,"pornstar-bio-left")]//*[@src])[1]/@src').get() or ''
            return absolute_url(raw, base) if raw else ''

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('//div[contains(@class,"player-info-row")]//a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = actor_link.xpath('@href').get() or ''
            if actor_name and href:
                refs.append((actor_name, absolute_url(href, base)))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        script_text = details_page_elements.xpath('(//div[@id="player"]//script)[1]/text()').get() or ''
        poster = script_match(script_text, r'image:\s*"([^"]+)"')

        metadata.art = [poster] if poster else []
