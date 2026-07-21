from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, iso_date, load_data, pack_cur_id, slugify

_GENRES: dict[str, list[str]] = load_data(__file__, 'pornpros_genres')


def _query_slug(title: str) -> str:
    return slugify(title.lower().replace("'s", ' s').replace("'", '').replace('.', ''))


class PornProsClient(Client):
    async def _release(self, base: str, slug: str, capture: Any) -> dict[str, Any] | None:
        headers = {'x-site': base}
        data = await self.fetch_json(f'{base}/api/releases/{slug}', FetchCtx(capture=capture), headers=headers)
        if isinstance(data, dict) and data.get('title'):
            return data

        # Legacy fallback: a single '-' often needs doubling to hit the release.
        if '-' in slug and '--' not in slug:
            head, _sep, tail = slug.rpartition('-')
            data = await self.fetch_json(f'{base}/api/releases/{head}--{tail}', FetchCtx(capture=capture), headers=headers)
            if isinstance(data, dict) and data.get('title'):
                return data

        return None

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        title = search_data.title
        if search_data.site_info.name != 'Casting Couch-X':
            title = ' '.join(title.split(' ')[2:])
            if title.startswith('and '):
                title = ' '.join(title.split(' ')[3:])

        slug = _query_slug(title)
        release = await self._release(base, slug, search_data.capture)
        if not release:
            return

        date = iso_date(release.get('releasedAt') or '')

        results.append(
            build_search_result(
                title=(release.get('title') or '').strip(),
                scene_url=f'{base}/api/releases/{slug}',
                query=title,
                display_date=date,
                search_date=search_data.search_date,
                cur_id=pack_cur_id([slug, date or '']),
            )
        )

    # ── Context loader — re-fetch the release JSON by slug ──────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        base = site.base_url.rstrip('/')
        pipe = payload.find('|')
        slug = payload[:pipe] if pipe >= 0 else payload
        scene_date = payload[pipe + 1 :].strip() if pipe >= 0 else ''
        release = await self._release(base, slug, ctx.capture if ctx else None)
        if not release:
            return None

        return LoadedScene(
            url=f'{base}/api/releases/{slug}', site=site, scene_date=scene_date or None, capture=ctx.capture if ctx else None, sel=None, html='', extra=release
        )

    def _r(self, scene: LoadedScene) -> dict[str, Any]:
        return scene.extra or {}

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.title = str(self._r(scene).get('title') or '').strip()

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        summary = str(self._r(scene).get('description') or '').strip()

        metadata.summary = summary if summary and summary.lower() != 'n/a' else ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'PornPros'

    def _tagline(self, scene: LoadedScene) -> str:
        return str((self._r(scene).get('sponsor') or {}).get('name') or '').strip()

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline(scene) or None

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        t = self._tagline(scene)

        metadata.collections = [t] if t else None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        d = iso_date(self._r(scene).get('releasedAt') or '')

        metadata.release_date = d or (iso_date(scene.scene_date) or scene.scene_date if scene.scene_date else None)

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.genres = self.dedup_strings(
            [
                str(genre_name).replace('_', ' ').replace('-', ' ').strip()
                for genre_name in [*(self._r(scene).get('tags') or []), *_GENRES.get(scene.site.name, [])]
            ]
        )

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for a in self._r(scene).get('actors') or []:
            raw = str(a.get('name') or '').strip()
            names = [p.strip() for p in raw.split('&')] if '&' in raw else [raw]
            for actor_name in names:
                if actor_name and actor_name not in seen:
                    seen.add(actor_name)
                    actors.append(ActorResult(name=actor_name))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        # Full URLs kept incl. query strings (image-URL policy); legacy '?'-strip dropped.
        release = self._r(scene)
        images = self.image_collector()
        images['push'](release.get('posterUrl'))
        for img in release.get('thumbUrls') or []:
            images['push'](img)

        metadata.art = images['list']
