from __future__ import annotations

import re
from urllib.parse import quote

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, iso_date, title_distance_score
from phoenixadult.utils.helpers.html_helpers import first_attr

STUDIO = 'Czech Authentic Videos'
_CASTING_HOST = 'czechcasting.com'
_TRAILING_ID_RE = re.compile(r'-(\d+)$')


class CzechAVClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        slug = quote(search_data.title.strip(), safe='')
        search_url = search_data.search_url(slug)
        search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {search_url}')
        if not search_results:
            return

        for search_result in search_results['sel'].xpath('//*[contains(@class,"search-item")][.//h2]'):
            a = search_result.xpath('(.//a[.//h2])[1]')
            title = first_attr(a)
            href = first_attr(a, '@href')
            if not title or not href:
                continue

            scene_url = absolute_url(href, search_data.site_info.base_url)
            thumb = first_attr(search_result, '(.//img)[1]/@src')

            m = _TRAILING_ID_RE.search(scene_url.rstrip('/'))
            search_id = int(m.group(1)) if m else 0
            if search_data.scene_id and search_data.scene_id.isdigit() and int(search_data.scene_id) == search_id:
                score: float = 100
            else:
                score = title_distance_score(search_data.title, title)

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    search_date=search_data.search_date,
                    score=score,
                    thumb_url=thumb or None,
                )
            )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    @staticmethod
    def _is_casting(scene: LoadedScene) -> bool:
        return _CASTING_HOST in scene.site.base_url

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = (details_page_elements.xpath('(//h1)[1]').xpath('string(.)').get() or '').strip()

        metadata.title = raw.split(':')[-1].strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        ps = details_page_elements.xpath('//div[contains(@class,"read-more")]//p')
        if not ps:
            return

        second = first_attr(ps[1]) if len(ps) > 1 else ''
        first = first_attr(ps[0])

        metadata.summary = second or first or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            genre_link.xpath('string(.)').get() or ''
            for genre_link in details_page_elements.xpath('//ul[contains(@class,"tags")]//li | //ul//li[contains(@class,"tag")]')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        if not self._is_casting(scene):
            return

        actor_name = (details_page_elements.xpath('(//span[@class="name"])[1]').xpath('string(.)').get() or '').strip()
        if not actor_name:
            return

        age = (details_page_elements.xpath('(//span[@class="age"])[1]').xpath('string(.)').get() or '').strip()
        full_name = f'{actor_name} {age}' if age else actor_name
        photo = first_attr(details_page_elements, '(//div[contains(@class,"gallery")]//a)[1]/@href')

        metadata.actors = [ActorResult(name=full_name, photo_url=photo)]

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        images = self.image_collector(lambda image: absolute_url(image, base))
        xpaths = (
            '//meta[@property="og:image"]/@content',
            '//img[contains(@class,"thumb")]/@src',
        )
        for xpath in xpaths:
            for image_url in details_page_elements.xpath(xpath).getall():
                images.push(image_url)

        metadata.art = images.items
