from __future__ import annotations

import re

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import api_date, build_search_result

_CAP_RE = re.compile(r'\b\w')


def _capitalize(s: str) -> str:
    return _CAP_RE.sub(lambda m: m.group().upper(), s)


class MetArtClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        api = search_data.site_info.base_url.rstrip('/') + search_data.site_info.search_path
        url = f'{api}/search-results?query[contentType]=movies&searchPhrase={search_data.encoded}'
        search_results = await self.fetch_json(url, FetchCtx(capture=search_data.capture), label=f'GET {url}')
        if not isinstance(search_results, dict) or not search_results.get('items'):
            return

        for entry in search_results['items']:
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
                    title=it['name'],
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=api_date(it.get('publishedAt')),
                    search_date=search_data.search_date,
                )
            )

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        pipe = payload.find('|')
        url = payload[:pipe] if pipe >= 0 else payload
        fallback_date = payload[pipe + 1 :].strip() if pipe >= 0 else ''
        capture = ctx.capture if ctx else None

        details_page_elements = await self.fetch_json(url, FetchCtx(capture=capture), label=f'GET {url}')
        if not isinstance(details_page_elements, dict):
            return None

        return LoadedScene(
            url=url, site=site, capture=capture, extra=details_page_elements, scene_date=fallback_date or None, subsite=ctx.subsite if ctx else None
        )

    async def update(self, metadata: SceneDetail, scene: LoadedScene) -> None:
        site = scene.site
        d = scene.extra
        base = site.base_url.rstrip('/')
        cdn = f'https://cdn.metartnetwork.com/{d["siteUUID"]}' if d.get('siteUUID') else ''

        # Title
        metadata.title = d.get('name') or ''

        # Summary
        metadata.summary = d.get('description') or ''

        # Studio
        metadata.studio = 'MetArt'

        # Tagline and Collection(s)
        metadata.tagline = site.name
        metadata.collections = [site.name]

        # Release Date
        metadata.release_date = api_date(d.get('publishedAt')) or scene.scene_date or None

        # Genres
        genres = [_capitalize(t) for t in (d.get('tags') or [])]
        genres.append('Glamorous')
        metadata.genres = genres

        # Actor(s)
        metadata.actors = [
            ActorResult(name=m['name'], photo_url=base + m['headshotImagePath'] if m.get('headshotImagePath') else '')
            for m in (d.get('models') or [])
            if isinstance(m, dict) and m.get('name')
        ]

        # Director(s)
        directors = [ActorResult(name=p['name']) for p in (d.get('photographers') or []) if isinstance(p, dict) and p.get('name')]
        metadata.directors = directors or None

        # Posters
        if cdn and d.get('coverImagePath'):
            metadata.art.append(cdn + d['coverImagePath'])

        if cdn and d.get('splashImagePath'):
            metadata.art.append(cdn + d['splashImagePath'])
