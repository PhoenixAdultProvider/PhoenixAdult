from __future__ import annotations

import re
from typing import Any, TypedDict
from urllib.parse import quote

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id

STUDIO = 'Teen Core Club'
_SEARCH_QS = 'sg=false&sort=release&video_type=scene&lang=en&site_id=10&genre=0&dach=false'
_MAX_PAGES = 10
_CAMEL_RE = re.compile(r'(\w)([A-Z])')


class _SceneExtra(TypedDict):
    v: dict[str, Any]
    title: str
    actors: list[ActorResult]


class TeenCoreClubClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        api_base = f'{search_data.site_info.base_url.rstrip("/")}/api'
        scene_id = search_data.scene_id or ''
        text = search_data.title.strip()
        encoded = quote(text)

        page = 1
        last_page = 1
        while page <= last_page:
            url = f'{api_base}/videos/browse/search/{encoded}?page={page}&{_SEARCH_QS}'
            search_results = await self.fetch_json(url, FetchCtx(capture=search_data.capture))
            videos = search_results.get('videos') if isinstance(search_results, dict) else None
            if not isinstance(videos, dict):
                break

            last_page = min(videos.get('last_page') or 1, _MAX_PAGES)
            for v in videos.get('data') or []:
                title = ((v.get('title') or {}).get('en') or '').strip()
                if not title or v.get('id') is None:
                    continue

                detail_url = f'{api_base}/videodetail/{v["id"]}'

                results.append(
                    build_search_result(
                        title=title,
                        scene_url=detail_url,
                        query=text,
                        display_date=iso_date(v.get('publication_date') or ''),
                        search_date=search_data.search_date,
                        score=100 if scene_id and str(v['id']) == scene_id else None,
                        cur_id=pack_cur_id([detail_url]),
                    )
                )

            page += 1

    # ── Context Loader ──────────────────────────────────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        details_page_elements = await self.fetch_json(payload, FetchCtx(capture=ctx.capture if ctx else None))
        v = details_page_elements.get('video') if isinstance(details_page_elements, dict) else None
        if not isinstance(v, dict):
            return None

        title = ((v.get('title') or {}).get('en') or '').strip()
        actors = [ActorResult(name=n) for n in ((a.get('name') or '').strip() for a in (v.get('actors') or [])) if n]

        if actors and title.lower().startswith('bic_'):
            names = [a.name for a in actors]
            title = ' & '.join(names) if len(names) == 2 else ', '.join(names)

        if not title:
            return None

        extra: _SceneExtra = {'v': v, 'title': title, 'actors': actors}
        return LoadedScene(url=payload, site=site, capture=ctx.capture if ctx else None, extra=extra)

    async def update(self, metadata: SceneDetail, scene: LoadedScene) -> None:
        site = scene.site
        extra: _SceneExtra = scene.extra
        v = extra['v']
        title = extra['title']
        actors = extra['actors']

        # Title
        metadata.title = title

        # Summary
        metadata.summary = ((v.get('description') or {}).get('en') or '').strip()

        # Studio
        metadata.studio = STUDIO

        # Tagline and Collection(s)
        tagline = site.name
        label = (v.get('labels') or [{}])[0].get('name') if v.get('labels') else None
        if label:
            tagline = _CAMEL_RE.sub(r'\1 \2', label.split('.')[0].strip())

        metadata.tagline = tagline if tagline and tagline != STUDIO else None
        metadata.collections = [tagline] if tagline else None

        # Release Date
        metadata.release_date = iso_date(v.get('publication_date') or '') or None

        # Genres
        metadata.genres = [g for g in (((gg.get('title') or {}).get('en') or '').strip() for gg in (v.get('genres') or [])) if g]

        # Actor(s)
        metadata.actors = actors

        # Posters
        images = self.image_collector()
        artwork = v.get('artwork') or {}
        cover = v.get('cover') or {}
        images['push'](artwork.get('small'))
        images['push'](artwork.get('large'))
        images['push'](cover.get('small'))
        images['push'](cover.get('medium'))
        images['push'](cover.get('large'))
        for s in v.get('screenshots') or []:
            images['push'](s)

        metadata.art = images['list']
