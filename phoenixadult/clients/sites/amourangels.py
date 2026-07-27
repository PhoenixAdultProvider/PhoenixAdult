from __future__ import annotations

import re

from parsel import Selector

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text

_TITLE_XP = '//td[contains(@class,"blox-bg")]//td[2]//b'
_DATE_CELL_XP = '//td[contains(@class,"blox-bg")]//td[2]'
_VIDEO_PREFIX = re.compile(r'^Video\s*', re.IGNORECASE)


def _strip_video_label(s: str) -> str:
    return _VIDEO_PREFIX.sub('', s).strip()


class AmourAngelsClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        scene_url = base + search_data.site_info.search_path.replace('{query}', search_data.title.strip())
        direct_page_elements = await self.fetch_and_load(
            scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] directScene {scene_url}'
        )
        if not direct_page_elements:
            return

        title = _strip_video_label(first_text(direct_page_elements['sel'], _TITLE_XP))
        if not title:
            return

        results.append(
            build_search_result(
                site=search_data.site_info,
                title=title,
                scene_url=scene_url,
                query=search_data.title,
                search_date=search_data.search_date,
                score=100,
                search_url=scene_url,
                cur_id=pack_cur_id([scene_url]),
            )
        )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = _strip_video_label(first_text(details_page_elements, _TITLE_XP))

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        cell_text = first_text(details_page_elements, _DATE_CELL_XP)
        parts = cell_text.split('Added')
        if len(parts) < 2:
            return

        candidate = parts[1].strip()[:10]

        metadata.release_date = iso_date(candidate, '%Y-%m-%d') or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.genres = ['Softcore', 'European Girls']

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            raw = (
                sel.xpath('(//td[contains(@class,"modelinfo-bg")]//td[1]//img/@src)[1]').get()
                or sel.xpath('(//td[contains(@class,"modelinfo-bg")]//img/@src)[1]').get()
                or ''
            )
            return absolute_url(raw, base) if raw else ''

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('//td[contains(@class,"modinfo")]//a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name and href:
                refs.append((actor_name.lower(), absolute_url(href, base)))

        resolved = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture, label=scene.site.name)
        metadata.actors = [ActorResult(name=a.name, photo_url=a.photo_url, gender='female') for a in resolved]

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        for row in details_page_elements.xpath('//td[contains(@class,"noisebg")]//div//img'):
            images['push'](first_attr(row, '@src'))

        metadata.art = images['list']
