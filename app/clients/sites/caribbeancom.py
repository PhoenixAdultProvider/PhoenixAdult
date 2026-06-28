from __future__ import annotations

import re
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url
from app.utils.helpers.html_helpers import first_text

_UPLOAD_DATE_RE = re.compile(r'(\d{4})/(\d{2})/(\d{2})')


class CaribbeancomClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        scene_id = (ctx.full_title or ctx.title).replace(' ', '-')
        scene_url = base + ctx.site_info.search_path.replace('{query}', scene_id)
        loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] directScene {scene_url}')
        if not loaded:
            return None
        if not first_text(loaded['sel'], '//title'):
            return None
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=[loaded['sel']], capture=ctx.capture, extra=scene_url)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, '//title')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        return str(loaded.extra)

    async def fetch_search_score(self, source: Any, loaded: LoadedSearch) -> float | None:
        return 100

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//title') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'caribbeancom'

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return 'caribbeancom'

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return ['caribbeancom']

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//span[@itemprop="uploadDate"]')
        if not raw:
            return None
        m = _UPLOAD_DATE_RE.search(raw)
        return f'{m.group(1)}-{m.group(2)}-{m.group(3)}' if m else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//a[@itemprop="genre"]')]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        entries: list[ActorResult] = []
        for a in scene.sel.xpath('//a[@itemprop="actor"]'):
            text = first_text(a, './/span[@itemprop="name"]')
            for name in (n.strip() for n in text.split(',')):
                if name:
                    entries.append(ActorResult(name=name))
        return self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []
        constructed = scene.url.replace('/eng', '').replace('index.html', 'images/poster_en.jpg')
        if constructed != scene.url:
            images.append(constructed)
        for el in scene.sel.xpath('//img[contains(@class,"gallery-image")]'):
            src = (el.xpath('@src').get() or '').strip()
            if not src:
                continue
            abs_url = absolute_url(src, scene.site.base_url)
            if abs_url not in images:
                images.append(abs_url)
        return images
