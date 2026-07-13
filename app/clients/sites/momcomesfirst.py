from __future__ import annotations

import re
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date, load_site_json
from app.utils.helpers.html_helpers import first_attr, first_text
from app.utils.processors.title_case import title_case

_ACTORS: set[str] = set(load_site_json(__file__, 'momcomesfirst_actors'))


class MomComesFirstClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        title_no_actors = ' '.join(ctx.title.replace('sons', '').replace('mothers', '').replace('moms', '').split(' ')[2:]).lower()
        encoded = title_no_actors.replace(' ', '+').replace("'", '')
        loaded = await self.fetch_and_load(f'{base}/?s={encoded}', FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//article'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/h2')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//h2//a/@href)[1]')
        if not href:
            return ''
        return absolute_url(href, loaded.site.base_url)

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        return iso_date(first_text(source, './/p//span'), '%b %d, %Y')

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = first_text(scene.sel, '//h1') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        parts: list[str] = []
        for p in scene.sel.xpath('//div[contains(@class,"entry-content")]//p'):
            t = first_attr(p, 'normalize-space(.)')
            if t and 'starring' not in t.lower():
                parts.append(t)
        metadata.summary = '\n'.join(parts) or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Mom Comes First'

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = ['Mom Comes First']

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//span[contains(@class,"published")]')
        metadata.release_date = (iso_date(raw, '%b %d, %Y') if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        genres: list[str] = []
        for a in scene.sel.xpath('//a[contains(@rel,"tag")]'):
            g = title_case(first_attr(a, 'normalize-space(.)'))
            if g and g.lower() not in _ACTORS and g not in genres:
                genres.append(g)
        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        names: list[str] = []
        for a in scene.sel.xpath('//a[contains(@rel,"tag")]'):
            g = title_case(first_attr(a, 'normalize-space(.)'))
            if g and g.lower() in _ACTORS:
                names.append(g)

        paras = scene.sel.xpath('//div[contains(@class,"entry-content")]//p')
        if paras:
            last_p = paras[-1].xpath('normalize-space(.)').get() or ''
            if 'starring' in last_p.lower():
                tail = re.split(r'starring', last_p, maxsplit=1, flags=re.IGNORECASE)[-1].split('*')[0]
                names.extend(n.strip() for n in tail.split('&'))

        actors: list[ActorResult] = []
        seen: set[str] = set()
        for name in names:
            name = name.strip()
            if name and name.lower() not in seen:
                seen.add(name.lower())
                actors.append(ActorResult(name=name))
        metadata.actors = actors
