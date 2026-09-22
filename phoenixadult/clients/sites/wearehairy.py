from __future__ import annotations

from typing import Any

from phoenixadult.clients.base import Client, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import ActorResult, SceneDetail
from phoenixadult.utils.helpers.helpers import iso_date, to_https
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text

_FIXED_GENRES: list[str] = ['Hairy Girls', 'Hairy Pussy']


class WeAreHairyClient(Client):
    search_url_xpath = '(.//div[contains(@class,"top")]//p//a/@href)[1]'
    search_rows_xpath = '//div[contains(@class,"results")]//ul//li'
    title_xpath = '//title'
    summary_xpath = '//div[contains(@class,"desc")]/div[1]//p'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/p[contains(@class,"title")]//a')

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = first_text(source, './/p[contains(@class,"short")]').replace('Added:', '').strip()
        return iso_date(raw) if raw else None

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, '//span[contains(@class,"added")]//time')
        if date:
            parsed = iso_date(date, '%b %d, %Y') or iso_date(date)
            if parsed:
                metadata.release_date = parsed
                return

        if scene.scene_date:
            metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres = self.dedup_strings(
            [first_attr(genre_link, 'normalize-space(.)') for genre_link in details_page_elements.xpath('//div[contains(@class,"tagline")]//p//a')]
        )
        for genre_name in _FIXED_GENRES:
            if genre_name not in genres:
                genres.append(genre_name)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        actors: list[ActorResult] = []
        seen: set[str] = set()
        for alt in details_page_elements.xpath('//div[contains(@class,"meet")]//a//img/@alt').getall():
            actor_name = (alt or '').replace('WeAreHairy.com', '').strip()
            if not actor_name or actor_name in seen:
                continue

            seen.add(actor_name)
            actors.append(ActorResult(name=actor_name))

        metadata.actors = actors

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        entries = [
            ActorResult(name=(p.xpath('normalize-space(.)').get() or '')) for p in details_page_elements.xpath('//div[contains(@class,"desc")]/div[2]//p')
        ]
        directors = self.dedup_people(entries)

        metadata.directors = directors or None

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: to_https((image or '').strip()))
        for src in details_page_elements.xpath('//div[contains(@class,"moviemain")]/div[1]//a//img/@src').getall():
            images.push(src)

        metadata.art = images.items
