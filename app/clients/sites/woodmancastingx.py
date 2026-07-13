from __future__ import annotations

import re
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text

STUDIO = 'Woodman Casting X'
_IMAGE_RE = re.compile(r'image:\s*"([^"]+)"')


class WoodmanCastingXClient(Client):
    async def _get_site_data(self, url: str, label: str) -> dict[str, Any] | None:
        first = await self.fetch_and_load(url, None, label)
        if not first:
            return None
        ids = [i for i in (s.strip() for s in first['sel'].xpath('//div[@id]/@id').getall()) if i and i != 'error']
        if not ids:
            return first
        cookie = '; '.join(f'{i}=1' for i in ids)
        retried = await self.fetch_and_load(url, FetchCtx(headers={'Cookie': cookie}), f'{label} (challenge)')
        return retried or first

    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        search_url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        data = await self._get_site_data(search_url, f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not data:
            return
        seen: set[str] = set()
        for a in data['sel'].xpath('//div[contains(@class,"items")]//a[contains(@class,"scene")]'):
            href = first_attr(a, '@href')
            if not href or href.startswith('http'):
                continue
            raw_title = first_attr(a, '(.//img/@alt)[1]')
            if not raw_title:
                continue
            scene_url = absolute_url(href, ctx.site_info.base_url)
            if scene_url in seen:
                continue
            seen.add(scene_url)
            results.append(
                build_search_result(
                    title=raw_title, scene_url=scene_url, query=ctx.title, search_date=ctx.search_date, cur_id=pack_cur_id([scene_url, ctx.search_date or ''])
                )
            )

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        url, _, tail = payload.partition('|')
        date = tail.strip()
        data = await self._get_site_data(url, f'[{site.name}] detail {url}')
        if not data:
            return None
        return LoadedScene(url=url, site=site, scene_date=date or None, capture=ctx.capture if ctx else None, sel=data['sel'], html=data['html'])

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = first_text(scene.sel, '//h1') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//p[contains(@class,"description")]')
        metadata.summary = ' '.join(raw.split()) or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        trailing = first_attr(scene.sel, '(//span[contains(.,"Published")]/following-sibling::text())[1]')
        raw = trailing.lstrip(':').strip()
        if raw:
            parsed = iso_date(raw)
            if parsed:
                metadata.release_date = parsed
                return
        if scene.scene_date:
            metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//div[contains(@class,"tags")]//a')]
        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        base = scene.site.base_url
        blocks = scene.sel.xpath('//div[contains(@class,"block_girls_videos")]//a[contains(@class,"girl_item")]')
        if blocks:
            actors: list[ActorResult] = []
            seen: set[str] = set()
            for a in blocks:
                name = first_text(a, './/span[contains(@class,"name")]')
                if not name or name in seen:
                    continue
                seen.add(name)
                src = first_attr(a, '(.//img/@src)[1]')
                photo = (absolute_url(src, base)) if src else ''
                actors.append(ActorResult(name=name, photo_url=photo))
            metadata.actors = actors
            return
        crumb = first_text(scene.sel, '//div[@id="breadcrumb"]//span[contains(@class,"crumb")]')
        name = crumb.split('-')[0].strip()
        metadata.actors = [ActorResult(name=name)] if name else []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        base = scene.site.base_url
        coll = self.image_collector(lambda raw: absolute_url((raw or '').strip(), base))
        for poster in scene.sel.xpath('//video[contains(@class,"player_video")]/@poster').getall():
            coll['push'](poster)
        for script in scene.sel.xpath('//script/text()').getall():
            if 'var player' not in script:
                continue
            m = _IMAGE_RE.search(script)
            if m:
                coll['push'](m.group(1).strip())
        metadata.raw_image_urls = coll['list']
