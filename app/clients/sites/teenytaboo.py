from __future__ import annotations

import re

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_text, web_search_urls

_WS_RE = re.compile(r'\s+')
_ACTOR_SPLIT_RE = re.compile(r',|\sand\s')


def _slugify(query: str) -> str:
    return _WS_RE.sub('-', query.strip()).lower()


def _normalize_web_url(raw: str) -> str:
    no_join = raw.split('/join.php')[0]
    idx = no_join.rfind('/')
    return no_join[:idx] if idx > 0 else no_join


class TeenyTabooClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        slug = _slugify(ctx.title)
        direct_url = base + ctx.site_info.search_path.replace('{query}', slug)

        seen = {direct_url}
        candidates = [direct_url]
        for raw in await web_search_urls(ctx.title, ctx.site_info):
            normalized = _normalize_web_url(raw)
            if '/video/' in normalized and normalized not in seen:
                seen.add(normalized)
                candidates.append(normalized)

        results: list[SearchResult] = []
        for scene_url in candidates:
            loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] candidate {scene_url}')
            if not loaded:
                continue
            raw = first_text(loaded['sel'], '//h1[contains(@class,"customhcolor")]')
            if not raw:
                continue
            title = raw.replace('-', ' ')
            date_raw = first_text(loaded['sel'], '//span[contains(@class,"date")]')
            release_date = iso_date(date_raw) if date_raw else None
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=ctx.title,
                    display_date=release_date,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([p for p in (scene_url, release_date or ctx.search_date) if p]),
                )
            )
        return results

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//h1[contains(@class,"customhcolor")]')
        return raw.replace('-', ' ') if raw else None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//h2[contains(@class,"customhcolor2")]') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//span[contains(@class,"date")]')
        return iso_date(raw) if raw else None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        raw = scene.sel.xpath('string((//h3)[1])').get() or ''
        if not raw:
            return []
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for piece in _ACTOR_SPLIT_RE.split(raw):
            name = re.sub(r'\d', '', piece).replace('&nbsp', '').replace('\xa0', ' ').strip()
            if name and name not in seen:
                seen.add(name)
                actors.append(ActorResult(name=name))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        images: list[str] = []
        for src in scene.sel.xpath('//center//img/@src').getall():
            s = (src or '').strip()
            if not s:
                continue
            abs_url = absolute_url(s, base)
            if abs_url not in images:
                images.append(abs_url)
        return images
