from __future__ import annotations

import re
from urllib.parse import quote

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text, meta_content

UMBRELLA_STUDIO = 'Dorcel Vision'
_YEAR_RE = re.compile(r'\d{4}')
_STUDIO_OVERRIDE_XP = '//div[contains(@class,"entries")]//strong[contains(.,"Studio")]/following-sibling::a[1]'


def _page_studio_override(scene: LoadedScene) -> str:
    details_page_elements = scene.require_sel()

    return first_text(details_page_elements, _STUDIO_OVERRIDE_XP)


class DorcelVisionClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        url = base + search_data.site_info.search_path.replace('{query}', quote(search_data.title))
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"')
        if not search_results:
            return

        for search_result in search_results['sel'].xpath('//a[contains(@class,"movies")]'):
            title = first_attr(search_result, '(.//img/@alt)[1]')
            href = first_attr(search_result, '@href')
            if not title or not href:
                continue

            scene_url = absolute_url(href, search_data.site_info.base_url)

            results.append(
                build_search_result(
                    title=title, scene_url=scene_url, query=search_data.title, search_date=search_data.search_date, cur_id=pack_cur_id([scene_url])
                )
            )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//h1') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        meta = meta_content(details_page_elements, 'twitter:description')

        metadata.summary = meta or first_text(details_page_elements, '//div[@id="summaryList"]') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = _page_studio_override(scene) or UMBRELLA_STUDIO

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        override = _page_studio_override(scene)

        metadata.collections = [UMBRELLA_STUDIO, override] if override else [UMBRELLA_STUDIO]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        year_entries = details_page_elements.xpath('//div[contains(@class,"entries")]//strong[contains(.,"Production year")]')
        if not year_entries:
            return

        text = ''.join(year_entries[0].xpath('following-sibling::text()').getall())
        m = _YEAR_RE.search(text)

        metadata.release_date = f'{m.group(0)}-01-01' if m else None

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        actors: list[ActorResult] = []
        seen: set[str] = set()
        for card in details_page_elements.xpath('//div[contains(@class,"casting")]//div[contains(@class,"slider-xl")]//div[contains(@class,"col-xs-2")]'):
            actor_name = first_text(card, './/a/strong')
            if not actor_name or actor_name in seen:
                continue

            seen.add(actor_name)
            photo_raw = first_attr(card, '(.//img/@data-src)[1]')
            photo = absolute_url(photo_raw, scene.site.base_url) if photo_raw else ''
            actors.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')
        images = self.image_collector(lambda image: absolute_url((image or '').strip().replace('blur9/', ''), base))

        for href in details_page_elements.xpath('//div[contains(@class,"covers")]//a[contains(@class,"cover")]/@href').getall():
            images['push'](href)

        for href in details_page_elements.xpath(
            '//div[contains(@class,"screenshots")]//div[contains(@class,"slider-xl")]//div[contains(@class,"col-xs-2")]//a/@href'
        ).getall():
            images['push'](href)

        metadata.art = images['list']
