from __future__ import annotations

import json
from typing import Any

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import append_unique, build_search_result, iso_date, pack_cur_id
from phoenixadult.utils.logging.logger import logger


def _ld_from_sel(sel: Any) -> dict[str, Any] | None:
    scripts = sel.xpath('//script[@type="application/ld+json"]/text()').getall()
    if not scripts:
        return None

    try:
        data = json.loads(scripts[-1])
    except (ValueError, TypeError):
        return None

    return data if isinstance(data, dict) else None


def _last_json_ld(scene: LoadedScene) -> dict[str, Any] | None:
    details_page_elements = scene.require_sel()

    return _ld_from_sel(details_page_elements)


def _strip_suffix(name: str | None) -> str:
    return (name or '').split('|')[0].strip()


class VirtualRealClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        slug = search_data.title.lower().replace(' ', '-')
        if not slug:
            return

        search_url = f'{base}{search_data.site_info.search_path}{slug}'
        search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] direct {search_url}')
        if not search_results:
            return

        ld = _ld_from_sel(search_results['sel'])
        if not ld:
            return

        title = _strip_suffix(ld.get('name'))
        if not title:
            return

        scene_url = (ld.get('url') or '').strip() or search_url
        date = iso_date(ld['datePublished']) if ld.get('datePublished') else None
        logger.info(search_data.site_info.name, f'VirtualReal direct hit "{title}" ({scene_url})')

        results.append(
            build_search_result(
                site=search_data.site_info,
                title=title,
                scene_url=scene_url,
                query=search_data.title,
                display_date=date,
                search_date=search_data.search_date,
                cur_id=pack_cur_id([scene_url, date or '']),
            )
        )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        ld = _last_json_ld(scene)

        metadata.title = _strip_suffix(ld.get('name') if ld else None) or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        ld = _last_json_ld(scene)

        metadata.summary = ((ld.get('description') if ld else '') or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name or ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        ld = _last_json_ld(scene)
        if ld and ld.get('datePublished'):
            parsed = iso_date(ld['datePublished'])
            if parsed:
                metadata.release_date = parsed
                return

        if scene.scene_date:
            metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        ld = _last_json_ld(scene)
        keywords = (ld.get('keywords') if ld else '') or ''
        parts: list[str | None] = list(keywords.split(','))

        metadata.genres = self.dedup_strings(parts)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        ld = _last_json_ld(scene)
        names = [(a.get('name') or '').strip() for a in (ld.get('actors') if ld else None) or [] if (a.get('name') or '').strip()]
        photos = [(src or '').strip() for src in details_page_elements.xpath('//div[contains(@class,"model-box")]//a//img/@src').getall()]
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for idx, actor_name in enumerate(names):
            if actor_name in seen:
                continue

            seen.add(actor_name)
            actors.append(ActorResult(name=actor_name, photo_url=photos[idx] if idx < len(photos) else ''))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        ld = _last_json_ld(scene)
        images: list[str] = []

        def push(raw: str) -> None:
            append_unique(images, raw, base)

        push((ld.get('image') if ld else '') or '')
        for href in details_page_elements.xpath('//figure[@itemprop="associatedMedia"]//a/@href').getall():
            push(href)

        metadata.art = images
