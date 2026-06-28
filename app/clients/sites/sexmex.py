from __future__ import annotations

import re
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date, load_site_json
from app.utils.helpers.html_helpers import first_text

_TITLE_FIXES: dict[str, str] = load_site_json(__file__, 'sexmex_title_fixes')
_TITLE_KEYWORDS: list[str] = load_site_json(__file__, 'sexmex_title_keywords')


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
        href = (source.xpath('(.//a/@href)[1]').get() or '').strip()
        if not href:
            return ''
        return href if href.startswith('http') else absolute_url(href, loaded.site.base_url)

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = first_text(source, './/p[contains(@class,"scene-date")]')
        return iso_date(raw) if raw else None

    # ── Detail field hooks ────────────────────────────────────────────────────

    def _actor_names(self, scene: LoadedScene) -> list[str]:
        assert scene.sel is not None
        return [
            (a.xpath('normalize-space(.)').get() or '').strip()
            for a in scene.sel.xpath('//p[@class]//a')
            if (a.xpath('normalize-space(.)').get() or '').strip()
        ]

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//h4')
        if not raw:
            return None
        return _cleanup_title(raw, self._actor_names(scene)) or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"panel-body")]//p') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        raw = scene.sel.xpath('(//meta[@name="keywords"]/@content)[1]').get() or ''
        actor_lower = {n.lower() for n in self._actor_names(scene)}
        genres: list[str] = []
        for raw_g in raw.split(','):
            g = raw_g.strip()
            if g and g.lower() not in actor_lower and g not in genres:
                genres.append(g)
        return genres

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath('//p[@class]//a'):
            name = (el.xpath('normalize-space(.)').get() or '').strip()
            href = (el.xpath('@href').get() or '').strip()
            if not name or not href or name in seen:
                continue
            seen.add(name)
            actor_page = await self.fetch_and_load(f'{base}/tour/{href}', FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
            photo = (actor_page['sel'].xpath('(//img/@src)[1]').get() or '').strip() if actor_page else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        images: list[str] = []

        def push(raw: str) -> None:
            raw = (raw or '').strip()
            if not raw:
                return
            abs_url = (raw if raw.startswith('http') else absolute_url(raw, base)).split('?')[0]
            if abs_url and abs_url not in images:
                images.append(abs_url)

        for raw in scene.sel.xpath('//div[contains(@class,"thumbnail")]//img/@src').getall():
            push(raw)
        for raw in scene.sel.xpath('//video/@poster').getall():
            push(raw)
        return images
