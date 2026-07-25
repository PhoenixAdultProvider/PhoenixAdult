from __future__ import annotations

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import build_search_result, iso_date, join_url, pack_cur_id, slugify
from phoenixadult.utils.helpers.html_helpers import append_year_param, first_attr, first_text, meta_content

_DIRECTOR = ActorResult(
    name='Petter Hegre',
    photo_url='https://img.discogs.com/TafxhnwJE2nhLodoB6UktY6m0xM=/fit-in/180x264/filters:strip_icc():format(jpeg):mode_rgb():quality(90)/discogs-images/A-2236724-1305622884.jpeg.jpg',
)


class HegreClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')

        direct = base + search_data.site_info.search_path.replace('{query}', slugify(search_data.title))
        direct_page_elements = await self.fetch_and_load(direct, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] directScene {direct}')
        if direct_page_elements:
            title = first_text(direct_page_elements['sel'], '//h1')
            if title:
                raw_date = first_text(direct_page_elements['sel'], '//span[contains(@class,"date")]')
                date = iso_date(raw_date) if raw_date else None

                results.append(
                    build_search_result(
                        site=search_data.site_info,
                        title=title,
                        scene_url=direct,
                        query=search_data.title,
                        display_date=date,
                        search_date=search_data.search_date,
                        score=100,
                        cur_id=pack_cur_id([direct]),
                    )
                )
                return

        search_url = append_year_param(f'{base}/search?q={search_data.encoded}', 'year', year=search_data.year, search_date=search_data.search_date)
        search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {search_url}')
        if not search_results:
            return

        for search_result in search_results['sel'].xpath('//div[contains(@class,"item")]'):
            href = first_attr(search_result, '(.//a/@href)[1]')
            if not href or not ('/films/' in href or '/massage/' in href):
                continue

            scene_url = join_url(href, base)
            title = first_attr(search_result, '(.//img/@alt)[1]')
            if not title:
                continue

            raw_date = first_text(search_result, '(.//div[contains(@class,"details")]/span)[last()]')
            date = iso_date(raw_date) if raw_date else None

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

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = meta_content(details_page_elements, 'og:title') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = first_text(details_page_elements, '//div[contains(@class,"record-description-content") and contains(@class,"record-box-content")]')
        if not raw:
            return

        idx = raw.find('Runtime')

        metadata.summary = raw[:idx].strip() if idx >= 0 else raw

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Hegre'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, '//span[contains(@class,"date")]')

        metadata.release_date = iso_date(date) if date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres: list[str] = []
        for genre_link in details_page_elements.xpath('//a[contains(@class,"tag")]'):
            genre_name = first_attr(genre_link, 'normalize-space(.)').lower()
            if genre_name and genre_name not in genres:
                genres.append(genre_name)

        count = len(details_page_elements.xpath('//a[contains(@class,"record-model")]'))
        if (group := self.group_genre_for(count)) and group not in genres:
            genres.append(group)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        entries: list[ActorResult] = []
        for actor_link in details_page_elements.xpath('//a[contains(@class,"record-model")]'):
            actor_name = first_attr(actor_link, '@title')
            raw = first_attr(actor_link, '(.//img/@src)[1]')
            entries.append(ActorResult(name=actor_name, photo_url=raw.replace('240x', '480x') if raw else ''))

        metadata.actors = self.dedup_people(entries)

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.directors = [_DIRECTOR]

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = meta_content(details_page_elements, 'twitter:image')
        if not raw:
            return

        images: list[str] = []
        small = raw.replace('board-image', 'poster-image').replace('1600x', '640x')
        if small != raw:
            images.append(small)

        large = raw.replace('1600x', '1920x')
        if large not in images:
            images.append(large)

        metadata.art = images
