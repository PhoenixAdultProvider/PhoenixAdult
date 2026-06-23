from __future__ import annotations

import re

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_text

STUDIO = 'Swallow Bay'
_SLUG_RE = re.compile(r"[\s']")
_ORDINAL_RE = re.compile(r'(\d+)(st|nd|rd|th)')
_DATE_PREFIX_RE = re.compile(r'^Date:\s*', re.IGNORECASE)
# Exact class-token match so "content-models" never catches "content-models-photos".
_MODELS_XP = '//div[contains(concat(" ", normalize-space(@class), " "), " content-models ")]/a'


def _parse_date(raw: str) -> str | None:
    cleaned = _ORDINAL_RE.sub(r'\1', raw)
    return iso_date(cleaned, '%d %b %Y') or iso_date(cleaned)


class SwallowBayClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        slug = _SLUG_RE.sub('-', ctx.title.strip().lower())
        scene_url = base + ctx.site_info.search_path.replace('{query}', slug)
        loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] direct-URL {slug}')
        if not loaded:
            return []
        title = (loaded['sel'].xpath('(//meta[@name="twitter:image:alt"]/@content)[1]').get() or '').strip()
        if not title:
            return []
        return [build_search_result(title=title, scene_url=scene_url, query=ctx.title, search_date=ctx.search_date, score=100, cur_id=pack_cur_id([scene_url]))]

    # ── Context loader (default fetches the scene URL) ─────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        url = payload.split('|', 1)[0]
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture if ctx else None), f'[{site.name}] detail {url}')
        if not loaded:
            return None
        return LoadedScene(url=url, site=site, capture=ctx.capture if ctx else None, sel=loaded['sel'], html=loaded['html'])

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//meta[@name="twitter:image:alt"]/@content)[1]').get() or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"content-desc") and contains(@class,"more-desc")]') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [STUDIO]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = _DATE_PREFIX_RE.sub('', first_text(scene.sel, '//div[contains(@class,"content-date")]'))
        return _parse_date(raw) if raw else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//div[contains(@class,"box")]//a')]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        entries: list[ActorResult] = []
        for el in scene.sel.xpath(_MODELS_XP):
            name = (el.xpath('@title').get() or '').strip()
            photo = ''
            if name:
                photo = (scene.sel.xpath(f'(//div[contains(@class,"content-models-photos")]//a[@title="{name}"]//span//img/@src)[1]').get() or '').strip()
            entries.append(ActorResult(name=name, photo_url=photo))
        return self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        poster = (scene.sel.xpath('(//meta[@property="og:image"]/@content)[1]').get() or '').strip()
        return [poster] if poster else []
