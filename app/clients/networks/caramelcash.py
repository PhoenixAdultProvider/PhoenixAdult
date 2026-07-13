from __future__ import annotations

import re

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id, strip_query
from app.utils.helpers.html_helpers import first_attr, web_search_urls
from app.utils.searchengines import web_search_available

STUDIO = 'Caramel Cash'

_DDMMYYYY_RE = re.compile(r'^\d{1,2}\.\d{1,2}\.\d{4}$')
_ORDINAL_RE = re.compile(r'(\d)(st|nd|rd|th)', re.IGNORECASE)


def _parse_caramel_date(raw: str) -> str | None:
    cleaned = raw.strip()
    if not cleaned:
        return None
    if _DDMMYYYY_RE.match(cleaned):
        return iso_date(cleaned, '%d.%m.%Y')
    no_prefix = cleaned.split(':')[-1].strip() if ':' in cleaned else cleaned
    no_ordinal = _ORDINAL_RE.sub(r'\1', no_prefix).strip()
    return iso_date(no_ordinal, '%d %b %Y') or iso_date(no_ordinal)


__testing__ = {'parse_caramel_date': _parse_caramel_date}


class CaramelCashClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        candidates: list[str] = []
        if ctx.scene_id:
            candidates.append(base + ctx.site_info.search_path.replace('{query}', ctx.scene_id))

        if web_search_available():
            for u in await web_search_urls(ctx.title, ctx.site_info, include=['video/', 'videos/'], exclude=['/page/']):
                clean = strip_query(u)
                if clean not in candidates:
                    candidates.append(clean)

        for scene_url in candidates:
            page = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] candidate {scene_url}')
            if not page:
                continue
            raw_title = (page['sel'].xpath('(//h1)[1]').xpath('string(.)').get() or '').strip()
            if not raw_title:
                continue
            raw_date = (page['sel'].xpath('(//div[contains(@class,"content-date")])[1]').xpath('string(.)').get() or '').strip()
            date = _parse_caramel_date(raw_date) if raw_date else ctx.search_date
            results.append(
                build_search_result(
                    title=raw_title,
                    scene_url=scene_url,
                    query=ctx.title,
                    display_date=date,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
                )
            )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = (scene.sel.xpath('(//div[contains(@class,"content-title")])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        # Legacy uses the SECOND content-desc block.
        metadata.summary = (scene.sel.xpath('(//div[contains(@class,"content-desc")])[2]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//div[contains(@class,"content-date")])[1]').xpath('string(.)').get() or '').strip()
        if raw:
            metadata.release_date = _parse_caramel_date(raw)
            return
        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('string(.)').get() or '' for a in scene.sel.xpath('//div[contains(@class,"content-tags")]//a')]
        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        entries = [
            ActorResult(name=first_attr(a))
            for a in scene.sel.xpath('//section[contains(@class,"content-sec") and contains(@class,"backdrop")]//div[contains(@class,"main__models")]//a')
        ]
        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        coll = self.image_collector()
        for href in scene.sel.xpath('//section[contains(@class,"content-gallery-sec")]//a[@data-lightbox="gallery"]/@href').getall():
            coll['push'](href)
        metadata.raw_image_urls = coll['list']
