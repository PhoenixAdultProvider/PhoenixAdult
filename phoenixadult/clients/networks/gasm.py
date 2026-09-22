from __future__ import annotations

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.data_files import load_data
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr
from phoenixadult.utils.helpers.scoring import title_distance_score
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.helpers.text import slugify
from phoenixadult.utils.helpers.urls import absolute_url
from phoenixadult.utils.processors.title_case import title_case

STUDIO = 'GASM'
_DATE_FMT = '%b %d, %Y'

_CHANNELS: dict[str, str] = load_data(__file__, 'gasm_channels')


class GasmClient(Client):
    title_xpath = '(//h1[contains(@class,"post_title")]//span)[1]'

    def __init__(self) -> None:
        super().__init__({'Cookie': 'WarningModal=true'})

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')

        if search_data.scene_id:
            scene_url = f'{base}/post/details/{search_data.scene_id}'
            search_results = await self.fetch_and_load(scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] direct {scene_url}')
            if not search_results:
                return

            title = (search_results['sel'].xpath('(//h1[contains(@class,"post_title")]//span)[1]').xpath('string(.)').get() or '').strip()
            if not title:
                return

            date_raw = (search_results['sel'].xpath('(//h3[contains(@class,"post_date")])[1]').xpath('string(.)').get() or '').strip()
            date_iso = iso_date(date_raw, _DATE_FMT) if date_raw else None

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=date_iso,
                    search_date=search_data.search_date,
                    score=100,
                )
            )
            return

        encoded = slugify(search_data.title).replace('-', '+')
        search_url = base + search_data.site_info.search_path + encoded
        channel = _CHANNELS.get(search_data.site_info.name)
        if channel:
            search_url += f'&channel={channel}'

        search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search')
        if not search_results:
            return

        for search_result in search_results['sel'].xpath('//div[contains(@class,"results_item")]'):
            a = search_result.xpath('(.//a[contains(@class,"post_title")])[1]')
            title = first_attr(a)
            href = first_attr(a, '@href')
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
                    score=title_distance_score(search_data.title, title),
                )
            )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _tagline(self, scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        raw = (details_page_elements.xpath('(//a[contains(@href,"/studio/profile/")])[1]').xpath('string(.)').get() or '').strip()
        return title_case(raw, site_name=scene.site.name) if raw else ''

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = details_page_elements.xpath('(//h2[contains(@class,"post_description")])[1]').xpath('string(.)').get() or ''

        metadata.summary = raw.replace('´', "'").replace('’', "'").strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline(scene) or ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        out: list[str] = []
        tagline = self._tagline(scene)
        if tagline:
            out.append(tagline)

        dvd = (details_page_elements.xpath('(//div[contains(@class,"post_item") and contains(@class,"dvd")]//h1)[1]').xpath('string(.)').get() or '').strip()
        if dvd:
            out.append(title_case(dvd.lower(), site_name=scene.site.name))

        metadata.collections = out or None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (details_page_elements.xpath('(//h3[contains(@class,"post_date")])[1]').xpath('string(.)').get() or '').strip()

        metadata.release_date = (iso_date(date, _DATE_FMT) if date else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        out = [
            genre_name
            for genre_name in (first_attr(genre_link, 'normalize-space(.)') for genre_link in details_page_elements.xpath('//a[contains(@href,"/search?s=")]'))
            if genre_name
        ]

        metadata.genres = out

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        out = [
            ActorResult(name=n)
            for n in (first_attr(actor_link, 'normalize-space(.)') for actor_link in details_page_elements.xpath('//a[contains(@href,"models/")]'))
            if n
        ]

        metadata.actors = out

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        for src in details_page_elements.xpath('//img[contains(@class,"item_cover")]/@src').getall():
            images.push(src)

        images.push(details_page_elements.xpath('(//meta[@name="twitter:image"])[1]/@content').get())

        metadata.art = images.items
