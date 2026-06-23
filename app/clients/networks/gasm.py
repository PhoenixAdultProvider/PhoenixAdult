from __future__ import annotations

import json
from pathlib import Path

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, slugify, title_distance_score
from app.utils.processors.title_case import title_case

STUDIO = 'GASM'
_DATE_FMT = '%b %d, %Y'

_DATA = Path(__file__).parent / '_data' / 'json'
_CHANNELS: dict[str, str] = json.loads((_DATA / 'gasm_channels.json').read_text(encoding='utf-8'))


class GasmClient(Client):
    def __init__(self) -> None:
        super().__init__({'Cookie': 'WarningModal=true'})

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')

        if ctx.scene_id:
            scene_url = f'{base}/post/details/{ctx.scene_id}'
            loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] direct {scene_url}')
            if not loaded:
                return []
            title = (loaded['sel'].xpath('(//h1[contains(@class,"post_title")]//span)[1]').xpath('string(.)').get() or '').strip()
            if not title:
                return []
            date_raw = (loaded['sel'].xpath('(//h3[contains(@class,"post_date")])[1]').xpath('string(.)').get() or '').strip()
            date_iso = (iso_date(date_raw, _DATE_FMT) if date_raw else None) or ctx.search_date
            return [build_search_result(title=title, scene_url=scene_url, query=ctx.title, display_date=date_iso, score=100)]

        encoded = slugify(ctx.title).replace('-', '+')
        search_url = base + ctx.site_info.search_path + encoded
        channel = _CHANNELS.get(ctx.site_info.name)
        if channel:
            search_url += f'&channel={channel}'
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search')
        if not loaded:
            return []

        results: list[SearchResult] = []
        for row in loaded['sel'].xpath('//div[contains(@class,"results_item")]'):
            a = row.xpath('(.//a[contains(@class,"post_title")])[1]')
            title = (a.xpath('string(.)').get() or '').strip()
            href = (a.xpath('@href').get() or '').strip()
            if not title or not href:
                continue
            scene_url = absolute_url(href, ctx.site_info.base_url)
            results.append(
                build_search_result(
                    title=title, scene_url=scene_url, query=ctx.title, display_date=ctx.search_date, score=title_distance_score(ctx.title, title)
                )
            )
        return results

    # ── Field hooks ───────────────────────────────────────────────────────────

    def _tagline_of(self, scene: LoadedScene) -> str:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//a[contains(@href,"/studio/profile/")])[1]').xpath('string(.)').get() or '').strip()
        return title_case(raw, site_name=scene.site.name) if raw else ''

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//h1[contains(@class,"post_title")]//span)[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = scene.sel.xpath('(//h2[contains(@class,"post_description")])[1]').xpath('string(.)').get() or ''
        return raw.replace('´', "'").replace('’', "'").strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return self._tagline_of(scene) or None

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        out: list[str] = []
        tagline = self._tagline_of(scene)
        if tagline:
            out.append(tagline)
        dvd = (scene.sel.xpath('(//div[contains(@class,"post_item") and contains(@class,"dvd")]//h1)[1]').xpath('string(.)').get() or '').strip()
        if dvd:
            out.append(title_case(dvd.lower(), site_name=scene.site.name))
        return out or None

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//h3[contains(@class,"post_date")])[1]').xpath('string(.)').get() or '').strip()
        return (iso_date(raw, _DATE_FMT) if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        out = [g for g in ((a.xpath('normalize-space(.)').get() or '').strip() for a in scene.sel.xpath('//a[contains(@href,"/search?s=")]')) if g]
        return out or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        out = [
            ActorResult(name=n) for n in ((a.xpath('normalize-space(.)').get() or '').strip() for a in scene.sel.xpath('//a[contains(@href,"models/")]')) if n
        ]
        return out or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        coll = self.image_collector(lambda raw: absolute_url(raw, scene.site.base_url))
        for src in scene.sel.xpath('//img[contains(@class,"item_cover")]/@src').getall():
            coll['push'](src)
        coll['push'](scene.sel.xpath('(//meta[@name="twitter:image"])[1]/@content').get())
        images: list[str] = coll['list']
        return images or None
