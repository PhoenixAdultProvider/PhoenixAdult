from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id, slugify

_SCENE_BASE = 'https://www.naughtyamerica.com'
_LASTPAGE_RE = re.compile(r'\d+(?=#)')
STUDIO = 'Naughty America'
# AWS WAF here is rate-based; serialize fetches and space them apart (matches the
# reference scraper's CONCURRENT_REQUESTS=1 + DOWNLOAD_DELAY=2) to stay under it.
_PACE_SECONDS = 2.0

_CARD_XP = '//div[contains(@class,"scene-item")] | //div[@class="scene-grid-item"]'


def _https(raw: str) -> str:
    return f'https:{raw}' if raw.startswith('//') else raw


def _scene_path(href: str) -> str:
    if '/scene/' in href:
        return 'scene/' + href.split('/scene/', 1)[1].lstrip('/')
    return href.lstrip('/')


class NaughtyAmericaClient(Client):
    def __init__(self, extra_headers: dict[str, str] | None = None) -> None:
        super().__init__(extra_headers)
        self._pace_lock = asyncio.Lock()
        self._last_fetch = 0.0

    async def _paced(self, url: str, ctx: FetchCtx | None = None, label: str | None = None) -> dict[str, Any] | None:
        """Serialized, rate-limited fetch — keeps requests >=_PACE_SECONDS apart and
        opts into the bypass fallback (NA's AWS WAF 202-blocks plain fetches)."""
        if ctx is None:
            ctx = FetchCtx()
        ctx.use_bypass = True
        async with self._pace_lock:
            delta = time.monotonic() - self._last_fetch
            if delta < _PACE_SECONDS:
                await asyncio.sleep(_PACE_SECONDS - delta)
            self._last_fetch = time.monotonic()
            return await self.fetch_and_load(url, ctx, label)

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        search_url = f'{base}/search?term={slugify(ctx.title).replace("-", "+")}&_gl=1'
        loaded = await self._paced(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {search_url}')
        if not loaded:
            return []

        page_sel = loaded['sel']
        is_search_mode = bool(page_sel.xpath('//div[contains(@class,"scene-item")]'))
        last_href = page_sel.xpath('(//li/a[./i[contains(@class,"double")]])[1]/@href').get() or ''
        m = _LASTPAGE_RE.search(last_href)
        pagination = int(m.group(0)) + 2 if m else 3

        results: list[SearchResult] = []
        seen: set[str] = set()
        for idx in range(2, pagination):
            for card in page_sel.xpath(_CARD_XP):
                anchor = card.xpath('(.//a[contains(@href,"/scene/")])[1]')
                href = (anchor.xpath('@href').get() or '').strip()
                raw_title = (anchor.xpath('@title').get() or '').strip()
                if not href or not raw_title:
                    continue
                path = _scene_path(href)
                if path in seen:
                    continue
                seen.add(path)
                date = iso_date((card.xpath('(.//p[contains(@class,"entry-date")])[1]').xpath('string(.)').get() or '').strip())
                results.append(
                    build_search_result(
                        title=raw_title,
                        scene_url=f'{_SCENE_BASE}/{path}',
                        query=ctx.title,
                        display_date=date,
                        search_date=ctx.search_date,
                        cur_id=pack_cur_id([path]),
                    )
                )
            if pagination > 1 and pagination != idx + 1:
                next_url = f'{search_url}&page={idx}' if is_search_mode else f'{base}/pornstar/{slugify(ctx.title)}?related_page={idx}'
                nxt = await self._paced(next_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search page {idx}')
                if not nxt:
                    break
                page_sel = nxt['sel']
        return results

    # ── Context loader (curID is the scene URL slug path) ────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        path = payload.split('|')[0].lstrip('/')
        url = f'{_SCENE_BASE}/{path}'
        loaded = await self._paced(url, FetchCtx(capture=ctx.capture if ctx else None), f'[{site.name}] detail {url}')
        if not loaded:
            return None
        return LoadedScene(url=url, site=site, capture=ctx.capture if ctx else None, sel=loaded['sel'], html=loaded['html'])

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//div[contains(@class,"scene-info")]//h1)[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        div = scene.sel.xpath('(//div[contains(@class,"synopsis") and contains(@class,"grey-text")])[1]')
        return ''.join(div.xpath('.//text()[not(ancestor::h2)]').getall()).strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//a[contains(@class,"site-title")])[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        tag = await self.fetch_tagline(scene)
        return [tag] if tag else None

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//div[contains(@class,"date-tags")]//span[contains(@class,"entry-date")])[1]').xpath('string(.)').get() or '').strip()
        return iso_date(raw) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [
            a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//div[contains(@class,"categories") and contains(@class,"grey-text")]//a')
        ]
        return self.dedup_strings(values) or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        names = [n for n in ((a.xpath('normalize-space(.)').get() or '').strip() for a in scene.sel.xpath('//div[contains(@class,"performer-list")]//a')) if n]
        actors: list[ActorResult] = []
        for name in names:
            slug = name.lower().replace(' ', '-').replace("'", '')
            page = await self._paced(f'{_SCENE_BASE}/pornstar/{slug}', None, f'GET pornstar {slug}')
            raw = (page['sel'].xpath('(//img[contains(@class,"performer-pic")])[1]/@data-src').get() or '').strip() if page else ''
            actors.append(ActorResult(name=name, photo_url=_https(raw) if raw else ''))
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        coll = self.image_collector(_https)
        xpaths = (
            '//a[@class="play-trailer"]/picture[1]//source[contains(@data-srcset,"jpg")]/@data-srcset',
            '//dl8-video/@poster[contains(.,"jpg")]',
        )
        for xpath in xpaths:
            for raw in scene.sel.xpath(xpath).getall():
                coll['push'](raw)
        images: list[str] = coll['list']
        return images or None
