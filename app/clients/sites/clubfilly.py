from __future__ import annotations

import re
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_attr, first_text

_TITLE_XP = '//div[contains(@class,"fltWrap")]/h1/span'
_DESC_PREFIX = re.compile(r'^Description:\s*')
_DATE_PREFIX = re.compile(r'^Release Date\s*:\s*')
_STARRING_PREFIX = re.compile(r'^Starring:\s*')


class ClubFillyClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        scene_url = base + ctx.site_info.search_path.replace('{query}', ctx.title.strip())
        loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] directScene {scene_url}')
        if not loaded:
            return None
        if not first_text(loaded['sel'], _TITLE_XP):
            return None
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=[loaded['sel']], capture=ctx.capture, extra=scene_url)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, _TITLE_XP)

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        return str(loaded.extra)

    async def fetch_search_score(self, source: Any, loaded: LoadedSearch) -> float | None:
        return 100

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = first_text(scene.sel, _TITLE_XP) or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//p[contains(@class,"description")]')
        if not raw:
            return
        metadata.summary = _DESC_PREFIX.sub('', raw).strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'ClubFilly'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//div[contains(@class,"fltRight")]')
        date_text = _DATE_PREFIX.sub('', raw).strip()
        metadata.release_date = iso_date(date_text, '%Y-%m-%d') or None

    def _collect_actors(self, scene: LoadedScene) -> list[ActorResult]:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//p[contains(@class,"starring")]')
        text = _STARRING_PREFIX.sub('', raw).strip()
        if not text:
            return []
        names = [n.strip() for n in text.split(',') if n.strip()]
        return [ActorResult(name=name) for name in names]

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.actors = self._collect_actors(scene)

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        genres = ['Lesbian']
        n = len(self._collect_actors(scene))
        if n == 3:
            genres.append('Threesome')
        elif n == 4:
            genres.append('Foursome')
        elif n > 4:
            genres.append('Orgy')
        metadata.genres = genres

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        images: list[str] = []
        for el in scene.sel.xpath('//ul[@id="lstSceneFocus"]/li/img'):
            src = first_attr(el, '@src')
            if not src:
                continue
            abs_url = absolute_url(src, scene.site.base_url)
            if abs_url not in images:
                images.append(abs_url)
        metadata.raw_image_urls = images
