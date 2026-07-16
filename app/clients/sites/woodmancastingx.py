from __future__ import annotations

import re
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text

STUDIO = 'Woodman Casting X'
_IMAGE_RE = re.compile(r'image:\s*"([^"]+)"')


class WoodmanCastingXClient(Client):
    async def _get_site_data(self, url: str, label: str) -> dict[str, Any] | None:
        first_page_elements = await self.fetch_and_load(url, None, label)
        if not first_page_elements:
            return None

        ids = [i for i in (s.strip() for s in first_page_elements['sel'].xpath('//div[@id]/@id').getall()) if i and i != 'error']
        if not ids:
            return first_page_elements

        cookie = '; '.join(f'{i}=1' for i in ids)
        retried_page_elements = await self.fetch_and_load(url, FetchCtx(headers={'Cookie': cookie}), f'{label} (challenge)')
        return retried_page_elements or first_page_elements

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        search_url = base + search_data.site_info.search_path.replace('{query}', search_data.encoded)
        data = await self._get_site_data(search_url, f'[{search_data.site_info.name}] search "{search_data.title}"')
        if not data:
            return

        seen: set[str] = set()
        for a in data['sel'].xpath('//div[contains(@class,"items")]//a[contains(@class,"scene")]'):
            href = first_attr(a, '@href')
            if not href or href.startswith('http'):
                continue

            raw_title = first_attr(a, '(.//img/@alt)[1]')
            if not raw_title:
                continue

            scene_url = absolute_url(href, search_data.site_info.base_url)
            if scene_url in seen:
                continue

            seen.add(scene_url)

            results.append(
                build_search_result(
                    title=raw_title,
                    scene_url=scene_url,
                    query=search_data.title,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([scene_url, search_data.search_date or '']),
                )
            )

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        url, _, tail = payload.partition('|')
        date = tail.strip()
        data = await self._get_site_data(url, f'[{site.name}] detail {url}')
        if not data:
            return None

        return LoadedScene(url=url, site=site, scene_date=date or None, capture=ctx.capture if ctx else None, sel=data['sel'], html=data['html'])

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//h1') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = first_text(details_page_elements, '//p[contains(@class,"description")]')

        metadata.summary = ' '.join(raw.split()) or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        trailing = first_attr(details_page_elements, '(//span[contains(.,"Published")]/following-sibling::text())[1]')
        date = trailing.lstrip(':').strip()
        if date:
            parsed = iso_date(date)
            if parsed:
                metadata.release_date = parsed
                return

        if scene.scene_date:
            metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            genre_link.xpath('normalize-space(.)').get() for genre_link in details_page_elements.xpath('//div[contains(@class,"tags")]//a')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        blocks = details_page_elements.xpath('//div[contains(@class,"block_girls_videos")]//a[contains(@class,"girl_item")]')
        if blocks:
            actors: list[ActorResult] = []
            seen: set[str] = set()
            for a in blocks:
                actor_name = first_text(a, './/span[contains(@class,"name")]')
                if not actor_name or actor_name in seen:
                    continue

                seen.add(actor_name)
                src = first_attr(a, '(.//img/@src)[1]')
                photo = (absolute_url(src, base)) if src else ''
                actors.append(ActorResult(name=actor_name, photo_url=photo))

            metadata.actors = actors
            return

        crumb = first_text(details_page_elements, '//div[@id="breadcrumb"]//span[contains(@class,"crumb")]')
        actor_name = crumb.split('-')[0].strip()

        metadata.actors = [ActorResult(name=actor_name)] if actor_name else []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        images = self.image_collector(lambda image: absolute_url((image or '').strip(), base))
        for poster in details_page_elements.xpath('//video[contains(@class,"player_video")]/@poster').getall():
            images['push'](poster)

        for script in details_page_elements.xpath('//script/text()').getall():
            if 'var player' not in script:
                continue

            m = _IMAGE_RE.search(script)
            if m:
                images['push'](m.group(1).strip())

        metadata.art = images['list']
