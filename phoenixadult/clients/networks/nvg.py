from __future__ import annotations

import re
from typing import Any

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.capture import RawCaptureEntry
from phoenixadult.models.scrape import ActorResult, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, web_search_urls
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.scoring import date_distance_score, title_distance_score
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.logging.best_effort import best_effort

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

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        scene_id = int(search_data.scene_id) if search_data.scene_id else None
        cast_query = search_data.title.strip()

        page_scene = await self._get_page_data(scene_id, search_data.capture, base) if scene_id is not None else None

        urls: list[str] = []
        with best_effort('Net Video Girls', 'webSearch', level='debug'):
            found = await web_search_urls(cast_query or search_data.title, search_data.site_info)
            urls = [u for u in found if '/tag/' not in u and '/page/' not in u and '/category/' not in u]

        if not urls:
            updates = (page_scene or {}).get('updates') or {}
            if updates.get('mysqlId') is not None:
                sid = updates['mysqlId']
                own_date = iso_date(updates.get('release_date') or '') or None
                date = own_date or search_data.search_date or ''

                results.append(
                    build_search_result(
                        site=search_data.site_info,
                        title=(updates.get('short_title') or '').strip(),
                        scene_url=base,
                        query=search_data.title,
                        display_date=own_date,
                        search_date=search_data.search_date,
                        score=100,
                        cur_id=pack_cur_id([f'{sid}|{date}|{cast_query}']),
                    )
                )

            return

        for scene_url in urls:
            search_results = await self.fetch_and_load(scene_url, FetchCtx(capture=search_data.capture))
            if not search_results:
                continue

            sel = search_results['sel']
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
                score = (
                    date_distance_score(search_data.search_date, own_date)
                    if search_data.search_date and own_date
                    else title_distance_score(search_data.title, title)
                )

            date = own_date or search_data.search_date or ''

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=own_date,
                    search_date=search_data.search_date,
                    score=score,
                    cur_id=pack_cur_id([f'{scene_url}|{date}|{cast_query}|{video_id}']),
                )
            )

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
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
            details_page_elements = await self.fetch_and_load(head, FetchCtx(capture=capture, use_bypass=site.use_bypass))
            if details_page_elements:
                sel = details_page_elements['sel']
                title = (sel.xpath('(//title)[1]').xpath('string(.)').get() or '').split('|')[0].strip()
                summary = (sel.xpath('(//div[contains(@class,"the-content")]/p)[1]').xpath('string(.)').get() or '').strip()
                poster = first_attr(sel, '(//video)[1]/@poster')

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

        return LoadedScene(
            url=scene_url or payload,
            site=site,
            scene_date=date or None,
            capture=capture,
            extra={'title': title, 'summary': summary, 'poster': poster, 'cast_str': cast_str, 'scene_url': scene_url},
        )

    async def update(self, metadata: SceneDetail, scene: LoadedScene) -> None:
        extra = scene.extra

        # Title
        metadata.title = extra['title']

        # Summary
        metadata.summary = extra['summary']

        # Studio
        metadata.studio = STUDIO

        # Tagline and Collection(s)
        metadata.tagline = scene.site.name
        metadata.collections = [scene.site.name]

        # Release Date
        metadata.release_date = scene.scene_date or None

        # Genres
        metadata.genres = []

        # Actor(s)
        metadata.actors = _actors_from(extra['cast_str'])

        # Posters
        metadata.art = [extra['poster']] if extra['poster'] else []
        metadata.scene_url = extra['scene_url']
