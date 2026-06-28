from __future__ import annotations

import re
from typing import Literal

from app.clients.base import ActorResult, Client, FetchCtx, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import api_date, build_search_result

_CAP_RE = re.compile(r'\b\w')


def _capitalize(s: str) -> str:
    return _CAP_RE.sub(lambda m: m.group().upper(), s)


class MetArtClient(Client):
    def image_rule(self, site: ResolvedSiteInfo) -> Literal['aspect', 'threshold']:
        return 'aspect'

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        api = ctx.site_info.base_url.rstrip('/') + ctx.site_info.search_path
        url = f'{api}/search-results?query[contentType]=movies&searchPhrase={ctx.encoded}'
        data = await self.fetch_json(url, FetchCtx(capture=ctx.capture), label=f'GET {url}')
        if not isinstance(data, dict) or not data.get('items'):
            return []

        results: list[SearchResult] = []
        for entry in data['items']:
            it = entry.get('item') if isinstance(entry, dict) else None
            if not isinstance(it, dict) or not it.get('name') or not it.get('path'):
                continue
            parts = [p for p in it['path'].split('/') if p]
            if len(parts) < 2:
                continue
            name_slug, date_slug = parts[-1], parts[-2]
            scene_url = f'{api}/movie?name={name_slug}&date={date_slug}'
            results.append(
                build_search_result(
                    title=it['name'], scene_url=scene_url, query=ctx.title, display_date=api_date(it.get('publishedAt')), search_date=ctx.search_date
                )
            )
        return results

    async def fetch_scene_detail(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> SceneDetail | None:
        pipe = payload.find('|')
        url = payload[:pipe] if pipe >= 0 else payload
        fallback_date = payload[pipe + 1 :].strip() if pipe >= 0 else ''

        d = await self.fetch_json(url, FetchCtx(capture=ctx.capture if ctx else None), label=f'GET {url}')
        if not isinstance(d, dict):
            return None

        base = site.base_url.rstrip('/')
        cdn = f'https://cdn.metartnetwork.com/{d["siteUUID"]}' if d.get('siteUUID') else ''

        genres = [_capitalize(t) for t in (d.get('tags') or [])]
        genres.append('Glamorous')

        actors = [
            ActorResult(name=m['name'], photo_url=base + m['headshotImagePath'] if m.get('headshotImagePath') else '')
            for m in (d.get('models') or [])
            if isinstance(m, dict) and m.get('name')
        ]
        directors = [ActorResult(name=p['name']) for p in (d.get('photographers') or []) if isinstance(p, dict) and p.get('name')]

        raw_images: list[str] = []
        if cdn and d.get('coverImagePath'):
            raw_images.append(cdn + d['coverImagePath'])
        if cdn and d.get('splashImagePath'):
            raw_images.append(cdn + d['splashImagePath'])

        return SceneDetail(
            title=d.get('name') or '',
            summary=d.get('description') or '',
            studio='MetArt',
            tagline=site.name,
            release_date=api_date(d.get('publishedAt')) or fallback_date or None,
            collections=[site.name],
            genres=genres,
            actors=actors,
            directors=directors or None,
            raw_image_urls=raw_images,
            scene_url=url,
        )
