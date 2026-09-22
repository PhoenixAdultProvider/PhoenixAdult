from __future__ import annotations

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, iso_date, load_data, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_attr

_DATE_FMT = '%Y %B %d'
_ROSTER: set[str] = set(load_data(__file__, 'queensnake_actors'))


def _is_qs_actor(tag: str) -> bool:
    return tag.strip().lower() in _ROSTER


class QueenSnakeClient(Client):
    title_xpath = '(//span[@class="contentFilmName"])[1]'
    summary_xpath = '(//div[@class="contentPreviewDescription"])[1]'

    def __init__(self) -> None:
        super().__init__({'Cookie': 'cLegalAge=true'})

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        slug = search_data.title.strip().replace(' ', '-').lower()
        search_url = f'{base}/previewmovie/{slug}/'
        search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {search_url}')
        if not search_results:
            return

        pager = search_results['sel'].xpath('(//div[@class="pagerWrapper"]//a)[1]/@href').get() or ''
        if '/previewmovies/0' in pager:
            return

        for search_result in search_results['sel'].xpath('//div[@class="contentBlock"]'):
            title = (search_result.xpath('(.//span[@class="contentFilmName"])[1]').xpath('string(.)').get() or '').strip()
            if not title:
                continue

            raw_date = (search_result.xpath('(.//span[@class="contentFileDate"])[1]').xpath('string(.)').get() or '').strip().split(' • ')[0]
            date = iso_date(raw_date, _DATE_FMT) if raw_date else None

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=search_url,
                    query=search_data.title,
                    display_date=date,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([x for x in (search_url, date) if x]),
                )
            )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (details_page_elements.xpath('(//span[@class="contentFileDate"])[1]').xpath('string(.)').get() or '').strip().split(' • ')[0]

        metadata.release_date = (iso_date(date, _DATE_FMT) if date else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres = ['BDSM', 'S&M']
        for genre_link in details_page_elements.xpath('//div[@class="contentPreviewTags"]//a'):
            genre_name = first_attr(genre_link, 'normalize-space(.)')
            if genre_name and genre_name not in genres:
                genres.append(genre_name)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        actors: list[ActorResult] = []
        seen: set[str] = set()
        for actor_link in details_page_elements.xpath('//div[@class="contentPreviewTags"]//a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            if not actor_name or actor_name in seen or not _is_qs_actor(actor_name):
                continue

            seen.add(actor_name)
            actors.append(ActorResult(name=actor_name))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        for src in details_page_elements.xpath('//div[@class="contentBlock"]//img[contains(@src,"preview")]/@src').getall():
            images.push(src)

        metadata.art = images.items
