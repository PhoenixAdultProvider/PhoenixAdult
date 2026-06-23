from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_text, web_search_urls

_TITLE_FIXES_DATA = Path(__file__).parent / '_data' / 'json' / 'blackpayback_title_fixes.json'
_TITLE_FIXES: dict[str, str] = json.loads(_TITLE_FIXES_DATA.read_text(encoding='utf-8'))

_IAFD_STUDIO_URL = 'https://www.iafd.com/studio.rme/studio=9856/blackpayback.com.htm'
_POSTER_RE = re.compile(r'poster="([^"]+)"')
_LEADING_NUM_RE = re.compile(r'^\d+\s+')


@dataclass
class _BpbExtra:
    title: str
    release_date: str | None
    actors: list[ActorResult]


class BlackPayBackClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        text = _LEADING_NUM_RE.sub('', ctx.title).strip()
        slug = re.sub(r'\s+', '-', text.lower())

        candidates: list[str] = [f'{base}/tour/trailers/{slug}.html']
        for u in await web_search_urls(text, ctx.site_info, include=['/trailers/']):
            if u not in candidates:
                candidates.append(u)

        results: list[SearchResult] = []
        for scene_url in candidates:
            loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] candidate {scene_url}')
            if not loaded:
                continue
            title = first_text(loaded['sel'], '//h1')
            if not title or '404 Error' in title:
                continue
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=text,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([scene_url]),
                )
            )
        return results

    # ── Detail: main page + two-hop IAFD lookup, stashed for the field hooks ──

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        fetch_ctx = FetchCtx(capture=ctx.capture if ctx else None)
        main = await self.fetch_and_load(payload, fetch_ctx, f'[{site.name}] detail {payload}')
        if not main:
            return None
        title = first_text(main['sel'], '//h1')
        if not title:
            return None
        title = _TITLE_FIXES.get(title, title)

        release_date, actors = await self._iafd_lookup(title, fetch_ctx, site)
        return LoadedScene(
            url=payload,
            site=site,
            capture=fetch_ctx.capture,
            sel=main['sel'],
            html=main['html'],
            extra=_BpbExtra(title=title, release_date=release_date, actors=actors),
        )

    async def _iafd_lookup(self, title: str, fetch_ctx: FetchCtx, site: ResolvedSiteInfo) -> tuple[str | None, list[ActorResult]]:
        studio = await self.fetch_and_load(_IAFD_STUDIO_URL, fetch_ctx, f'[{site.name}] IAFD studio')
        if not studio:
            return None, []
        iafd_href = ''
        for row in studio['sel'].xpath('//table[@id="studio"]/tbody/tr'):
            row_title = (row.xpath('(.//a)[1]/text()').get() or '').split('(')[0].strip()
            if row_title.lower() == title.lower():
                iafd_href = (row.xpath('(.//a/@href)[1]').get() or '').strip()
                break
        if not iafd_href:
            return None, []

        iafd = await self.fetch_and_load(f'https://www.iafd.com{iafd_href}', fetch_ctx, f'[{site.name}] IAFD scene')
        if not iafd:
            return None, []
        raw_date = first_text(iafd['sel'], '//p[contains(.,"Release Date")]/following-sibling::p[contains(@class,"biodata")][1]')
        release_date = (iso_date(raw_date, '%b %d, %Y') or iso_date(raw_date)) if raw_date else None
        actors: list[ActorResult] = []
        for a in iafd['sel'].xpath('//div[contains(@class,"castbox")]//a'):
            name = (a.xpath('normalize-space(.)').get() or '').strip()
            if not name:
                continue
            photo = (a.xpath('(.//img/@src)[1]').get() or '').strip()
            actors.append(ActorResult(name=name, photo_url=photo))
        return release_date, actors

    def _extra(self, scene: LoadedScene) -> _BpbExtra:
        assert isinstance(scene.extra, _BpbExtra)
        return scene.extra

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        return self._extra(scene).title or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"videoDetails") and contains(@class,"clear")]/p') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        return self._extra(scene).release_date

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [
            li.xpath('normalize-space(.)').get() for li in scene.sel.xpath('//div[contains(@class,"featuring") and contains(@class,"clear")]//li[.//a]')
        ]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        return self._extra(scene).actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []
        for script in scene.sel.xpath('//div[contains(@class,"player")]//script'):
            text = script.xpath('string(.)').get() or ''
            m = _POSTER_RE.search(text)
            if not m:
                continue
            raw = m.group(1)
            abs_url = raw if raw.startswith('http') else absolute_url(raw, scene.site.base_url)
            if abs_url not in images:
                images.append(abs_url)
        return images
