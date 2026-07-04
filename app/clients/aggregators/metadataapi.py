from __future__ import annotations

from urllib.parse import quote

import httpx2

from app.clients.base import ActorResult, Client, FetchCtx, SceneContext, SceneDetail, SearchContext, SearchResult
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

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        url = f'{_API_BASE}/scenes?parse={ctx.encoded}'
        if ctx.ohash:
            url += f'&hash={quote(ctx.ohash)}'
        data = await self.fetch_json(url, FetchCtx(capture=ctx.capture), headers=_auth_headers(), label=f'GET {url}')
        if not isinstance(data, dict) or not data.get('data'):
            return []
        results: list[SearchResult] = []
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
                )
            )
        return results

    async def fetch_scene_detail(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> SceneDetail | None:
        url, _, tail = payload.partition('|')
        fallback_date = tail.strip()
        headers = _auth_headers()
        res = await self.fetch_json(url, FetchCtx(capture=ctx.capture if ctx else None), headers=headers, label=f'GET {url}')
        d = res.get('data') if isinstance(res, dict) else None
        if not isinstance(d, dict):
            return None

        site_obj = d.get('site') or {}
        studio = site_obj.get('name') or site.name
        collections: list[str] = [site_obj['name']] if site_obj.get('name') else []
        if site_obj.get('network_id') and site_obj.get('id') != site_obj.get('network_id'):
            parent = await self.fetch_json(f'{_API_BASE}/sites/{site_obj["network_id"]}', FetchCtx(capture=ctx.capture if ctx else None), headers=headers)
            parent_name = (parent.get('data') or {}).get('name') if isinstance(parent, dict) else None
            if parent_name:
                studio = parent_name
                collections.append(parent_name)

        genres = [t['name'].strip() for t in (d.get('tags') or []) if (t.get('name') or '').strip()]

        actors: list[ActorResult] = []
        for p in d.get('performers') or []:
            name = p.get('name') or ''
            face = p.get('face') or ''
            photo = face if face and 'default' not in face else ''
            parent_p = p.get('parent') or {}
            if parent_p.get('name'):
                name = parent_p['name']
                photo = parent_p.get('face') or ''
            if name:
                actors.append(ActorResult(name=name, photo_url=photo))

        raw_images: list[str] = []
        if (d.get('posters') or {}).get('large'):
            raw_images.append(d['posters']['large'])
        if (d.get('background') or {}).get('large'):
            raw_images.append(d['background']['large'])

        return SceneDetail(
            title=d.get('title') or '',
            summary=d.get('description') or '',
            studio=studio,
            tagline=studio,
            collections=collections or None,
            release_date=api_date(d.get('date')) or fallback_date or None,
            genres=genres,
            actors=actors,
            raw_image_urls=raw_images,
            scene_url=url,
        )
