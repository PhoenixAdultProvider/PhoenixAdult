from __future__ import annotations

import re

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, web_search_urls
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.helpers.urls import strip_query

STUDIO = 'Caramel Cash'

_DDMMYYYY_RE = re.compile(r'^\d{1,2}\.\d{1,2}\.\d{4}$')
_ORDINAL_RE = re.compile(r'(\d)(st|nd|rd|th)', re.IGNORECASE)


def _parse_caramel_date(raw: str) -> str | None:
    cleaned = raw.strip()
    if not cleaned:
        return None

    if _DDMMYYYY_RE.match(cleaned):
        return iso_date(cleaned, '%d.%m.%Y')

    no_prefix = cleaned.split(':')[-1].strip() if ':' in cleaned else cleaned
    no_ordinal = _ORDINAL_RE.sub(r'\1', no_prefix).strip()
    return iso_date(no_ordinal, '%d %b %Y') or iso_date(no_ordinal)


__testing__ = {'parse_caramel_date': _parse_caramel_date}


class CaramelCashClient(Client):
    title_xpath = '(//div[contains(@class,"content-title")])[1]'
    summary_xpath = '(//div[contains(@class,"content-desc")])[2]'

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        candidates: list[str] = []
        if search_data.scene_id:
            candidates.append(search_data.search_url(search_data.scene_id))

        for u in await web_search_urls(search_data.title, search_data.site_info, include=['video/', 'videos/'], exclude=['/page/']):
            clean = strip_query(u)
            if clean not in candidates:
                candidates.append(clean)

        for scene_url, details_page_elements in await self.fetch_candidate_pages(
            candidates, FetchCtx(capture=search_data.capture), lambda scene_url: f'[{search_data.site_info.name}] candidate {scene_url}'
        ):
            if not details_page_elements:
                continue

            raw_title = (details_page_elements['sel'].xpath('(//h1)[1]').xpath('string(.)').get() or '').strip()
            if not raw_title:
                continue

            raw_date = (details_page_elements['sel'].xpath('(//div[contains(@class,"content-date")])[1]').xpath('string(.)').get() or '').strip()
            date = _parse_caramel_date(raw_date) if raw_date else search_data.search_date

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=raw_title,
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=date,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
                )
            )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (details_page_elements.xpath('(//div[contains(@class,"content-date")])[1]').xpath('string(.)').get() or '').strip()
        if date:
            metadata.release_date = _parse_caramel_date(date)
            return

        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            genre_link.xpath('string(.)').get() or '' for genre_link in details_page_elements.xpath('//div[contains(@class,"content-tags")]//a')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        entries = [
            ActorResult(name=first_attr(actor_link))
            for actor_link in details_page_elements.xpath(
                '//section[contains(@class,"content-sec") and contains(@class,"backdrop")]//div[contains(@class,"main__models")]//a'
            )
        ]

        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector()
        for href in details_page_elements.xpath('//section[contains(@class,"content-gallery-sec")]//a[@data-lightbox="gallery"]/@href').getall():
            images.push(href)

        metadata.art = images.items
