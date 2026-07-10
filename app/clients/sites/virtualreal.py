from __future__ import annotations

import json
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import append_unique, build_search_result, iso_date, pack_cur_id
from app.utils.logging.logger import logger


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
    assert scene.sel is not None
    return _ld_from_sel(scene.sel)


def _strip_suffix(name: str | None) -> str:
    return (name or '').split('|')[0].strip()


class VirtualRealClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        slug = ctx.title.lower().replace(' ', '-')
        if not slug:
            return []
        search_url = f'{base}{ctx.site_info.search_path}{slug}'
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] direct {search_url}')
        if not loaded:
            return []
        ld = _ld_from_sel(loaded['sel'])
        if not ld:
            return []
        title = _strip_suffix(ld.get('name'))
        if not title:
            return []
        scene_url = (ld.get('url') or '').strip() or search_url
        date = iso_date(ld['datePublished']) if ld.get('datePublished') else None
        logger.info(ctx.site_info.name, f'VirtualReal direct hit "{title}" ({scene_url})')
        return [
            build_search_result(
                title=title, scene_url=scene_url, query=ctx.title, display_date=date, search_date=ctx.search_date, cur_id=pack_cur_id([scene_url, date or ''])
            )
        ]

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        ld = _last_json_ld(scene)
        return _strip_suffix(ld.get('name') if ld else None) or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        ld = _last_json_ld(scene)
        return ((ld.get('description') if ld else '') or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        ld = _last_json_ld(scene)
        if ld and ld.get('datePublished'):
            parsed = iso_date(ld['datePublished'])
            if parsed:
                return parsed
        if scene.scene_date:
            return iso_date(scene.scene_date) or scene.scene_date
        return None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        ld = _last_json_ld(scene)
        keywords = (ld.get('keywords') if ld else '') or ''
        parts: list[str | None] = list(keywords.split(','))
        return self.dedup_strings(parts)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        ld = _last_json_ld(scene)
        names = [(a.get('name') or '').strip() for a in (ld.get('actors') if ld else None) or [] if (a.get('name') or '').strip()]
        photos = [(src or '').strip() for src in scene.sel.xpath('//div[contains(@class,"model-box")]//a//img/@src').getall()]
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for idx, name in enumerate(names):
            if name in seen:
                continue
            seen.add(name)
            actors.append(ActorResult(name=name, photo_url=photos[idx] if idx < len(photos) else ''))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        ld = _last_json_ld(scene)
        images: list[str] = []

        def push(raw: str) -> None:
            append_unique(images, raw, base)

        push((ld.get('image') if ld else '') or '')
        for href in scene.sel.xpath('//figure[@itemprop="associatedMedia"]//a/@href').getall():
            push(href)
        return images
