from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from app.clients.base import ActorResult, Client, FetchCtx, RawCaptureEntry, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, date_distance_score, iso_date, pack_cur_id, title_distance_score
from app.utils.helpers.html_helpers import first_attr
from app.utils.logging.logger import logger
from app.utils.searchengines import SearchOptions, web_search, web_search_available

_PAGE_DATA_URL = 'https://netvideogirls.com/page-data/home/page-data.json'
_VIDEO_ID_RE = re.compile(r'(\d+)-')
_HTTP_RE = re.compile(r'^https?:', re.IGNORECASE)
_AND_RE = re.compile(r'\s+and\s+', re.IGNORECASE)
STUDIO = 'NVG Network'


def _actors_from(raw: str) -> list[ActorResult]:
    return [ActorResult(name=s.strip()) for s in _AND_RE.split(raw) if s.strip()]


class NVGClient(Client):
    async def _get_page_data(self, scene_id: int, capture: list[RawCaptureEntry] | None, referer: str) -> dict[str, Any] | None:
        data = await self.fetch_json(_PAGE_DATA_URL, FetchCtx(capture=capture), headers={'Referer': referer})
        if not isinstance(data, dict):
            return None
        edges = (((data.get('result') or {}).get('data') or {}).get('allMysqlTourStats') or {}).get('edges') or []
        for edge in edges:
            tt = (edge.get('node') or {}).get('tour_thumbs') if isinstance(edge, dict) else None
            if isinstance(tt, dict) and (tt.get('updates') or {}).get('mysqlId') == scene_id:
                return tt
        return None

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        scene_id = int(ctx.scene_id) if ctx.scene_id else None
        cast_query = ctx.title.strip()

        page_scene = await self._get_page_data(scene_id, ctx.capture, base) if scene_id is not None else None

        urls: list[str] = []
        if web_search_available():
            try:
                found = await web_search(SearchOptions(query=cast_query or ctx.title, site=urlparse(base).netloc, num=10))
                urls = [u for u in found if '/tag/' not in u and '/page/' not in u and '/category/' not in u]
            except Exception as err:  # noqa: BLE001 - web search is best-effort; fall back to page-data
                logger.debug('Net Video Girls', f'webSearch threw: {err}')

        results: list[SearchResult] = []

        if not urls:
            updates = (page_scene or {}).get('updates') or {}
            if updates.get('mysqlId') is not None:
                sid = updates['mysqlId']
                own_date = iso_date(updates.get('release_date') or '') or None
                date = own_date or ctx.search_date or ''
                results.append(
                    build_search_result(
                        title=(updates.get('short_title') or '').strip(),
                        scene_url=base,
                        query=ctx.title,
                        display_date=own_date,
                        search_date=ctx.search_date,
                        score=100,
                        cur_id=pack_cur_id([f'{sid}|{date}|{cast_query}']),
                    )
                )
            return results

        for scene_url in urls:
            loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture))
            if not loaded:
                continue
            sel = loaded['sel']
            m = _VIDEO_ID_RE.search(sel.xpath('(//source)[1]/@src').get() or '')
            video_id = m.group(1) if m else ''

            updates = (page_scene or {}).get('updates') or {}
            if page_scene and video_id and str(updates.get('mysqlId')) == video_id:
                title = (updates.get('short_title') or '').strip()
                own_date = iso_date(updates.get('release_date') or '') or None
                score: float = 100
            else:
                title = (sel.xpath('(//title)[1]').xpath('string(.)').get() or '').split('|')[0].strip()
                own_date = iso_date(sel.xpath('(//meta[@itemprop])[1]/@content').get() or '') or None
                score = date_distance_score(ctx.search_date, own_date) if ctx.search_date and own_date else title_distance_score(ctx.title, title)
            date = own_date or ctx.search_date or ''

            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=ctx.title,
                    display_date=own_date,
                    search_date=ctx.search_date,
                    score=score,
                    cur_id=pack_cur_id([f'{scene_url}|{date}|{cast_query}|{video_id}']),
                )
            )
        return results

    async def fetch_scene_detail(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> SceneDetail | None:
        parts = payload.split('|')
        head = parts[0] if parts else ''
        date = parts[1] if len(parts) > 1 else ''
        cast_str = parts[2] if len(parts) > 2 else ''
        video_id = parts[3] if len(parts) > 3 else ''
        base = site.base_url.rstrip('/')
        capture = ctx.capture if ctx else None

        title = ''
        summary = ''
        poster = ''
        scene_url: str | None = None

        if _HTTP_RE.match(head):
            scene_url = head
            loaded = await self.fetch_and_load(head, FetchCtx(capture=capture))
            if loaded:
                sel = loaded['sel']
                title = (sel.xpath('(//title)[1]').xpath('string(.)').get() or '').split('|')[0].strip()
                summary = (sel.xpath('(//div[contains(@class,"the-content")]/p)[1]').xpath('string(.)').get() or '').strip()
                poster = first_attr(sel, '(//video)[1]/@poster')
            # Legacy merge: prefer the page-data fluid src when the mysqlId resolves.
            if video_id.isdigit():
                scene = await self._get_page_data(int(video_id), capture, base)
                src = ((((scene or {}).get('localFile') or {}).get('childImageSharp') or {}).get('fluid') or {}).get('src') if scene else None
                if src:
                    poster = src if src.startswith('http') else base + src
        elif head:
            scene = await self._get_page_data(int(head), capture, base) if head.isdigit() else None
            if scene:
                title = ((scene.get('updates') or {}).get('short_title') or '').strip()
                src = (((scene.get('localFile') or {}).get('childImageSharp') or {}).get('fluid') or {}).get('src')
                if src:
                    poster = src if src.startswith('http') else base + src

        if not title:
            return None

        return SceneDetail(
            title=title,
            summary=summary,
            studio=STUDIO,
            tagline=site.name,
            collections=[site.name],
            release_date=date or None,
            genres=[],
            actors=_actors_from(cast_str),
            raw_image_urls=[poster] if poster else [],
            scene_url=scene_url,
        )
