from __future__ import annotations

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_attr


class WankzVRClient(Client):
    def __init__(self) -> None:
        super().__init__({'Cookie': 'sst=ulang-en'})

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        tokens = search_data.title.strip().split()
        scene_id = tokens[0] if tokens and tokens[0].isdigit() else None

        if scene_id and len(tokens) == 1:
            scene_url = f'{base}/{scene_id}'
            search_results = await self.fetch_and_load(
                scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] directScene {scene_url}'
            )
            if not search_results:
                return

            title = (search_results['sel'].xpath('(//h1[contains(@class,"detail__title")])[1]').xpath('string(.)').get() or '').strip()
            if not title:
                return

            date = iso_date((search_results['sel'].xpath('(//span[contains(@class,"detail__date")])[1]').xpath('string(.)').get() or '').strip())

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=date,
                    search_date=search_data.search_date,
                    score=100,
                    cur_id=pack_cur_id([scene_url]),
                )
            )
            return

        search_url = base + search_data.site_info.search_path.replace('{query}', search_data.encoded.replace('%20', '+'))
        search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {search_url}')
        if not search_results:
            return

        for search_result in search_results['sel'].xpath('//ul[contains(@class,"cards-list")]//li'):
            texts = search_result.xpath('(.//div[contains(@class,"card__footer")]//div[contains(@class,"card__h")])[1]/text()').getall()
            title = next((t.strip() for t in texts if t.strip()), '')
            href = first_attr(search_result, '(.//a)[1]/@href')
            if not title or not href:
                continue

            scene_url = absolute_url(href, search_data.site_info.base_url)
            date = iso_date((search_result.xpath('(.//div[contains(@class,"card__date")])[1]').xpath('string(.)').get() or '').strip())

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=date,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([scene_url]),
                )
            )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = (details_page_elements.xpath('(//h1[contains(@class,"detail__title")])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = (details_page_elements.xpath('(//div[contains(@class,"detail__txt")])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (details_page_elements.xpath('(//span[contains(@class,"detail__date")])[1]').xpath('string(.)').get() or '').strip()

        metadata.release_date = iso_date(date) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            genre_link.xpath('normalize-space(.)').get() for genre_link in details_page_elements.xpath('//div[contains(@class,"tag-list")]//a')
        ]

        metadata.genres = self.dedup_strings(values) or []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            srcset = first_attr(sel, '(//div[contains(@class,"person__avatar")]//source)[2]/@srcset')
            well_formed = len(sel.xpath('/html/*')) == 2
            return srcset.replace('.webp', '.jpg') if srcset and well_formed else ''

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('//div[contains(@class,"detail__models")]//a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name:
                refs.append((actor_name, absolute_url(href, base) if href else ''))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, label=scene.site.name) or []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = first_attr(details_page_elements, '(//meta[@property="og:image"])[1]/@content')
        if not raw:
            return

        metadata.art = [raw.replace('cover', 'hero').replace('medium.jpg', 'large.jpg')]
