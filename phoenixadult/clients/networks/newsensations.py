from __future__ import annotations

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_attr, web_search_urls
from phoenixadult.utils.logging.best_effort import best_effort
from phoenixadult.utils.processors.actor_strip import enabled_for, strip_actor_prefix

STUDIO = 'New Sensations'


class NewSensationsClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        stem = search_data.site_info.base_url.rstrip('/') + search_data.site_info.search_path

        title_no_actors = strip_actor_prefix(search_data.title) if enabled_for(search_data.site_info) else search_data.title

        slug = title_no_actors.replace(' ', '-')

        candidates: list[str] = [f'{stem}updates/{slug}.html', f'{stem}updates/{slug}-.html', f'{stem}updates/{slug}-4k.html', f'{stem}dvds/{slug}.html']
        seen = set(candidates)
        with best_effort(search_data.site_info.name, 'webSearch'):
            found = await web_search_urls(search_data.title, search_data.site_info)
            for url in found:
                is_scene = '/updates/' in url or '/dvds/' in url or '/scenes/' in url
                is_tour = '/tour_ns/' in url or '/tour_famxxx/' in url
                if is_scene and is_tour and url not in seen:
                    seen.add(url)
                    candidates.append(url)

        for scene_url, search_results in await self.fetch_candidate_pages(
            candidates, FetchCtx(capture=search_data.capture), lambda scene_url: f'[{search_data.site_info.name}] {scene_url}'
        ):
            if not search_results:
                continue

            title = (
                search_results['sel']
                .xpath('(//div[@class="indScene"]/h1 | //div[@class="indSceneDVD"]/h1 | //div[@class="indScene"]/h2 | //div[@class="indSceneDVD"]/h2)[1]')
                .xpath('string(.)')
                .get()
                or ''
            ).strip()
            if not title:
                continue

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

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _is_dvd(self, scene: LoadedScene) -> bool:
        return '/dvds/' in scene.url

    def _dvd_tagline(self, scene: LoadedScene) -> str | None:
        if not self._is_dvd(scene):
            return None

        details_page_elements = scene.require_sel()

        return (details_page_elements.xpath('(//div[@class="indSceneDVD"]/h1)[1]').xpath('string(.)').get() or '').strip() or None

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        xp = '(//div[@class="indSceneDVD"]/h1)[1]' if self._is_dvd(scene) else '(//div[@class="indScene"]/h1 | //div[@class="indScene"]/h2)[1]'

        metadata.title = (details_page_elements.xpath(xp).xpath('string(.)').get() or '').strip()

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = (
            (details_page_elements.xpath('(//div[@class="description"]/h2)[1]').xpath('string(.)').get() or '').replace('Description:', '').strip()
        )

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._dvd_tagline(scene) or ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        if self._is_dvd(scene):
            dvd = self._dvd_tagline(scene)
            metadata.collections = [dvd] if dvd else None
            return

        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        if self._is_dvd(scene):
            date = (details_page_elements.xpath('(//div[@class="datePhotos"])[1]').xpath('string(.)').get() or '').replace('RELEASED:', '').strip()
        else:
            date = (details_page_elements.xpath('(//div[@class="sceneDateP"]/span)[1]').xpath('string(.)').get() or '').strip()

        metadata.release_date = (iso_date(date) if date else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres: list[str] = []
        if self._is_dvd(scene):
            for genre_link in details_page_elements.xpath('//div[@class="textLink"]//a'):
                genre_name = first_attr(genre_link, 'normalize-space(.)')
                if genre_name and genre_name not in genres:
                    genres.append(genre_name)
        else:
            cast = len(details_page_elements.xpath('//div[@class="sceneTextLink"]//span[@class="tour_update_models"]/a'))
            if (group := self.group_genre_for(cast)) and group not in genres:
                genres.append(group)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        xp = '//span[@class="tour_update_models"]/a' if self._is_dvd(scene) else '//div[@class="sceneTextLink"]//span[@class="tour_update_models"]/a'

        def extract_photo(sel: Selector) -> str:
            raw = first_attr(sel, '(//div[@class="modelBioPic"]/img)[1]/@src0_3x')
            return absolute_url(raw, base) if raw else ''

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath(xp):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name:
                refs.append((actor_name, absolute_url(href, base) if href else ''))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, label='actor')

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        images.push(details_page_elements.xpath('(//span[@id="trailer_thumb"]//img)[1]/@src').get())
        if self._is_dvd(scene):
            for src in details_page_elements.xpath('//div[@class="videoBlock"]//img/@src0_3x').getall():
                images.push(src)

        metadata.art = images.items
