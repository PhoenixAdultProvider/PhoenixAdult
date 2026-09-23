from __future__ import annotations

from typing import Any

from parsel import Selector

from phoenixadult.clients.base import Client, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import SceneDetail, SearchContext
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text, meta_content
from phoenixadult.utils.helpers.text import slugify
from phoenixadult.utils.helpers.urls import join_url

_TRAILER_P_XP = '//div[contains(@class,"trailer") and contains(@class,"topSpace")]//div//p'
_CAST_XP = _TRAILER_P_XP + '//a'


class GirlsOutWestClient(Client):
    candidate_include = ('/trailers/',)
    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def candidate_urls(self, search_data: SearchContext) -> list[str]:
        return [search_data.search_url(slugify(search_data.title))]

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        if source.html.strip() == 'Page not found':
            return ''
        return meta_content(source.sel, 'twitter:title')

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        return self._date_from(source.sel)

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _date_from(self, sel: Any) -> str | None:
        text = first_text(sel, _TRAILER_P_XP)
        parts = text.split('\\')
        if len(parts) < 2:
            return None

        return iso_date(parts[1].strip(), '%m/%d/%Y')

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = meta_content(details_page_elements, 'twitter:title') or ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.release_date = self._date_from(details_page_elements)

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres = ['Amateur', 'Australian']
        count = len(details_page_elements.xpath(_CAST_XP))
        if (group := self.group_genre_for(count)) and group not in genres:
            genres.append(group)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            raw = first_attr(sel, '(//div[contains(@class,"profilePic")]//img/@src0_3x)[1]')
            return join_url(raw, base) if raw else ''

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath(_CAST_XP):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name and href:
                refs.append((actor_name, join_url(href, base)))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture, label=scene.site.name)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: join_url(image, scene.site.base_url))
        for image_url in details_page_elements.xpath('//div[contains(@class,"videoplayer")]//img/@src0_3x').getall():
            image_url = (image_url or '').strip()
            if not image_url:
                continue

            images.push(image_url)

        metadata.art = images.items
