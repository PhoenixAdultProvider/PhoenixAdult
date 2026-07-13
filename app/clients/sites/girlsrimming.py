from __future__ import annotations

import re

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import build_search_result, iso_date, join_url, pack_cur_id, slugify
from app.utils.helpers.html_helpers import first_attr, meta_content, web_search_urls

_ID_SEPARATOR = ' Id '
_WORD_RE = re.compile(r'\w\S*')


def _py_title(s: str) -> str:
    return _WORD_RE.sub(lambda m: m.group(0)[0].upper() + m.group(0)[1:].lower(), s)


class GirlsRimmingClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        direct = base + ctx.site_info.search_path.replace('{query}', slugify(ctx.title))
        candidates = [direct]
        for u in await web_search_urls(ctx.title, ctx.site_info, include=['/trailers/']):
            lc = u.lower()
            if lc not in candidates:
                candidates.append(lc)

        for scene_url in candidates:
            page = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] candidate {scene_url}')
            if not page or page['html'].strip() == 'Page not found':
                continue
            title = first_attr(page['sel'], '(//h2[contains(@class,"title")]/text())[1]')
            if not title:
                continue
            date = ctx.search_date
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=ctx.title,
                    display_date=date,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
                )
            )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = first_attr(scene.sel, '(//h2[contains(@class,"title")]/text())[1]') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = meta_content(scene.sel, 'description') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Girls Rimming'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    def _keywords(self, scene: LoadedScene) -> str:
        assert scene.sel is not None
        return scene.sel.xpath('(//meta[@name="keywords"]/@content)[1]').get() or ''

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        genres: list[str] = []
        for part in self._keywords(scene).split(','):
            entry = part.strip()
            if not entry or _ID_SEPARATOR in entry:
                continue
            titled = _py_title(entry)
            if titled not in genres:
                genres.append(titled)
        if 'Rim Job' not in genres:
            genres.append('Rim Job')
        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for part in self._keywords(scene).split(','):
            entry = part.strip()
            if _ID_SEPARATOR not in entry:
                continue
            name = entry.split(_ID_SEPARATOR)[0].strip()
            if not name or name in seen:
                continue
            seen.add(name)
            actors.append(ActorResult(name=name, photo_url=await self._resolve_actor_photo(name, scene)))
        metadata.actors = actors

    async def _resolve_actor_photo(self, name: str, scene: LoadedScene) -> str:
        base = scene.site.base_url.rstrip('/')
        slug = re.sub(r'\s+', '-', name.lower())
        direct_url = f'{base}/tour/models/{slug}.html'
        page = await self.fetch_and_load(direct_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor-direct {name}')
        if not page or page['html'].strip() == 'Page not found':
            page = None
            for u in (x.lower() for x in await web_search_urls(name, scene.site, include=['/models/'])):
                candidate = await self.fetch_and_load(u, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor-fallback {name}')
                if candidate and candidate['html'].strip() != 'Page not found':
                    page = candidate
                    break
        if not page:
            return ''
        raw = first_attr(page['sel'], '(//div[contains(@class,"model_picture")]//img/@src0_3x)[1]')
        return join_url(raw, base) if raw else ''

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        coll = self.image_collector(lambda raw: join_url(raw, scene.site.base_url))
        for raw in scene.sel.xpath('//div[@id="fakeplayer"]//img/@src0_3x').getall():
            coll['push']((raw or '').strip())
        metadata.raw_image_urls = coll['list']
