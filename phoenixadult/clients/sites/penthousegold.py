from __future__ import annotations

import re

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.helpers.urls import absolute_url

_H1_XP = '//div[contains(@class,"content-desc") and contains(@class,"content-new-scene")]//h1'
_UPLOAD_XP = '(//meta[@itemprop="uploadDate"]/@content)[1]'
_PREFIX_RE = re.compile(r'^(Video|Movie)\s*-\s*')


class PenthouseGoldClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        seen: set[str] = set()

        search_url = search_data.search_url()
        search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {search_url}')
        if search_results:
            for search_result in search_results['sel'].xpath('//div[contains(@class,"scene")]'):
                anchor = search_result.xpath('(.//a[@data-track="TITLE_LINK"])[1]')
                href = first_attr(anchor, '@href')
                if '/scenes/' not in href:
                    continue

                title = first_attr(anchor, 'normalize-space(.)')
                if not title:
                    continue

                scene_url = absolute_url(href, search_data.site_info.base_url)
                if scene_url in seen:
                    continue

                seen.add(scene_url)
                date = iso_date(first_text(search_result, './/span[contains(@class,"scene-date")]'))

                results.append(
                    build_search_result(
                        site=search_data.site_info,
                        title=title,
                        scene_url=scene_url,
                        query=search_data.title,
                        display_date=date,
                        search_date=search_data.search_date,
                        cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
                    )
                )

        slug = re.sub(r'\s+', '-', search_data.title.strip())
        for kind in ('video', 'movie'):
            scene_url = f'{base}/scenes/{kind}---{slug}_vids.html'
            if scene_url in seen:
                continue

            guess_page_elements = await self.fetch_and_load(
                scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] guess {scene_url}'
            )
            title = first_text(guess_page_elements['sel'], _H1_XP) if guess_page_elements else ''
            if not title:
                continue

            seen.add(scene_url)
            raw_date = (guess_page_elements['sel'].xpath(_UPLOAD_XP).get() or '').strip() if guess_page_elements else ''
            date = iso_date(raw_date, '%m/%d/%Y') if raw_date else None

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=date,
                    search_date=search_data.search_date,
                    score=100,
                    cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
                )
            )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = _PREFIX_RE.sub('', first_text(details_page_elements, _H1_XP)).strip()

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//div[contains(@class,"content-desc") and contains(@class,"content-new-scene")]//p')

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (details_page_elements.xpath(_UPLOAD_XP).get() or '').strip()

        metadata.release_date = (iso_date(date, '%m/%d/%Y') if date else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            first_attr(genre_link, 'normalize-space(.)').lower() for genre_link in details_page_elements.xpath('//ul[contains(@class,"scene-tags")]//li//a')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        entries: list[ActorResult] = []
        for card in details_page_elements.xpath('//ul[@id="featured_pornstars"]//div[contains(@class,"model")]'):
            actor_name = first_text(card, './/h3')
            raw = first_attr(card, '(.//img/@src)[1]')
            photo = (absolute_url(raw, scene.site.base_url)) if raw else ''
            entries.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = first_attr(details_page_elements, '(//div[@id="trailer_player_finished"]//img/@src)[1]')
        if not raw:
            return

        metadata.art = [absolute_url(raw, scene.site.base_url)]
