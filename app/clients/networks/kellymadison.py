from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_attr

STUDIO = 'Kelly Madison Productions'
_NATS_COOKIE = 'nats=MC4wLjMuNTguMC4wLjAuMC4w'

_POSTER_TEMPLATES: list[str] = [
    'https://tour-content-cdn.kellymadisonmedia.com/episode/poster_image/{slug}/poster.jpg',
    'https://tour-content-cdn.kellymadisonmedia.com/episode/episode_thumb_image_1/{slug}/1.jpg',
    'https://tour-content-cdn.kellymadisonmedia.com/episode/episode_thumb_image_1/{slug}/01.jpg',
]


def _tagline_from_title(title: str, site_name: str) -> str:
    lc = title.lower()
    if 'teenfidelity' in lc:
        return 'TeenFidelity'
    if 'kelly madison' in lc:
        return 'Kelly Madison'
    return site_name


class KellyMadisonClient(Client):
    def __init__(self) -> None:
        super().__init__({'Cookie': _NATS_COOKIE})

    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        scene_id = ctx.scene_id or ''
        if not scene_id and ctx.full_title:
            first_tok = ctx.full_title.strip().split()[0] if ctx.full_title.strip() else ''
            stripped = re.sub(r'^e', '', first_tok, flags=re.IGNORECASE)
            if stripped and stripped.isdigit():
                scene_id = stripped
        url = base + ctx.site_info.search_path.replace('{query}', quote(ctx.title.strip()))
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {url}')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//a[contains(@class,"video-card")]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture, extra={'scene_id': scene_id})

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath('(.//h3)[1]').xpath('string(.)').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '@href')
        return absolute_url(href, loaded.site.base_url) if href else ''

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = (source.xpath('(.//time)[1]').xpath('string(.)').get() or '').strip()
        return iso_date(raw, '%m/%d/%y') if raw else loaded.ctx.search_date

    async def fetch_search_score(self, source: Any, loaded: LoadedSearch) -> float | None:
        scene_id = (loaded.extra or {}).get('scene_id') or ''
        if not scene_id:
            return None
        episode_id = (source.xpath('(.//span[contains(@class,"video-title")])[1]').xpath('string(.)').get() or '').split('#')[-1].strip()
        href = first_attr(source, '@href')
        scene_url = absolute_url(href, loaded.site.base_url) if href else ''
        search_id = scene_url.rstrip('/').split('/')[-1]
        return 100 if scene_id in (episode_id, search_id) else None

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//h1[contains(@class,"title")])[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//div[contains(.,"Episode Summary")]/p)[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//h1[contains(@class,"title")])[1]').xpath('string(.)').get() or '').strip()
        return _tagline_from_title(raw, scene.site.name)

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [await self.fetch_tagline(scene) or scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//p[contains(.,"Published")]//strong)[1]').xpath('string(.)').get() or '').strip()
        if raw:
            return iso_date(raw, '%Y-%m-%d') or iso_date(raw)
        return (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres = ['Hardcore', 'Heterosexual']
        cast = len(scene.sel.xpath('//p[contains(.,"Starring")]//a[contains(@href,"/models/")]'))
        if cast == 3:
            genres.append('Threesome')
        elif cast == 4:
            genres.append('Foursome')
        elif cast > 4:
            genres.append('Orgy')
        return genres

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        refs: list[tuple[str, str]] = []
        for el in scene.sel.xpath('//p[contains(.,"Starring")]//a[contains(@href,"/models/")]'):
            name = first_attr(el, 'normalize-space(.)')
            href = first_attr(el, '@href')
            if name and href:
                refs.append((name, href))
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for name, href in refs:
            if name in seen:
                continue
            seen.add(name)
            actor_url = absolute_url(href, base)
            page = await self.fetch_and_load(actor_url, None, f'[{scene.site.name}] actor {name}')
            raw = first_attr(page['sel'], '(//div[contains(@class,"one")]//img)[1]/@src') if page else ''
            photo = (absolute_url(raw, base)) if raw else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        slug = scene.url.rstrip('/').split('/')[-1]
        if not slug:
            return None
        return [t.replace('{slug}', slug) for t in _POSTER_TEMPLATES]
