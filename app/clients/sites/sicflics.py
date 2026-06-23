from __future__ import annotations

import json
import re
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneContext, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_text

STUDIO = 'Sicflics'
_ACTOR_SPLIT_RE = re.compile(r"['?]")


def _actor_from_description(description: str) -> str:
    parts = _ACTOR_SPLIT_RE.split(description)
    return parts[1].strip() if len(parts) > 1 else ''


class SicflicsClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//li[contains(@class,"col-sm-6") and contains(@class,"col-lg-4")]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def build_search_results(self, source: Any, loaded: LoadedSearch) -> list[SearchResult]:
        title = first_text(source, './/div[contains(@class,"vidtitle")]/p[1]')
        img_url = (source.xpath('(.//div[contains(@class,"vidthumb")]//a[contains(@class,"diagrad")]//img/@src)[1]').get() or '').strip()
        scene_id = (source.xpath('(.//a[@data-movie]/@data-movie)[1]').get() or '').strip()
        if not title or not scene_id:
            return []
        desc_raw = first_text(source, './/div[contains(@class,"collapse")]/p')
        description = desc_raw.split(':', 1)[1].strip() if ':' in desc_raw else desc_raw
        raw_date = first_text(source, './/div[contains(@class,"vidtitle")]/p[2]')
        release_date = iso_date(raw_date) if raw_date else None

        base = loaded.site.base_url.rstrip('/')
        packed = json.dumps(
            {
                'sceneID': scene_id,
                'imgURL': img_url if img_url.startswith('http') else absolute_url(img_url, loaded.site.base_url),
                'description': description,
            }
        )
        popup_url = f'{base}/v6/v6.pop.php?id={scene_id}'
        return [
            build_search_result(
                title=title,
                scene_url=popup_url,
                query=loaded.ctx.title,
                display_date=release_date,
                search_date=loaded.ctx.search_date,
                cur_id=pack_cur_id([packed]),
            )
        ]

    # ── Context loader ────────────────────────────────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        try:
            packed = json.loads(payload)
        except (ValueError, TypeError):
            return None
        base = site.base_url.rstrip('/')
        popup_url = f'{base}/v6/v6.pop.php?id={packed.get("sceneID", "")}'
        loaded = await self.fetch_and_load(popup_url, FetchCtx(capture=ctx.capture if ctx else None), f'[{site.name}] popup {popup_url}')
        if not loaded:
            return None
        return LoadedScene(url=popup_url, site=site, capture=ctx.capture if ctx else None, sel=loaded['sel'], html=loaded['html'], extra=packed)

    def _packed(self, scene: LoadedScene) -> dict[str, Any]:
        return scene.extra if isinstance(scene.extra, dict) else {}

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//h4[contains(@class,"red")]')
        return raw.lower() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        return (self._packed(scene).get('description') or '').replace('\n', '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//span[@title="Date Added"]')
        if not raw:
            return None
        tail = raw.split(':', 1)[1].strip() if ':' in raw else raw
        return iso_date(tail) if tail else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [
            (a.xpath('normalize-space(.)').get() or '').replace('#', '') for a in scene.sel.xpath('//div[contains(@class,"vidwrap")]//p//a')
        ]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        name = _actor_from_description(self._packed(scene).get('description') or '')
        return [ActorResult(name=name)] if name else []

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        img = (self._packed(scene).get('imgURL') or '').strip()
        return [img] if img else []
