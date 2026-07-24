from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, date_distance_score, iso_date, load_data, title_distance_score
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.searchengines import SearchOptions, web_search, web_search_available, web_search_filtered

STUDIO = 'First Time Videos'

_PHOTO_LOOKUP: dict[str, list[str]] = load_data(__file__, 'ftv_photo_lookup')

_GENRES: dict[str, list[str]] = {
    'FTVGirls': ['Teen', 'Solo', 'Public'],
    'FTVMilfs': ['MILF', 'Solo', 'Public'],
}

_POSTER_RULES: list[str] = [
    '//img[@id="Magazine"]/@src',
    '//div[contains(@class,"gallery")]//div[contains(@class,"row")]//*[@href]/@href',
    '//div[contains(@class,"thumbs_horizontal")]//*[@href]/@href',
    '//a[.//img[contains(@class,"t")]]/@href',
]
_SCENE_ID_RE = re.compile(r'-(\d+)\.')


def _photo_lookup(scene_id: int) -> list[str]:
    return _PHOTO_LOOKUP.get(str(scene_id), ['none'])


def _parse_title_and_date(sel: Any) -> tuple[str, str | None]:
    raw = sel.xpath('(//title)[1]').xpath('string(.)').get() or ''
    segments = raw.split('Released')
    title = segments[0].strip()
    date_raw = segments[-1].replace('!', '').strip()
    return title, (iso_date(date_raw) if date_raw else None)


def _collect_images(sel: Any) -> list[str]:
    out: list[str] = []
    for xp in _POSTER_RULES:
        out.extend(v for v in sel.xpath(xp).getall() if v)

    return out


__testing__ = {'photo_lookup': _photo_lookup, 'parse_title_and_date': _parse_title_and_date}


class FTVClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        host = urlsplit(search_data.site_info.base_url).netloc.removeprefix('www.')
        candidates: list[str] = []
        if search_data.scene_id:
            candidates.append(f'{base}{search_data.site_info.search_path}{search_data.scene_id}.html')

        if web_search_available():
            try:
                for url in await web_search_filtered(SearchOptions(query=search_data.title, site=host, num=10), url_contains='/update/'):
                    if url not in candidates:
                        candidates.append(url)
            except Exception as err:  # noqa: BLE001 - best-effort
                logger.debug(search_data.site_info.name, f'webSearch: {err}')

        for scene_url in candidates:
            details_page_elements = await self.fetch_and_load(
                scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] candidate {scene_url}'
            )
            if not details_page_elements:
                continue

            title, date_iso = _parse_title_and_date(details_page_elements['sel'])
            if not title:
                continue

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

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _cast_base_names(self, scene: LoadedScene) -> list[str]:
        details_page_elements = scene.require_sel()

        names = []
        for row in details_page_elements.xpath('//div[@id="ModelDescription"]//h1'):
            n = (row.xpath('string(.)').get() or '').replace("'s Statistics", '').strip()
            if n:
                names.append(n)

        return names

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = _parse_title_and_date(details_page_elements)[0] or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = (details_page_elements.xpath('(//div[@id="Bio"])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.release_date = _parse_title_and_date(details_page_elements)[1] or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.genres = _GENRES.get(scene.site.name) or []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        summary = (details_page_elements.xpath('(//div[@id="Bio"])[1]').xpath('string(.)').get() or '').strip()
        thumbs = details_page_elements.xpath('//div[@id="Thumbs"]//img/@src').getall()
        actors: list[ActorResult] = []
        for idx, row in enumerate(details_page_elements.xpath('//div[@id="ModelDescription"]//h1')):
            base_name = (row.xpath('string(.)').get() or '').replace("'s Statistics", '').strip()
            if not base_name:
                continue

            actor_name = base_name
            m = re.search(rf'\s({re.escape(base_name)} [A-Z]\w+)\s', summary)
            if m:
                actor_name = m.group(1)

            photo_raw = thumbs[idx] if idx < len(thumbs) else ''
            actors.append(ActorResult(name=actor_name, photo_url=absolute_url(photo_raw, base) if photo_raw else ''))

        metadata.actors = actors or []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        images = self.image_collector(lambda image: absolute_url(image, base))

        m = _SCENE_ID_RE.search(scene.url)
        scene_id = int(m.group(1)) if m else 0
        slugs = _photo_lookup(scene_id)
        cast_query = ' '.join(self._cast_base_names(scene)).strip()
        if cast_query and web_search_available():
            host = urlsplit(base).netloc.removeprefix('www.')
            try:
                gallery_results = await web_search(SearchOptions(query=cast_query, site=host, num=10))
            except Exception as err:  # noqa: BLE001 - best-effort
                logger.debug(scene.site.name, f'webSearch: {err}')
                gallery_results = []

            for photo_url in gallery_results:
                is_gallery = 'galleries' in photo_url or 'preview' in photo_url
                slug_match = any(s == 'none' or s in photo_url for s in slugs)
                if not is_gallery or not slug_match:
                    continue

                gallery_page_elements = await self.fetch_and_load(photo_url, None, f'GET {photo_url} (gallery)')
                if gallery_page_elements:
                    for raw in _collect_images(gallery_page_elements['sel']):
                        images['push'](raw)

        for raw in _collect_images(details_page_elements):
            images['push'](raw)

        metadata.art = images['list'] or []
