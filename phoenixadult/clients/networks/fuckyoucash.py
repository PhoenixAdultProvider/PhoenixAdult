from __future__ import annotations

from typing import Any

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.data18 import mapping_slug
from phoenixadult.utils.helpers.helpers import build_search_result, dict_values_from_key, iso_date, load_data, pack_cur_id, slugify
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.processors.actor_strip import actor_strip_candidates

_GENRES: dict[str, list[str]] = load_data(__file__, 'fuckyoucash_genres')
_DATA18_NAMES = {'Porn+': 'PornPlus'}
_ACTORS_REPLACE: dict[str, tuple[str, str]] = {
    '40oz-zombie-booty': ('Vanessa', 'Vanessa Cruz'),
    'double-o-negro-mammoth-bootay': ('Vanessa', 'Vanessa Monet'),
    'juicy-ass-moon-bounce': ('Zo', 'Daiquiri Holland & Vanessa Monet'),
}


def _query_slug(title: str) -> str:
    return slugify(title.lower().replace("'s", ' s').replace("'", '').replace('.', ''))


def _slug_candidates(title: str) -> list[str]:
    return list(dict.fromkeys(slug for slug in (_query_slug(form) for form in actor_strip_candidates(title)) if slug))


class FuckYouCashClient(Client):
    async def _release(self, base: str, slug: str, capture: Any, fallback: str = '') -> dict[str, Any] | None:
        hosts = [host for host in (base, fallback) if host]
        head, _sep, tail = slug.rpartition('-')
        doubled = f'{head}--{tail}' if '-' in slug and '--' not in slug else ''
        for candidate in (slug, doubled):
            if not candidate:
                continue
            for host in hosts:
                data = await self.fetch_json(f'{host}/api/releases/{candidate}', FetchCtx(capture=capture), headers={'x-site': host})
                if isinstance(data, dict) and data.get('title'):
                    return data

        return None

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        title = search_data.title

        release: dict[str, Any] | None = None
        slug = ''
        for candidate in _slug_candidates(title):
            release = await self._release(base, candidate, search_data.capture, search_data.site_info.fallback_url)
            if release:
                slug = candidate
                break

        if not release:
            return

        date = iso_date(release.get('releasedAt') or '')

        results.append(
            build_search_result(
                site=search_data.site_info,
                title=(release.get('title') or '').strip(),
                scene_url=f'{base}/api/releases/{slug}',
                query=title,
                display_date=date,
                search_date=search_data.search_date,
                cur_id=pack_cur_id([slug, date or '']),
            )
        )

    # ── Context Loader — Re-Fetch the Release JSON by Slug ──────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        base = site.base_url.rstrip('/')
        pipe = payload.find('|')
        slug = payload[:pipe] if pipe >= 0 else payload
        scene_date = payload[pipe + 1 :].strip() if pipe >= 0 else ''
        release = await self._release(base, slug, ctx.capture if ctx else None, site.fallback_url)
        if not release:
            return None

        return LoadedScene(
            url=f'{base}/api/releases/{slug}',
            site=site,
            scene_date=scene_date or None,
            capture=ctx.capture if ctx else None,
            sel=None,
            html='',
            extra=release,
            source_json=release,
        )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _data(self, scene: LoadedScene) -> dict[str, Any]:
        return scene.extra or {}

    def _sub_site(self, scene: LoadedScene) -> str:
        if not scene.site.sub_group:
            return ''
        sponsor = str((self._data(scene).get('sponsor') or {}).get('name') or '').strip()
        return sponsor if sponsor and sponsor != scene.site.sub_group else ''

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.title = str(self._data(scene).get('title') or '').strip()

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        summary = str(self._data(scene).get('description') or '').strip()

        metadata.summary = summary if summary and summary.lower() != 'n/a' else ''

    def studio_for(self, site: ResolvedSiteInfo) -> str | None:
        return site.sub_group or site.name

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = self.studio_for(scene.site) or scene.site.name

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._sub_site(scene)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        studio = scene.site.sub_group or scene.site.name

        metadata.collections = [self._sub_site(scene) or studio]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        date = iso_date(self._data(scene).get('releasedAt') or '')

        metadata.release_date = date or (iso_date(scene.scene_date) or scene.scene_date if scene.scene_date else None)

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.genres = self.dedup_strings(
            [
                str(genre_name).replace('_', ' ').replace('-', ' ').strip()
                for genre_name in [*(self._data(scene).get('tags') or []), *_GENRES.get(scene.site.name, [])]
            ]
        )

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        release = self._data(scene)
        title = str(release.get('title') or '')
        rename = dict_values_from_key(_ACTORS_REPLACE, _query_slug(title))
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for actor in release.get('actors') or []:
            for actor_name in (part.strip() for part in str(actor.get('name') or '').split('&')):
                credited = rename[1] if rename and actor_name.casefold() == rename[0].casefold() else actor_name
                if credited != actor_name:
                    logger.info(scene.site.name, f'recredited "{actor_name}" as "{credited}" on "{title}"')
                for final_name in (part.strip() for part in credited.split('&')):
                    if final_name and final_name not in seen:
                        seen.add(final_name)
                        actors.append(ActorResult(name=final_name))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        release = self._data(scene)
        images = self.image_collector()
        images.push(release.get('posterUrl'))
        for img in release.get('thumbUrls') or []:
            images.push(img)

        metadata.art = images.items

        # Posters from Data18
        await self.enrich_from_data18(
            metadata,
            scene.site,
            scene_id=mapping_slug(metadata.title, metadata.tagline, metadata),
            providers=list(dict.fromkeys(_DATA18_NAMES.get(p, p) for p in (metadata.tagline, metadata.studio, scene.site.name) if p)),
        )
