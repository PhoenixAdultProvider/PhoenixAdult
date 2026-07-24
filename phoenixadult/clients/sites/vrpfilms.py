from __future__ import annotations

import re

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import append_unique, build_search_result, iso_date, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text
from phoenixadult.utils.logging.logger import logger

_HERO_TITLE_XP = '//section[contains(@class,"login-banner") and contains(@class,"parallax")]//h1'
_URL_RE = re.compile(r"""url\(['"]?([^'")]+)['"]?\)""")


def _slugify(title: str) -> str:
    return title.lower().replace(' ', '-').replace('_', ' ')


def _url_from_style(style: str) -> str:
    m = _URL_RE.search(style or '')
    return m.group(1) if m else ''


class VRPFilmsClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        slug = _slugify(search_data.title)
        if not slug:
            return

        base = search_data.site_info.base_url.rstrip('/')
        scene_url = f'{base}{search_data.site_info.search_path}{slug}'
        search_results = await self.fetch_and_load(scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] direct {scene_url}')
        if not search_results:
            return

        raw = first_text(search_results['sel'], _HERO_TITLE_XP)
        if not raw:
            return

        logger.info(search_data.site_info.name, f'VRPFilms direct hit "{raw}" ({scene_url})')

        results.append(
            build_search_result(
                title=raw,
                scene_url=scene_url,
                query=search_data.title,
                search_date=search_data.search_date,
                cur_id=pack_cur_id([scene_url, search_data.search_date or '']),
            )
        )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, _HERO_TITLE_XP) or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//div[contains(@class,"col-md-8") and contains(@class,"text-justify")]') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        if not scene.scene_date:
            return

        metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = first_text(details_page_elements, '//div[contains(@class,"single__download") and contains(@class,"tags")]')
        parts: list[str | None] = list(raw.split(','))

        metadata.genres = self.dedup_strings(parts)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        entries: list[ActorResult] = []
        for actor_link in details_page_elements.xpath('//a[contains(@class,"starring_contain")]'):
            actor_name = first_text(actor_link, './/div[contains(@class,"col-xs-12") and contains(@class,"video-star-title")]//h3')
            style = first_attr(actor_link, '(.//div[contains(@class,"starring_image")]/@style)[1]')
            entries.append(ActorResult(name=actor_name, photo_url=_url_from_style(style)))

        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        images: list[str] = []

        def push(raw: str) -> None:
            append_unique(images, raw, base)

        bg_style = first_attr(details_page_elements, '(//section[contains(@class,"login-banner") and contains(@class,"parallax")]/@style)[1]')
        push(_url_from_style(bg_style))
        for href in details_page_elements.xpath(
            '//div[contains(@class,"col-md-12") and contains(@class,"gallery-body")]//div//div//div//a[@href]/@href'
        ).getall():
            push(href)

        metadata.art = images
