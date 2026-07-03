from __future__ import annotations

import re

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id, title_distance_score
from app.utils.helpers.html_helpers import first_attr, first_string

STUDIO = 'Couples Cinema'
_YEAR_RE = re.compile(r'^\d{4}$')


class CouplesCinemaClient(Client):
    def __init__(self) -> None:
        super().__init__({'Cookie': 'WarningModal=true'})

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')

        # Numeric sceneId → direct scene.
        if ctx.scene_id:
            scene_url = f'{base}/post/details/{ctx.scene_id}'
            page = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] directScene {scene_url}')
            if not page:
                return []
            title = (page['sel'].xpath('(//div[contains(@class,"mediaHeader")]//span[contains(@class,"title")])[1]').xpath('string(.)').get() or '').strip()
            if not title:
                return []
            return [
                build_search_result(title=title, scene_url=scene_url, query=ctx.title, search_date=ctx.search_date, score=100, cur_id=pack_cur_id([scene_url]))
            ]

        # Keyword search.
        slug = '+'.join(ctx.title.split())
        search_url = base + ctx.site_info.search_path.replace('{query}', slug)
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {search_url}')
        if not loaded:
            return []

        requested = ctx.site_info.name.lower()
        results: list[SearchResult] = []
        for card in loaded['sel'].xpath('//div[contains(@class,"Post")]'):
            title = (card.xpath('(.//span[contains(@class,"title")])[1]').xpath('string(.)').get() or '').strip()
            href = first_attr(card, '(.//a[contains(@class,"media")])[1]/@href')
            if not title or not href:
                continue
            scene_url = absolute_url(href, ctx.site_info.base_url)
            studio = (card.xpath('(.//span[contains(@class,"source")])[1]').xpath('string(.)').get() or '').strip()
            cover = first_attr(card, '(.//a[contains(@class,"media")]//img[contains(@class,"image")])[1]/@src')
            cover_packed = self.encode(cover) if cover else ''

            score: float = title_distance_score(ctx.title, title)
            if studio.lower() != requested:
                score -= 10

            # Always pack date + cover segments (legacy parity).
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=ctx.title,
                    search_date=ctx.search_date,
                    score=score,
                    cur_id=pack_cur_id([scene_url, ctx.search_date or '', cover_packed]),
                )
            )
        return results

    # ── Detail field hooks ────────────────────────────────────────────────────

    @staticmethod
    def _date_part(scene: LoadedScene) -> str | None:
        return scene.scene_date.split('|')[0].strip() if scene.scene_date else None

    @staticmethod
    def _cover_part(scene: LoadedScene) -> str:
        if scene.scene_date and '|' in scene.scene_date:
            return scene.scene_date.split('|', 1)[1]
        return ''

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//div[contains(@class,"mediaHeader")]//span[contains(@class,"title")])[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//span[contains(@class,"description")])[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//span[contains(@class,"type")])[1]').xpath('string(.)').get() or '').strip()
        return raw.split('|')[0].strip() or None

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        tag = await self.fetch_tagline(scene)
        return [tag] if tag else None

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        date_part = self._date_part(scene)
        if date_part:
            return iso_date(date_part) or date_part
        raw = (scene.sel.xpath('(//span[contains(@class,"type")])[1]').xpath('string(.)').get() or '').strip()
        parts = [p.strip() for p in raw.split('|')]
        year = parts[1] if len(parts) > 1 else ''
        return f'{year}-01-01' if _YEAR_RE.match(year) else None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        entries = [ActorResult(name=first_string(a)) for a in scene.sel.xpath('//div[contains(@class,"cast")]//a')]
        return self.dedup_people(entries) or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        coll = self.image_collector(lambda raw: absolute_url(raw, scene.site.base_url))

        cover_packed = self._cover_part(scene)
        if cover_packed:
            try:
                coll['push'](self.decode(cover_packed))
            except Exception:  # noqa: BLE001 - decode failures are non-fatal
                pass

        for raw in scene.sel.xpath('//video/@poster').getall():
            coll['push'](raw)
        images: list[str] = coll['list']
        return images or None
