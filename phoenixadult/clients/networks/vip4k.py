from __future__ import annotations

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import build_search_result, iso_date, join_url, load_data, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_attr

STUDIO = 'VIP4K'
_GENRES: dict[str, list[str]] = load_data(__file__, 'vip4k_genres')


def _clean_title(raw: str) -> str:
    return raw.split('|')[-1].strip() if raw else raw


class VIP4KClient(Client):
    summary_xpath = '(//div[contains(@class,"player-description__text")])[1]'

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')

        scene_id = search_data.scene_id or ''
        if scene_id.isdigit() and int(scene_id) > 10:
            scene_url = f'{base}/en/videos/{scene_id}'
            direct_page_elements = await self.fetch_and_load(
                scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] directScene {scene_url}'
            )
            if direct_page_elements:
                title = _clean_title(direct_page_elements['sel'].xpath('(//title)[1]').xpath('string(.)').get() or '')
                if title:
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
                    return

        search_url = search_data.search_url()
        search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {search_url}')
        if not search_results:
            return

        for search_result in search_results['sel'].xpath('//div[contains(@class,"item__description")]'):
            anchor = search_result.xpath('(.//a[contains(@class,"item__title")])[1]')
            raw_title = first_attr(anchor)
            href = first_attr(anchor, '@href')
            if not raw_title or not href:
                continue

            scene_url = join_url(href, base)
            raw_date = (search_result.xpath('(.//div[contains(@class,"item__date")])[1]').xpath('string(.)').get() or '').strip()
            date = (iso_date(raw_date) if raw_date else None) or search_data.search_date

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=raw_title,
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=date,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([scene_url, date or '']),
                )
            )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _tagline(self, scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        raw = (
            details_page_elements.xpath('(//a[contains(@class,"player-additional__site") and contains(@class,"ph_register")])[1]').xpath('string(.)').get()
            or ''
        ).strip()
        return raw.replace('Sis', 'Sis.Porn') if raw else scene.site.name

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = _clean_title(details_page_elements.xpath('(//title)[1]').xpath('string(.)').get() or '') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline(scene)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [self._tagline(scene)]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (details_page_elements.xpath('(//span[contains(@class,"player-additional__text")])[1]').xpath('string(.)').get() or '').strip()
        if date:
            metadata.release_date = iso_date(date)
            return

        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres = list(_GENRES.get(scene.site.name, []))
        for genre_link in details_page_elements.xpath('//div[contains(@class,"tags")]//a'):
            genre_name = (genre_link.xpath('string(.)').get() or '').replace('#', '').strip()
            if genre_name and genre_name not in genres:
                genres.append(genre_name)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        entries = [
            ActorResult(name=(actor_link.xpath('(.//div[contains(@class,"model__name")])[1]').xpath('string(.)').get() or '').strip())
            for actor_link in details_page_elements.xpath(
                '//a[contains(@class,"player-description__model") and contains(@class,"model") and contains(@class,"ph_register")]'
            )
        ]

        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: image if image.startswith('http') else (f'https:{image}' if image.startswith('//') else image))
        for row in details_page_elements.xpath('//div[contains(@class,"player-item__block")]//img'):
            images.push((row.xpath('@data-src').get() or row.xpath('@src').get() or '').strip())

        metadata.art = images.items
