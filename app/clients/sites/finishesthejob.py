from __future__ import annotations

import re
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, title_distance_score
from app.utils.helpers.html_helpers import first_attr, first_text

_NON_ALNUM_RE = re.compile(r'[^a-z0-9]', re.IGNORECASE)
_SUBSITE_RE = re.compile(r'scene/(.*?)/')


def _norm(s: str) -> str:
    return _NON_ALNUM_RE.sub('', s).lower()


class FinishesTheJobClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//div[contains(@class,"scene")]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/h3[@itemprop="name"]')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//a/@href)[1]')
        if not href:
            return ''
        return absolute_url(href, loaded.site.base_url)

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        return loaded.ctx.search_date

    async def fetch_search_score(self, source: Any, loaded: LoadedSearch) -> float | None:
        title = first_text(source, './/h3[@itemprop="name"]')
        footer_href = first_attr(source, '(.//div[contains(@class,"card-footer")]//a/@href)[1]')
        m = _SUBSITE_RE.search(footer_href)
        sub_site = m.group(1) if m else ''
        bad_subsite = _norm(sub_site) != _norm(loaded.site.name)
        return title_distance_score(loaded.ctx.title, title) - (10 if bad_subsite else 0)

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//span[@itemprop="name"]') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//p[@itemprop="description"]') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'Finishes The Job'

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        return scene.scene_date or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        entries = [ActorResult(name=a.xpath('normalize-space(.)').get() or '') for a in scene.sel.xpath('//h2[contains(.,"Starring")]//a')]
        return self.dedup_people(entries)

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//p[contains(.,"Categories")]//a')]
        return self.dedup_strings(values)

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []

        def push(raw: str) -> None:
            raw = (raw or '').strip()
            if not raw:
                return
            abs_url = absolute_url(raw, scene.site.base_url)
            if abs_url not in images:
                images.append(abs_url)

        for el in scene.sel.xpath('//video[@poster]'):
            push(el.xpath('@poster').get() or '')

        title = first_text(scene.sel, '//span[@itemprop="name"]').lower()
        if title:
            for el in scene.sel.xpath('//div[contains(@class,"first-set")]//img'):
                alt = first_attr(el, '@alt').lower()
                if alt == title:
                    push(el.xpath('@src').get() or '')
        return images
