from __future__ import annotations

import json
from typing import Any

from parsel import Selector

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.processors.similarity import compare_string


def _parse_ld(sel: Selector) -> dict[str, Any] | None:
    text = (sel.xpath('(//script[@type="application/ld+json"])[1]/text()').get() or '').strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except (ValueError, TypeError):
        return None


class POVRClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        scene_url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {scene_url}')
        if not loaded:
            return []

        results: list[SearchResult] = []
        for card in loaded['sel'].xpath('//div[contains(@class,"thumbnail-wrap")]/div'):
            title = (card.xpath('normalize-space((.//h6[contains(@class,"thumbnail__title")])[1])').get() or '').strip()
            href = (card.xpath('(.//a[contains(@class,"thumbnail__link")]/@href)[1]').get() or '').strip()
            if not title or not href:
                continue
            url = href if href.startswith('http') else absolute_url(href, ctx.site_info.base_url)
            sub_site = (card.xpath('normalize-space((.//a[contains(@class,"thumbnail__footer-link")])[1])').get() or '').strip()

            site_dist = compare_string(sub_site.lower().replace('originals', ''), ctx.site_info.name.lower()).levenshtein
            title_dist = compare_string(ctx.title.lower(), title.lower()).levenshtein
            score = 60 - (site_dist * 6) // 10 + (40 - (title_dist * 4) // 10)

            results.append(
                build_search_result(
                    title=title,
                    scene_url=url,
                    query=ctx.title,
                    search_date=ctx.search_date,
                    score=score,
                    cur_id=pack_cur_id([x for x in (url, sub_site) if x]),
                )
            )
        return results

    # ── Context loader (ld+json detail; channel packed in curID) ──────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        pipe = payload.find('|')
        url = payload[:pipe] if pipe >= 0 else payload
        sub_site = payload[pipe + 1 :].strip() if pipe >= 0 else ''
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture if ctx else None), f'[{site.name}] scene {url}')
        if not loaded:
            return None
        ld = _parse_ld(loaded['sel'])
        if ld is None:
            return None
        return LoadedScene(
            url=url, site=site, capture=ctx.capture if ctx else None, sel=loaded['sel'], html=loaded['html'], extra={'ld': ld, 'subSite': sub_site}
        )

    def _ld(self, scene: LoadedScene) -> dict[str, Any]:
        return scene.extra.get('ld', {}) if isinstance(scene.extra, dict) else {}

    def _sub_site(self, scene: LoadedScene) -> str:
        return scene.extra.get('subSite', '') if isinstance(scene.extra, dict) else ''

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        return (self._ld(scene).get('name') or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        return (self._ld(scene).get('description') or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return self._sub_site(scene) or scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [self._sub_site(scene) or scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        raw = (self._ld(scene).get('uploadDate') or '').strip()
        return (iso_date(raw) if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [
            (a.xpath('normalize-space(.)').get() or '').strip().lower() for a in scene.sel.xpath('//ul[contains(@class,"category-link")]//li//a')
        ]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        actors: list[ActorResult] = []
        for a in self._ld(scene).get('actor') or []:
            name = (a.get('name') or '').strip()
            if not name:
                continue
            photo = ''
            page = (a.get('@id') or '').strip()
            if page:
                loaded = await self.fetch_and_load(page, FetchCtx(capture=scene.capture), f'GET {page} (actor)')
                ld = _parse_ld(loaded['sel']) if loaded else None
                photo = (ld or {}).get('image') or ''
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        thumb = (self._ld(scene).get('thumbnailUrl') or '').strip()
        return [thumb.replace('tiny', 'large')] if thumb else []
