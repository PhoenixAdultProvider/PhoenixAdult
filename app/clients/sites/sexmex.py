from __future__ import annotations

import re
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_attr, first_text

_TITLE_FIXES: dict[str, str] = {' Analìa ': ' Analia ', ' Kary ': ' Kari '}
_TITLE_KEYWORDS: list[str] = ['casting', 'debut', 'mesmerized', 'porn casting', 'pov']


def _apply_title_fixes(raw: str) -> str:
    out = raw
    for find, replace in _TITLE_FIXES.items():
        out = out.replace(find, replace)
    return out


def _cleanup_title(raw: str, actor_names: list[str]) -> str:
    fixed = _apply_title_fixes(raw)
    if any(fixed.lower().startswith(kw) for kw in _TITLE_KEYWORDS):
        return fixed.replace('.', ':')
    out = fixed
    for name in actor_names:
        escaped = re.escape(name)
        out = re.split(rf'\.\s{escaped}', out, flags=re.IGNORECASE)[0]
        tail = re.split(rf'{escaped}\s\.', out, flags=re.IGNORECASE)
        out = tail[-1]
    return out.strip()


class SexMexClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        encoded = ctx.title.lower().replace(' ', '+')
        url = base + ctx.site_info.search_path.replace('{query}', encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//div[contains(@class,"thumbnail")]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/h5')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//a/@href)[1]')
        if not href:
            return ''
        return absolute_url(href, loaded.site.base_url)

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = first_text(source, './/p[contains(@class,"scene-date")]')
        return iso_date(raw) if raw else None

    # ── Detail field hooks ────────────────────────────────────────────────────

    def _actor_names(self, scene: LoadedScene) -> list[str]:
        assert scene.sel is not None
        return [first_attr(a, 'normalize-space(.)') for a in scene.sel.xpath('//p[@class]//a') if first_attr(a, 'normalize-space(.)')]

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//h4')
        if not raw:
            return
        metadata.title = _cleanup_title(raw, self._actor_names(scene)) or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = first_text(scene.sel, '//div[contains(@class,"panel-body")]//p') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name or ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = scene.sel.xpath('(//meta[@name="keywords"]/@content)[1]').get() or ''
        actor_lower = {n.lower() for n in self._actor_names(scene)}
        genres: list[str] = []
        for raw_g in raw.split(','):
            g = raw_g.strip()
            if g and g.lower() not in actor_lower and g not in genres:
                genres.append(g)
        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath('//p[@class]//a'):
            name = first_attr(el, 'normalize-space(.)')
            href = first_attr(el, '@href')
            if not name or not href or name in seen:
                continue
            seen.add(name)
            actor_page = await self.fetch_and_load(f'{base}/tour/{href}', FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
            photo = first_attr(actor_page['sel'], '(//img/@src)[1]') if actor_page else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        coll = self.image_collector(lambda raw: absolute_url((raw or '').strip(), base).split('?')[0])
        for raw in scene.sel.xpath('//div[contains(@class,"thumbnail")]//img/@src').getall():
            coll['push'](raw)
        for raw in scene.sel.xpath('//video/@poster').getall():
            coll['push'](raw)
        metadata.raw_image_urls = coll['list']
