from __future__ import annotations

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text
from app.utils.logging.logger import logger

STUDIO = 'TwoTGirls'


class TwoTGirlsClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        slug = search_data.title.replace(' ', '-')
        if not slug:
            return

        direct_url = f'{base}/video/{slug}'

        direct_page_elements = await self.fetch_and_load(
            direct_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] direct {direct_url}'
        )
        if direct_page_elements:
            cards = direct_page_elements['sel'].xpath('//div[contains(@class,"video-details")]')
            title = first_text(cards[0], './/h1') if cards else ''
            if title:
                logger.info(search_data.site_info.name, f'TwoTGirls direct hit "{title}" ({direct_url})')

                results.append(
                    build_search_result(
                        title=title,
                        scene_url=direct_url,
                        query=search_data.title,
                        search_date=search_data.search_date,
                        cur_id=pack_cur_id([direct_url, search_data.search_date or '']),
                    )
                )
                return

        search_url = base + search_data.site_info.search_path.replace('{query}', search_data.encoded)
        search_results = await self.fetch_and_load(
            search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"'
        )
        if not search_results:
            return

        seen: set[str] = set()
        for search_result in search_results['sel'].xpath('//article'):
            title = first_text(search_result, './/h2')
            href = first_attr(search_result, '(.//a/@href)[1]')
            if not title or not href:
                continue

            scene_url = absolute_url(href, search_data.site_info.base_url)
            if scene_url in seen:
                continue

            seen.add(scene_url)

            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([scene_url, search_data.search_date or '']),
                )
            )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//h1') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//div[contains(@class,"shadow") and contains(@class,"video-details")]//p') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        if not scene.scene_date:
            return

        metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres = self.dedup_strings(
            [first_attr(genre_link, 'normalize-space(.)') for genre_link in details_page_elements.xpath('//p[contains(@class,"video-tags")]//a')]
        )
        count = len(details_page_elements.xpath('//p[contains(@class,"video-date")]//a'))
        if (group := self.group_genre_for(count)) and group not in genres:
            genres.append(group)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for actor_link in details_page_elements.xpath('//p[contains(@class,"video-date")]//a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if not actor_name or actor_name in seen:
                continue

            seen.add(actor_name)
            photo = ''
            if href:
                url = absolute_url(href, base)
                model_page_elements = await self.fetch_and_load(url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {actor_name}')
                if model_page_elements:
                    raw = first_attr(model_page_elements['sel'], '(//div[contains(@class,"col-md-4")]//img/@src)[1]')
                    if raw:
                        photo = absolute_url(raw, base)

            actors.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        images = self.image_collector(lambda image: absolute_url((image or '').strip().replace('720p', '1080p'), base))
        for poster in details_page_elements.xpath('//video/@poster').getall():
            images['push'](poster)

        for src in details_page_elements.xpath('//article//div[contains(@class,"row")]//img/@src').getall():
            images['push'](src)

        metadata.art = images['list']
