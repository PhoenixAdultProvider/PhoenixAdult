from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, date_distance_score, iso_date, load_data, title_distance_score
from app.utils.helpers.html_helpers import first_attr

STUDIO = 'Femdom Empire'
_DATE_FMT = '%B %d, %Y'

_MANUAL_MATCHES: dict[str, dict[str, str]] = load_data(__file__, 'femdomempire_manual_matches')


class FemdomEmpireClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')

        def parse_rows(sel: Any) -> None:
            for row in sel.xpath('//div[contains(@class,"item-info")]'):
                a = row.xpath('(.//a)[1]')
                title = first_attr(a)
                href = first_attr(a, '@href')
                if not title or not href:
                    continue

                scene_url = absolute_url(href, search_data.site_info.base_url)

                date_raw = (row.xpath('(.//span[@class="date"])[1]').xpath('string(.)').get() or '').strip()
                date_iso = iso_date(date_raw) if date_raw else None

                score = (
                    date_distance_score(search_data.search_date, date_iso)
                    if search_data.search_date and date_iso
                    else title_distance_score(search_data.title, title)
                )

                results.append(
                    build_search_result(
                        title=title, scene_url=scene_url, query=search_data.title, display_date=date_iso, search_date=search_data.search_date, score=score
                    )
                )

        advanced_search_results = await self.fetch_and_load(
            base + search_data.site_info.search_path.replace('{query}', search_data.encoded),
            FetchCtx(capture=search_data.capture),
            f'[{search_data.site_info.name}] advanced',
        )
        if advanced_search_results:
            parse_rows(advanced_search_results['sel'])

        manual = _MANUAL_MATCHES.get(search_data.title.strip())
        if manual:
            results.append(build_search_result(title=manual['title'], scene_url=manual['url'], query=search_data.title, score=101))

        if results:
            return

        standard_search_results = await self.fetch_and_load(
            f'{base}/tour/search.php?query={search_data.encoded}', FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] standard'
        )
        if standard_search_results:
            parse_rows(standard_search_results['sel'])

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = (details_page_elements.xpath('(//div[contains(@class,"videoDetails")]//h3)[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = (details_page_elements.xpath('(//div[contains(@class,"videoDetails")]//p)[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (
            (details_page_elements.xpath('(//div[contains(@class,"videoInfo") and contains(@class,"clear")]//p)[1]').xpath('string(.)').get() or '')
            .replace('Date Added:', '')
            .strip()
        )

        metadata.release_date = iso_date(date, _DATE_FMT) if date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres: list[str] = []
        for genre_link in details_page_elements.xpath('(//div[contains(@class,"featuring")])[2]//ul//li'):
            genre_name = first_attr(genre_link).lower().replace('categories:', '').replace('tags:', '').strip()
            if genre_name:
                genres.append(genre_name)

        if 'Femdom' not in genres:
            genres.append('Femdom')

        metadata.genres = genres or []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        actors: list[ActorResult] = []
        for actor_link in details_page_elements.xpath('(//div[contains(@class,"featuring")])[1]/ul/li'):
            actor_name = (actor_link.xpath('string(.)').get() or '').replace('Featuring:', '').strip()
            if actor_name:
                actors.append(ActorResult(name=actor_name))

        title = (details_page_elements.xpath('(//div[contains(@class,"videoDetails")]//h3)[1]').xpath('string(.)').get() or '').strip()
        if title == 'Owned by Alexis' and not any(a.name == 'Alexis Monroe' for a in actors):
            actors.append(ActorResult(name='Alexis Monroe'))

        metadata.actors = actors or []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        for image_url in details_page_elements.xpath('//a[contains(@class,"fake_trailer")]//img/@src0_1x').getall():
            images['push'](image_url)

        metadata.art = images['list'] or []
