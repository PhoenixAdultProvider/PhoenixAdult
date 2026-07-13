from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, LoadedScene, RawCaptureEntry, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.graphql_client import GraphQLClient
from app.utils.helpers.helpers import build_search_result

_SEARCH_QUERY = 'query Search($query: String!) { search { search(input: {query: $query}) { result { type itemId name description images } } } }'
_FIND_VIDEO_QUERY = (
    'query FindVideo($videoId: ID!) { video { find(input: {videoId: $videoId}) '
    '{ result { videoId title duration galleryCount description { short long } talent { type talent { talentId name } } } } } }'
)
_BATCH_ASSET_QUERY = (
    'query BatchFindAssetQuery($paths: [String!]!) { asset { batch(input: {paths: $paths}) { result { path mime size serve { type uri } } } } }'
)

_CHUNK_SIZE = 25

_SITE_CONFIG: dict[str, dict[str, Any]] = {
    'Fit18': {'api_key': '77cd9282-9d81-4ba8-8868-ca9125c76991', 'endpoint': 'https://fit18.team18media.app/graphql', 'genres': ['Young', 'Gym']},
    'Thicc18': {'api_key': '0e36c7e9-8cb7-4fa1-9454-adbc2bad15f0', 'endpoint': 'https://thicc18.team18media.app/graphql', 'genres': ['Thicc']},
}


class Network18Client(GraphQLClient):
    async def _gql(self, site_name: str, base_url: str, query: str, variable: str, value: Any, label: str, sink: list[RawCaptureEntry] | None) -> Any:
        cfg = _SITE_CONFIG[site_name]
        headers = {'argonath-api-key': cfg['api_key'], 'Referer': base_url}
        return await self.graphql(cfg['endpoint'], query, {variable: value}, headers=headers, capture_label=label, capture_sink=sink)

    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        if ctx.site_info.name not in _SITE_CONFIG:
            return
        site = ctx.site_info
        data = await self._gql(site.name, site.base_url, _SEARCH_QUERY, 'query', ctx.title, f'[{site.name}] search "{ctx.title}"', ctx.capture)
        items = (((data or {}).get('search') or {}).get('search') or {}).get('result') or []

        for item in items:
            if not isinstance(item, dict) or item.get('type') != 'VIDEO' or not item.get('itemId'):
                continue
            images = item.get('images')
            thumb = str(images[0]) if isinstance(images, list) and images else None
            results.append(
                build_search_result(
                    title=item.get('name') or '',
                    scene_url=item['itemId'],
                    query=ctx.title,
                    search_date=ctx.search_date,
                    cur_id=self.encode(item['itemId']),
                    thumb_url=thumb,
                )
            )

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        if site.name not in _SITE_CONFIG:
            return None
        video_id = payload
        sink = ctx.capture if ctx else None
        splitted = video_id.split(':')
        model_id = splitted[0]
        scene = splitted[-1]
        try:
            scene_num = int(scene.replace('scene', ''))
        except ValueError:
            scene_num = 0

        data = await self._gql(site.name, site.base_url, _FIND_VIDEO_QUERY, 'videoId', video_id, f'[{site.name}] findVideo {video_id}', sink)
        detail = (((data or {}).get('video') or {}).get('find') or {}).get('result')
        if not isinstance(detail, dict):
            return None

        return LoadedScene(
            url=video_id,
            site=site,
            capture=sink,
            extra={'detail': detail, 'model_id': model_id, 'scene': scene, 'scene_num': scene_num},
            subsite=ctx.subsite if ctx else None,
        )

    async def update(self, metadata: SceneDetail, scene: LoadedScene) -> None:
        site = scene.site
        e = scene.extra
        detail = e['detail']
        model_id = e['model_id']
        scene_id = e['scene']
        scene_num = e['scene_num']
        sink = scene.capture

        # Title
        metadata.title = detail.get('title') or ''

        # Summary
        summary = ((detail.get('description') or {}).get('long') or '').strip()
        if summary and summary[-1] not in '!.?':
            summary += '.'
        metadata.summary = summary

        # Studio
        metadata.studio = site.name

        # Tagline and Collection(s)
        metadata.tagline = site.name
        metadata.collections = [site.name]

        # Genres
        metadata.genres = list(_SITE_CONFIG[site.name]['genres'])

        # Actor(s)
        metadata.actors = await self._fetch_actors(site, detail.get('talent') or [], sink)

        # Posters
        metadata.raw_image_urls = await self._fetch_image_urls(site, model_id, scene_id, scene_num, detail.get('galleryCount') or 0, sink)

    async def _fetch_actors(self, site: ResolvedSiteInfo, talent: list[Any], sink: list[RawCaptureEntry] | None) -> list[ActorResult]:
        talent = [t for t in talent if isinstance(t, dict) and isinstance(t.get('talent'), dict) and t['talent'].get('talentId')]
        if not talent:
            return []
        paths = [f'/members/models/{t["talent"]["talentId"]}/profile-sm.jpg' for t in talent]
        asset_results: list[Any] = []
        data = await self._gql(site.name, site.base_url, _BATCH_ASSET_QUERY, 'paths', paths, f'[{site.name}] batchAsset (actors)', sink)
        asset_results = (((data or {}).get('asset') or {}).get('batch') or {}).get('result') or []
        actors: list[ActorResult] = []
        for idx, t in enumerate(talent):
            uri = ((asset_results[idx].get('serve') or {}).get('uri') or '') if idx < len(asset_results) and isinstance(asset_results[idx], dict) else ''
            actors.append(ActorResult(name=t['talent'].get('name') or '', photo_url=uri, gender='female'))
        return actors

    async def _fetch_image_urls(
        self, site: ResolvedSiteInfo, model_id: str, scene: str, scene_num: int, gallery_count: int, sink: list[RawCaptureEntry] | None
    ) -> list[str]:
        paths = [f'/members/models/{model_id}/scenes/{scene}/videothumb.jpg']
        for idx in range(1, gallery_count + 1):
            paths.append(f'/members/models/{model_id}/scenes/{scene}/photos/thumbs/{site.name.lower()}-{model_id}-{scene_num}-{idx}.jpg')

        all_results: list[Any] = []
        for i in range(0, len(paths), _CHUNK_SIZE):
            chunk = paths[i : i + _CHUNK_SIZE]
            data = await self._gql(site.name, site.base_url, _BATCH_ASSET_QUERY, 'paths', chunk, f'[{site.name}] batchAsset chunk@{i}', sink)
            all_results.extend((((data or {}).get('asset') or {}).get('batch') or {}).get('result') or [])

        return [r['serve']['uri'] for r in all_results if isinstance(r, dict) and (r.get('serve') or {}).get('uri')]
