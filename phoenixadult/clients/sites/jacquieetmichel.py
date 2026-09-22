from __future__ import annotations

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.data_files import load_data
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.helpers.urls import absolute_url

_ACTORS: dict[str, list[str]] = load_data(__file__, 'jacquieetmichel_actors')

_RELEASE_XP = '(//div[contains(@class,"content-detail__infos__row")]//p[contains(@class,"content-detail__description--link")])[2]'


class JacquieEtMichelClient(Client):
    title_xpath = '//h1[contains(@class,"content-detail__title")]'
    summary_xpath = '//div[contains(@class,"content-detail__description")]'

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        seen: set[str] = set()

        search_url = search_data.search_url()
        search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {search_url}')
        if search_results:
            for search_result in search_results['sel'].xpath('//a[contains(@class,"content-card--video")]'):
                title = first_text(search_result, './/h2[contains(@class,"content-card__title")]')
                href = first_attr(search_result, '@href')
                if not title or not href:
                    continue

                scene_url = absolute_url(href, search_data.site_info.base_url)
                if scene_url in seen:
                    continue

                seen.add(scene_url)
                date_raw = first_text(search_result, './/div[contains(@class,"content-card__date")]').replace('Added on', '').strip()
                date = iso_date(date_raw)

                results.append(
                    build_search_result(
                        site=search_data.site_info,
                        title=title,
                        scene_url=scene_url,
                        query=search_data.title,
                        display_date=date,
                        search_date=search_data.search_date,
                        cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
                    )
                )

        if search_data.scene_id:
            scene_url = f'{base}/en/content/{search_data.scene_id}'
            if scene_url not in seen:
                direct_page_elements = await self.fetch_and_load(
                    scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] directScene {scene_url}'
                )
                title = first_text(direct_page_elements['sel'], '//h1[contains(@class,"content-detail__title")]') if direct_page_elements else ''
                if title:
                    results.append(
                        build_search_result(
                            site=search_data.site_info,
                            title=title,
                            scene_url=scene_url,
                            query=search_data.title,
                            search_date=search_data.search_date,
                            score=100,
                            cur_id=pack_cur_id([x for x in (scene_url, search_data.search_date) if x]),
                        )
                    )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, _RELEASE_XP)

        metadata.release_date = (iso_date(date) if date else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres: list[str] = []
        for genre_link in details_page_elements.xpath('//div[contains(@class,"content-detail__row")]//li[contains(@class,"content-detail__tag")]'):
            genre_name = (genre_link.xpath('normalize-space(.)').get() or '').replace(',', '').strip()
            if genre_name == 'Sodomy':
                genre_name = 'Anal'

            if genre_name and genre_name not in genres:
                genres.append(genre_name)

        if 'French porn' not in genres:
            genres.append('French porn')

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        for fragment, names in _ACTORS.items():
            if fragment in scene.url:
                metadata.actors = [ActorResult(name=actor_name) for actor_name in names]
                return

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = first_attr(details_page_elements, '(//video/@poster)[1]')
        if not raw:
            return

        metadata.art = [absolute_url(raw, scene.site.base_url)]
