from __future__ import annotations

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id, slugify
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text

STUDIO = 'Xev Unleashed'
_XEV_PHOTO = 'https://xevunleashed.com/content//contentthumbs/00/01/1-set-2x.jpg'
_AVAILDATE_XP = '(//span[contains(@class,"availdate")]/text())[1]'


class XevUnleashedClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        seen: set[str] = set()

        slug = slugify(search_data.title, replacements=[("'", '')])
        if slug:
            direct_url = f'{base}/updates/{slug}.html'
            direct_page_elements = await self.fetch_and_load(
                direct_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] direct {direct_url}'
            )
            if direct_page_elements:
                raw_title = first_text(direct_page_elements['sel'], '//span[contains(@class,"update_title")]')
                if raw_title:
                    date_raw = (direct_page_elements['sel'].xpath(_AVAILDATE_XP).get() or '').strip()
                    date = (iso_date(date_raw, '%m/%d/%Y') or iso_date(date_raw)) if date_raw else None
                    seen.add(direct_url.lower())

                    results.append(
                        build_search_result(
                            title=raw_title,
                            scene_url=direct_url,
                            query=search_data.title,
                            display_date=date,
                            search_date=search_data.search_date,
                            cur_id=pack_cur_id([direct_url, date or '']),
                        )
                    )

        search_url = base + search_data.site_info.search_path.replace('{query}', search_data.encoded)
        search_results = await self.fetch_and_load(
            search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"'
        )
        if search_results:
            for search_result in search_results['sel'].xpath('//div[contains(@class,"updateItem")]'):
                raw_title = first_text(search_result, './/h4')
                href = first_attr(search_result, '(.//a/@href)[1]')
                if not raw_title or not href:
                    continue

                scene_url = absolute_url(href, search_data.site_info.base_url)
                if scene_url.lower() in seen:
                    continue

                seen.add(scene_url.lower())
                date_raw = first_text(search_result, './/p//span')
                date = iso_date(date_raw) if date_raw else None

                results.append(
                    build_search_result(
                        title=raw_title,
                        scene_url=scene_url,
                        query=search_data.title,
                        display_date=date,
                        search_date=search_data.search_date,
                        cur_id=pack_cur_id([scene_url, date or '']),
                    )
                )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//span[contains(@class,"update_title")]') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//span[contains(@class,"latest_update_description")]') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [STUDIO]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date_raw = (details_page_elements.xpath(_AVAILDATE_XP).get() or '').strip()
        if date_raw:
            parsed = iso_date(date_raw, '%m/%d/%Y') or iso_date(date_raw)
            if parsed:
                metadata.release_date = parsed
                return

        if scene.scene_date:
            metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            genre_link.xpath('normalize-space(.)').get() for genre_link in details_page_elements.xpath('//span[contains(@class,"update_tags")]//a')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        actors = [ActorResult(name='Xev Bellringer', photo_url=_XEV_PHOTO)]
        keywords = (details_page_elements.xpath('(//meta[@name="keywords"]/@content)[1]').get() or '').lower()
        if 'princess leia' in keywords:
            actors.append(ActorResult(name='Princess Leia'))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        images = self.image_collector(lambda image: absolute_url((image or '').strip(), base))
        for src in details_page_elements.xpath('//div[contains(@class,"update_image")]//img/@src0_4x').getall():
            images['push'](src)

        metadata.art = images['list']
