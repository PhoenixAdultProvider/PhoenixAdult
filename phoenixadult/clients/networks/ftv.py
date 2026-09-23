from __future__ import annotations

import re
from typing import Any

from phoenixadult.clients.base import Client, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext
from phoenixadult.utils.helpers.data_files import load_data
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import web_search_urls
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.scoring import date_distance_score, title_distance_score
from phoenixadult.utils.helpers.urls import absolute_url
from phoenixadult.utils.logging.logger import logger

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
    candidate_include = ('/update/',)
    summary_xpath = '(//div[@id="Bio"])[1]'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def candidate_urls(self, search_data: SearchContext) -> list[str]:
        if not search_data.scene_id:
            return []
        return [f'{search_data.site_info.base_url.rstrip("/")}{search_data.site_info.search_path}{search_data.scene_id}.html']

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return _parse_title_and_date(source.sel)[0]

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        return _parse_title_and_date(source.sel)[1]

    async def fetch_search_score(self, source: Any, loaded: LoadedSearch) -> float | None:
        title, date_iso = _parse_title_and_date(source.sel)
        if loaded.ctx.search_date and date_iso:
            return date_distance_score(loaded.ctx.search_date, date_iso)
        return title_distance_score(loaded.ctx.title, title)

    def search_cur_id(self, scene_url: str, date: str | None, loaded: LoadedSearch) -> str:
        return pack_cur_id([p for p in (scene_url, date or loaded.ctx.search_date) if p])

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

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

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

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        images = self.image_collector(lambda image: absolute_url(image, base))

        m = _SCENE_ID_RE.search(scene.url)
        scene_id = int(m.group(1)) if m else 0
        slugs = _photo_lookup(scene_id)
        cast_query = ' '.join(self._cast_base_names(scene)).strip()
        if cast_query:
            try:
                gallery_results = await web_search_urls(cast_query, scene.site)
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
                        images.push(raw)

        for raw in _collect_images(details_page_elements):
            images.push(raw)

        metadata.art = images.items
