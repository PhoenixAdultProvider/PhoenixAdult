from __future__ import annotations

from typing import Any
from urllib.parse import quote

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, iso_date, join_url, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_attr

STUDIO = 'Jules Jordan'


def _desc_row(sel: Any, label: str) -> str:
    return (sel.xpath(f'(//div[contains(@class,"player-scene-description")]//span[contains(text(),"{label}")]/..)[1]').xpath('string(.)').get() or '').strip()


class JulesJordanClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        seen: set[str] = set()

        direct_url = f'{base}/trial/scenes/{"-".join(search_data.title.lower().split())}_vids.html'
        direct_page_elements = await self.fetch_and_load(
            direct_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] directScene {direct_url}'
        )
        if direct_page_elements:
            seen.add(direct_url)

            results.append(
                build_search_result(
                    title=search_data.title,
                    scene_url=direct_url,
                    query=search_data.title,
                    search_date=search_data.search_date,
                    score=100,
                    cur_id=pack_cur_id([x for x in (direct_url, search_data.search_date) if x]),
                )
            )

        search_url = base + search_data.site_info.search_path.replace('{query}', search_data.encoded)
        search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {search_url}')
        if search_results:
            for search_result in search_results['sel'].xpath('//div[contains(@class,"grid-item")]'):
                a = search_result.xpath('(.//a)[1]')
                href = first_attr(a, '@href')
                title = first_attr(a, '(.//img)[1]/@alt')
                if not href or not title:
                    continue

                scene_url = absolute_url(href, search_data.site_info.base_url)
                if scene_url in seen:
                    continue

                seen.add(scene_url)

                results.append(
                    build_search_result(
                        title=title,
                        scene_url=scene_url,
                        query=search_data.title,
                        search_date=search_data.search_date,
                        cur_id=pack_cur_id([x for x in (scene_url, search_data.search_date) if x]),
                    )
                )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = (details_page_elements.xpath('(//div[contains(@class,"movie_title")])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = _desc_row(details_page_elements, 'Description:').replace('Description:', '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.tagline = _desc_row(details_page_elements, 'Movie:').replace('Movie:', '').replace('Feature: ', '').strip() or None

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [STUDIO]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        if scene.scene_date:
            metadata.release_date = scene.scene_date
            return

        date = _desc_row(details_page_elements, 'Date:').replace('Date:', '').strip()

        metadata.release_date = iso_date(date) if date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres: list[str] = []
        for genre_link in details_page_elements.xpath('//span[contains(text(),"Categories")]//a'):
            genre_name = first_attr(genre_link, 'normalize-space(.)').lower()
            if genre_name and genre_name not in genres:
                genres.append(genre_name)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        if scene.site.name == 'GirlGirl':
            anchors = details_page_elements.xpath('//div[contains(@class,"item")]//span//div//a')
        else:
            anchors = details_page_elements.xpath('//div[contains(@class,"player-scene-description")]//span[contains(text(),"Starring:")]/..//a')

        actors: list[ActorResult] = []
        seen: set[str] = set()
        for row in anchors:
            actor_name = first_attr(row, 'normalize-space(.)')
            if not actor_name or actor_name in seen:
                continue

            seen.add(actor_name)
            photo = ''
            href = first_attr(row, '@href')
            if href:
                actor_url = absolute_url(href, base)
                model_page_elements = await self.fetch_and_load(actor_url, None, f'GET {actor_url} (actor)')
                raw = first_attr(model_page_elements['sel'], '(//img[contains(@class,"model_bio_thumb")])[1]/@src0_3x') if model_page_elements else ''
                if raw:
                    photo = absolute_url(raw, base)

            actors.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')
        images = self.image_collector(lambda image: join_url(image, base))

        images['push'](first_attr(details_page_elements, '(//video[@id="video-player"])[1]/@poster'))

        title = (details_page_elements.xpath('(//div[contains(@class,"movie_title")])[1]').xpath('string(.)').get() or '').strip()
        if title:
            search_url = base + scene.site.search_path.replace('{query}', quote(title))
            search_page_elements = await self.fetch_and_load(search_url, None, f'GET {search_url} (slideshow)')
            if search_page_elements:
                img = search_page_elements['sel'].xpath('(//img[contains(@id,"set-target")])[1]')
                for i in range(7):
                    images['push']((img.xpath(f'@src{i}_1x').get() or '').strip())

        metadata.art = images['list']
