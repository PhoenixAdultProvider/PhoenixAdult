from __future__ import annotations

import math
import re
from datetime import date

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import build_search_result, iso_date, join_url, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_attr

STUDIO = 'PornWorld'
_PER_PAGE = 99
_MAX_CRAWL_PAGES = 15
_ISO_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_SUFFIX_RE = re.compile(r'\s*-\s*PornWorld\s*$', re.IGNORECASE)


def _clean_title(raw: str) -> str:
    return _SUFFIX_RE.sub('', raw).strip()


def _iso_date_obj(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


class PornWorldClient(Client):
    summary_xpath = '(//div[text()="Description:"]/following-sibling::div)[1]'
    genres_xpath = '//div[contains(@class,"genres-list")]//a'

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')

        if search_data.search_date and _ISO_RE.match(search_data.search_date):
            dated = await self._date_crawl(search_data, base)
            if dated:
                results.extend(dated)
                return

        first_word = search_data.scene_id or (search_data.title.strip().split()[0] if search_data.title.strip() else '')
        if first_word.isdigit() and len(first_word) > 3:
            scene_url = f'{base}/watch/{first_word}'
            direct_page_elements = await self.fetch_and_load(
                scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] directScene {scene_url}'
            )
            if direct_page_elements:
                title = _clean_title((direct_page_elements['sel'].xpath('(//title)[1]').xpath('string(.)').get() or '').strip())
                if title:
                    results.append(
                        build_search_result(
                            site=search_data.site_info,
                            title=title,
                            scene_url=scene_url,
                            query=search_data.title,
                            search_date=search_data.search_date,
                            score=100,
                            cur_id=pack_cur_id([scene_url]),
                        )
                    )
                    return

        slug = re.sub(r'\s+', '+', search_data.title.strip())
        search_url = search_data.search_url(slug)
        search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {search_url}')
        if not search_results:
            return

        sel = search_results['sel']

        if not sel.xpath('//h1[contains(@class,"section__title")]'):
            title = _clean_title((sel.xpath('(//title)[1]').xpath('string(.)').get() or '').strip())
            href = first_attr(sel, '(//a[contains(@class,"__pagination_button--more")])[1]/@href')
            if title and href:
                results.append(
                    build_search_result(
                        site=search_data.site_info,
                        title=title,
                        scene_url=join_url(href, base),
                        query=search_data.title,
                        search_date=search_data.search_date,
                        cur_id=pack_cur_id([join_url(href, base)]),
                    )
                )
                return

        for a in sel.xpath('//div[contains(@class,"card-scene")]//div[contains(@class,"card-scene__text")]/a'):
            title = first_attr(a, 'normalize-space(.)')
            href = first_attr(a, '@href')
            if not title or not href:
                continue

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=join_url(href, base),
                    query=search_data.title,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([join_url(href, base)]),
                )
            )

    # ── Search Helpers ────────────────────────────────────────────────────────

    async def _date_crawl(self, search_data: SearchContext, base: str) -> list[SearchResult]:
        assert search_data.search_date is not None
        target = _iso_date_obj(search_data.search_date)
        if target is None:
            return []

        delta_days = max(0, (date.today() - target).days)
        page = max(math.ceil(delta_days / _PER_PAGE), 1)

        for _ in range(_MAX_CRAWL_PAGES):
            url = f'{base}/new-videos/{page}'
            search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] dateCrawl p{page}')
            if not search_results:
                break

            date_els = search_results['sel'].xpath('//div[contains(@class,"card-scene__time")]/div[contains(@class,"label--time")][2]')
            if not date_els:
                break

            first_date = _iso_date_obj(date_els[0].xpath('string(.)').get() or '')
            if first_date and target > first_date and page > 1:
                page -= 1
                continue

            last_date = _iso_date_obj(date_els[-1].xpath('string(.)').get() or '')
            if last_date and target < last_date:
                page += 1
                continue

            results: list[SearchResult] = []
            for search_result in search_results['sel'].xpath('//div[contains(@class,"card-scene")]'):
                title = (search_result.xpath('(.//div[contains(@class,"card-scene__text")]/a)[1]').xpath('string(.)').get() or '').strip()
                href = first_attr(search_result, '(.//a)[1]/@href')
                if not title or not href:
                    continue

                scene_date_text = (search_result.xpath('(.//div[contains(@class,"label--time")])[2]').xpath('string(.)').get() or '').strip()
                scene_date = _iso_date_obj(scene_date_text)
                if scene_date is None:
                    continue

                days_diff = abs((target - scene_date).days)
                if days_diff >= 3:
                    continue

                results.append(
                    build_search_result(
                        site=search_data.site_info,
                        title=title,
                        scene_url=join_url(href, base),
                        query=search_data.title,
                        display_date=scene_date_text,
                        search_date=search_data.search_date,
                        score=100 - days_diff * 10,
                        cur_id=pack_cur_id([x for x in (join_url(href, base), scene_date_text) if x]),
                    )
                )

            return results

        return []

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = (details_page_elements.xpath('(//title)[1]').xpath('string(.)').get() or '').strip()

        metadata.title = _clean_title(raw) if raw else ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (details_page_elements.xpath('(//i[contains(@class,"bi-calendar")])[1]').xpath('string(.)').get() or '').strip()
        if date:
            metadata.release_date = iso_date(date)
            return

        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        entries = [
            ActorResult(name=first_attr(actor_link, 'normalize-space(.)'))
            for actor_link in details_page_elements.xpath('//h1[contains(@class,"watch__title")]//a')
        ]

        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector()
        for image_url in details_page_elements.xpath('//video/@data-poster').getall():
            images.push(image_url)

        metadata.art = images.items
