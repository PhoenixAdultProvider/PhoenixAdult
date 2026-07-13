from __future__ import annotations

from urllib.parse import quote

import httpx2

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from app.config.env import env
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import api_date, build_search_result
from app.utils.http.client import make_http

_API_BASE = 'https://api.theporndb.net'


def _auth_headers() -> dict[str, str]:
    token = env.metadata_api_token
    return {'Accept': 'application/json', 'Authorization': f'Bearer {token}'} if token else {}


class MetadataAPIClient(Client):
    @property
    def http(self) -> httpx2.AsyncClient:
        # Credentialed first-party API — verify TLS (the base client leaves it off for scrapers).
        if self._http is None:
            self._http = make_http(self._extra_headers, verify=True)
        return self._http

    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        url = f'{_API_BASE}/scenes?parse={ctx.encoded}'
        if ctx.ohash:
            url += f'&hash={quote(ctx.ohash)}'
        data = await self.fetch_json(url, FetchCtx(capture=ctx.capture), headers=_auth_headers(), label=f'GET {url}')
        if not isinstance(data, dict) or not data.get('data'):
            return
        for s in data['data']:
            scene_id = s.get('_id') or s.get('id')
            if not scene_id:
                continue
            results.append(
                build_search_result(
                    title=s.get('title') or '',
                    scene_url=f'{_API_BASE}/scenes/{scene_id}',
                    query=ctx.title,
                    display_date=api_date(s.get('date')),
                    search_date=ctx.search_date,
                    subsite=((s.get('site') or {}).get('name') or '').strip() or None,
                )
            )

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        url, _, tail = payload.partition('|')
        fallback_date = tail.strip()
        res = await self.fetch_json(url, FetchCtx(capture=ctx.capture if ctx else None), headers=_auth_headers(), label=f'GET {url}')
        d = res.get('data') if isinstance(res, dict) else None
        if not isinstance(d, dict):
            return None
        return LoadedScene(url=url, site=site, scene_date=fallback_date or None, capture=ctx.capture if ctx else None, extra=d)

    async def update(self, metadata: SceneDetail, scene: LoadedScene) -> None:
        d = scene.extra
        site = scene.site
        headers = _auth_headers()

        # Title
        metadata.title = d.get('title') or ''

        # Summary
        metadata.summary = d.get('description') or ''

        # Studio, Tagline and Collection(s)
        site_obj = d.get('site') or {}
        studio = site_obj.get('name') or site.name
        collections: list[str] = [site_obj['name']] if site_obj.get('name') else []
        if site_obj.get('network_id') and site_obj.get('id') != site_obj.get('network_id'):
            parent = await self.fetch_json(f'{_API_BASE}/sites/{site_obj["network_id"]}', FetchCtx(capture=scene.capture), headers=headers)
            parent_name = (parent.get('data') or {}).get('name') if isinstance(parent, dict) else None
            if parent_name:
                studio = parent_name
                collections.append(parent_name)
        metadata.studio = studio
        metadata.tagline = studio
        metadata.collections = collections or None

        # Release Date
        metadata.release_date = api_date(d.get('date')) or scene.scene_date or None

        # Genres
        metadata.genres = [t['name'].strip() for t in (d.get('tags') or []) if (t.get('name') or '').strip()]

        # Actor(s)
        for p in d.get('performers') or []:
            name = p.get('name') or ''
            face = p.get('face') or ''
            photo = face if face and 'default' not in face else ''
            parent_p = p.get('parent') or {}
            if parent_p.get('name'):
                name = parent_p['name']
                photo = parent_p.get('face') or ''
            if name:
                metadata.actors.append(ActorResult(name=name, photo_url=photo))

        # Posters
        if (d.get('posters') or {}).get('large'):
            metadata.raw_image_urls.append(d['posters']['large'])
        if (d.get('background') or {}).get('large'):
            metadata.raw_image_urls.append(d['background']['large'])
