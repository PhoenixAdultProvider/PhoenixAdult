from __future__ import annotations

import re
from urllib.parse import quote

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, pack_cur_id
from app.utils.helpers.html_helpers import first_text

UMBRELLA_STUDIO = 'Dorcel Vision'
_YEAR_RE = re.compile(r'\d{4}')
_STUDIO_OVERRIDE_XP = '//div[contains(@class,"entries")]//strong[contains(.,"Studio")]/following-sibling::a[1]'


def _page_studio_override(scene: LoadedScene) -> str:
    assert scene.sel is not None
    return first_text(scene.sel, _STUDIO_OVERRIDE_XP)


class DorcelVisionClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', quote(ctx.title))
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return []
        results: list[SearchResult] = []
        for el in loaded['sel'].xpath('//a[contains(@class,"movies")]'):
            title = (el.xpath('(.//img/@alt)[1]').get() or '').strip()
            href = (el.xpath('@href').get() or '').strip()
            if not title or not href:
                continue
            scene_url = href if href.startswith('http') else absolute_url(href, ctx.site_info.base_url)
            results.append(build_search_result(title=title, scene_url=scene_url, query=ctx.title, search_date=ctx.search_date, cur_id=pack_cur_id([scene_url])))
        return results

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//h1') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        meta = (scene.sel.xpath('(//meta[@name="twitter:description"]/@content)[1]').get() or '').strip()
        return meta or first_text(scene.sel, '//div[@id="summaryList"]') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return _page_studio_override(scene) or UMBRELLA_STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return _page_studio_override(scene) or UMBRELLA_STUDIO

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        override = _page_studio_override(scene)
        return [UMBRELLA_STUDIO, override] if override else [UMBRELLA_STUDIO]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        year_entries = scene.sel.xpath('//div[contains(@class,"entries")]//strong[contains(.,"Production year")]')
        if not year_entries:
            return None
        text = ''.join(year_entries[0].xpath('following-sibling::text()').getall())
        m = _YEAR_RE.search(text)
        return f'{m.group(0)}-01-01' if m else None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for card in scene.sel.xpath('//div[contains(@class,"casting")]//div[contains(@class,"slider-xl")]//div[contains(@class,"col-xs-2")]'):
            name = first_text(card, './/a/strong')
            if not name or name in seen:
                continue
            seen.add(name)
            photo_raw = (card.xpath('(.//img/@data-src)[1]').get() or '').strip()
            photo = absolute_url(photo_raw, scene.site.base_url) if photo_raw else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        images: list[str] = []

        def add(raw: str) -> None:
            raw = (raw or '').strip()
            if not raw:
                return
            stripped = raw.replace('blur9/', '')
            abs_url = stripped if stripped.startswith('http') else absolute_url(stripped, base)
            if abs_url not in images:
                images.append(abs_url)

        for href in scene.sel.xpath('//div[contains(@class,"covers")]//a[contains(@class,"cover")]/@href').getall():
            add(href)
        for href in scene.sel.xpath(
            '//div[contains(@class,"screenshots")]//div[contains(@class,"slider-xl")]//div[contains(@class,"col-xs-2")]//a/@href'
        ).getall():
            add(href)
        return images
