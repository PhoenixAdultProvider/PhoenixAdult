from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_text
from app.utils.processors.title_case import title_case

_ACTORS_DATA = Path(__file__).parent / '_data' / 'json' / 'momcomesfirst_actors.json'
_ACTORS: set[str] = set(json.loads(_ACTORS_DATA.read_text(encoding='utf-8')))


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
        href = (source.xpath('(.//h2//a/@href)[1]').get() or '').strip()
        if not href:
            return ''
        return href if href.startswith('http') else absolute_url(href, loaded.site.base_url)

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        return iso_date(first_text(source, './/p//span'), '%b %d, %Y')

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//h1') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        parts: list[str] = []
        for p in scene.sel.xpath('//div[contains(@class,"entry-content")]//p'):
            t = (p.xpath('normalize-space(.)').get() or '').strip()
            if t and 'starring' not in t.lower():
                parts.append(t)
        return '\n'.join(parts) or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'Mom Comes First'

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return ['Mom Comes First']

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//span[contains(@class,"published")]')
        return (iso_date(raw, '%b %d, %Y') if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres: list[str] = []
        for a in scene.sel.xpath('//a[contains(@rel,"tag")]'):
            g = title_case((a.xpath('normalize-space(.)').get() or '').strip())
            if g and g.lower() not in _ACTORS and g not in genres:
                genres.append(g)
        return genres

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        names: list[str] = []
        for a in scene.sel.xpath('//a[contains(@rel,"tag")]'):
            g = title_case((a.xpath('normalize-space(.)').get() or '').strip())
            if g and g.lower() in _ACTORS:
                names.append(g)

        paras = scene.sel.xpath('//div[contains(@class,"entry-content")]//p')
        if paras:
            last_p = paras[-1].xpath('normalize-space(.)').get() or ''
            if 'starring' in last_p.lower():
                tail = last_p.split('Starring')[-1].split('*')[0]
                names.extend(n.strip() for n in tail.split('&'))

        actors: list[ActorResult] = []
        seen: set[str] = set()
        for name in names:
            name = name.strip()
            if name and name.lower() not in seen:
                seen.add(name.lower())
                actors.append(ActorResult(name=name))
        return actors
