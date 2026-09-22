from __future__ import annotations

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, iso_date, load_data
from phoenixadult.utils.helpers.html_helpers import first_attr

_STUDIO_OVERRIDES: dict[str, str] = load_data(__file__, 'interracialpass_studios')
_TITLE_SELECTORS: dict[str, str] = {'BBC Surprise': 'h3', 'Hot Milfs Fuck': 'h1'}


def _studio_for(site_name: str) -> str:
    return _STUDIO_OVERRIDES.get(site_name, site_name)


def _title_selector_for(site_name: str) -> str:
    return _TITLE_SELECTORS.get(site_name, 'h2')


class InterracialPassClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        seen: set[str] = set()

        direct_url = f'{base}/t1/trailers/{search_data.title.strip().replace(" ", "-")}.html'
        direct_page_elements = await self.fetch_and_load(
            direct_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] directScene {direct_url}'
        )
        if direct_page_elements:
            title = (
                direct_page_elements['sel'].xpath('(//div[contains(@class,"video-player")]//h2[contains(@class,"section-title")])[1]').xpath('string(.)').get()
                or ''
            ).strip()
            if title:
                raw_date = (
                    (direct_page_elements['sel'].xpath('(//div[contains(@class,"update-info-row")])[1]').xpath('string(.)').get() or '')
                    .replace('Released:', '')
                    .strip()
                )
                seen.add(direct_url)

                results.append(
                    build_search_result(
                        site=search_data.site_info,
                        title=title,
                        scene_url=direct_url,
                        query=search_data.title,
                        display_date=iso_date(raw_date),
                        search_date=search_data.search_date,
                    )
                )

        search_url = search_data.search_url(search_data.title.strip().replace(' ', '+'))
        search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {search_url}')
        if search_results:
            for search_result in search_results['sel'].xpath('//div[contains(@class,"item-video")]'):
                a = search_result.xpath('(.//a)[1]')
                title = first_attr(a, '@title')
                href = first_attr(a, '@href')
                if not title or not href:
                    continue

                scene_url = absolute_url(href, search_data.site_info.base_url)
                if scene_url in seen:
                    continue

                seen.add(scene_url)
                date_tok = (search_result.xpath('(.//div[contains(@class,"more-info-div")])[1]').xpath('string(.)').get() or '').split('|')[-1].strip()

                results.append(
                    build_search_result(
                        site=search_data.site_info,
                        title=title,
                        scene_url=scene_url,
                        query=search_data.title,
                        display_date=iso_date(date_tok) if date_tok else None,
                        search_date=search_data.search_date,
                    )
                )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        tag = _title_selector_for(scene.site.name)

        metadata.title = (
            details_page_elements.xpath(f'(//div[contains(@class,"video-player")]//{tag}[contains(@class,"section-title")])[1]').xpath('string(.)').get() or ''
        ).strip()

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = (
            (details_page_elements.xpath('(//div[contains(@class,"update-info-block")])[2]').xpath('string(.)').get() or '').replace('Description:', '').strip()
        )

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = _studio_for(scene.site.name)

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (details_page_elements.xpath('(//div[contains(@class,"update-info-row")])[1]').xpath('string(.)').get() or '').replace('Released:', '').strip()

        metadata.release_date = (iso_date(date) if date else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            genre_link.xpath('string(.)').get() or '' for genre_link in details_page_elements.xpath('//ul[contains(@class,"tags")]//li//a')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')
        is_bbc = scene.site.name == 'BBC Surprise'
        actors: list[ActorResult] = []
        for actor_link in details_page_elements.xpath('//div[contains(@class,"models-list-thumbs")]//li'):
            actor_name = (actor_link.xpath('(.//span)[1]').xpath('string(.)').get() or '').strip()
            if not actor_name:
                continue

            raw = first_attr(actor_link, '(.//img)[1]/@src0_3x')
            photo = (raw if raw.startswith('http') else base + raw) if raw else ''
            if is_bbc and actor_name == 'Twins':
                actors.append(ActorResult(name='Joey White', photo_url=photo))
                actors.append(ActorResult(name='Sami White', photo_url=photo))
            else:
                actors.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')
        images = self.image_collector(lambda image: image if image.startswith('http') else base + image)
        for src in details_page_elements.xpath('//div[contains(@class,"player-thumb")]//img/@src0_1x').getall():
            images.push(src)

        metadata.art = images.items
