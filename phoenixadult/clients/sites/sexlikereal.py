from __future__ import annotations

from typing import Any

from parsel import Selector

from phoenixadult.clients.base import Client, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import SceneDetail, SearchContext
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text, meta_content
from phoenixadult.utils.helpers.urls import absolute_url

_STUDIO_CLASS = '_euacs6n160'
_SUMMARY_CLASS = '_s1jg1wcd75'
_DATE_CLASS = '_38471wcd31'
_GENRE_CLASS = '_1xdu1wcd88'
_ACTOR_CLASS = '_n7wm1ua719'
_ACTOR_AVATAR_CLASS = '_z763mqyu24 avatar avatar-size-32 outlined'
_COVER_CLASS = '_30hk1wta22'
_STUDIO_XP = f'//a[contains(@class,"{_STUDIO_CLASS}")]'


def _slug(title: str) -> str:
    return '-'.join(title.strip().lower().split())


class SexLikeRealClient(Client):
    candidate_include = ('/scenes/',)
    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def candidate_urls(self, search_data: SearchContext) -> list[str]:
        return [search_data.search_url(_slug(search_data.title))]

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source.sel, '//h1')

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = first_attr(source.sel, '(//time/@datetime)[1]')
        return iso_date(raw) if raw else None

    async def fetch_search_score(self, source: Any, loaded: LoadedSearch) -> float | None:
        return 100 if source.url == loaded.ctx.search_url(_slug(loaded.ctx.title)) else None

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//h1')

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        parts: list[str] = []
        for p in details_page_elements.xpath(f'//p[contains(@class,"{_SUMMARY_CLASS}")]'):
            t = first_attr(p, 'normalize-space(.)')
            if t and 'Video specifications' not in t:
                parts.append(t)

        metadata.summary = '\n'.join(parts)

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.studio = first_text(details_page_elements, _STUDIO_XP)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        studio = first_text(details_page_elements, _STUDIO_XP)

        metadata.collections = [studio] if studio else None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (details_page_elements.xpath(f'(//p[contains(@class,"{_DATE_CLASS}")]//time/@datetime)[1]').get() or '').strip()

        metadata.release_date = iso_date(date) if date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [s.xpath('normalize-space(.)').get() for s in details_page_elements.xpath(f'//a[contains(@class,"{_GENRE_CLASS}")]//span')]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            src = (sel.xpath(f'(//div[contains(@class,"{_ACTOR_AVATAR_CLASS}")]//img/@src)[1]').get() or '').strip()
            return absolute_url(src, base) if src else ''

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath(f'//a[contains(@class,"{_ACTOR_CLASS}")]'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name and href:
                refs.append((actor_name, absolute_url(href, base)))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture, label=scene.site.name)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: (image or '').strip().replace('.webp', '.jpg'))
        images.push(meta_content(details_page_elements, 'og:image', 'property'))
        for image_url in details_page_elements.xpath(f'//img[contains(@class,"{_COVER_CLASS}")]/@src').getall():
            images.push(image_url)

        metadata.art = images.items
