from __future__ import annotations

import re
from dataclasses import dataclass

from phoenixadult.clients.aggregators import iafd
from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_text, web_search_urls

_TITLE_FIXES: dict[str, str] = {'ARIA CARSON 2': 'Birfday Bitch'}

_IAFD_STUDIO_URL = 'https://www.iafd.com/studio.rme/studio=9856/blackpayback.com.htm'
_POSTER_RE = re.compile(r'poster="([^"]+)"')
_LEADING_NUM_RE = re.compile(r'^\d+\s+')


@dataclass
class _BpbExtra:
    title: str
    release_date: str | None
    actors: list[ActorResult]


class BlackPayBackClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        text = _LEADING_NUM_RE.sub('', search_data.title).strip()
        slug = re.sub(r'\s+', '-', text.lower())

        candidates: list[str] = [f'{base}/tour/trailers/{slug}.html']
        for u in await web_search_urls(text, search_data.site_info, include=['/trailers/']):
            if u not in candidates:
                candidates.append(u)

        for scene_url, details_page_elements in await self.fetch_candidate_pages(
            candidates, FetchCtx(capture=search_data.capture), lambda scene_url: f'[{search_data.site_info.name}] candidate {scene_url}'
        ):
            if not details_page_elements:
                continue

            title = first_text(details_page_elements['sel'], '//h1')
            if not title or '404 Error' in title:
                continue

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=text,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([scene_url]),
                )
            )

    # ── Context Loader (main page + two-hop IAFD lookup, stashed for the field hooks) ──

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        fetch_ctx = FetchCtx(capture=ctx.capture if ctx else None, use_bypass=site.use_bypass)
        main_page_elements = await self.fetch_and_load(payload, fetch_ctx, f'[{site.name}] detail {payload}')
        if not main_page_elements:
            return None

        title = first_text(main_page_elements['sel'], '//h1')
        if not title:
            return None

        title = _TITLE_FIXES.get(title, title)

        release_date, actors = await iafd.supplement(self, _IAFD_STUDIO_URL, title, fetch_ctx, f'[{site.name}]')
        return LoadedScene(
            url=payload,
            site=site,
            capture=fetch_ctx.capture,
            sel=main_page_elements['sel'],
            html=main_page_elements['html'],
            extra=_BpbExtra(title=title, release_date=release_date, actors=actors),
        )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _extra(self, scene: LoadedScene) -> _BpbExtra:
        assert isinstance(scene.extra, _BpbExtra)
        return scene.extra

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.title = self._extra(scene).title or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//div[contains(@class,"videoDetails") and contains(@class,"clear")]/p')

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = self._extra(scene).release_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            genre_link.xpath('normalize-space(.)').get()
            for genre_link in details_page_elements.xpath('//div[contains(@class,"featuring") and contains(@class,"clear")]//li[.//a]')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.actors = self._extra(scene).actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        for script in details_page_elements.xpath('//div[contains(@class,"player")]//script'):
            text = script.xpath('string(.)').get() or ''
            m = _POSTER_RE.search(text)
            if not m:
                continue

            images.push(m.group(1))

        metadata.art = images.items
