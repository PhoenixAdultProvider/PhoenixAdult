from __future__ import annotations

import math
import re
from datetime import date

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import build_search_result, iso_date, join_url, pack_cur_id
from app.utils.helpers.html_helpers import first_attr

STUDIO = 'PornWorld'
_PER_PAGE = 99
_MAX_CRAWL_PAGES = 15
_ISO_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_SUFFIX_RE = re.compile(r'\s*-\s*PornWorld\s*$', re.IGNORECASE)


def _clean_title(raw: str) -> str:
    return _SUFFIX_RE.sub('', raw).strip()


def _iso_date_obj(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


class PornWorldClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')

        if ctx.search_date and _ISO_RE.match(ctx.search_date):
            dated = await self._date_crawl(ctx, base)
            if dated:
                results.extend(dated)
                return

        first_word = ctx.scene_id or (ctx.title.strip().split()[0] if ctx.title.strip() else '')
        if first_word.isdigit() and len(first_word) > 3:
            scene_url = f'{base}/watch/{first_word}'
            page = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] directScene {scene_url}')
            if page:
                title = _clean_title((page['sel'].xpath('(//title)[1]').xpath('string(.)').get() or '').strip())
                if title:
                    results.append(
                        build_search_result(
                            title=title, scene_url=scene_url, query=ctx.title, search_date=ctx.search_date, score=100, cur_id=pack_cur_id([scene_url])
                        )
                    )
                    return

        slug = re.sub(r'\s+', '+', ctx.title.strip())
        search_url = base + ctx.site_info.search_path.replace('{query}', slug)
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {search_url}')
        if not loaded:
            return
        sel = loaded['sel']

        if not sel.xpath('//h1[contains(@class,"section__title")]'):
            title = _clean_title((sel.xpath('(//title)[1]').xpath('string(.)').get() or '').strip())
            href = first_attr(sel, '(//a[contains(@class,"__pagination_button--more")])[1]/@href')
            if title and href:
                results.append(
                    build_search_result(
                        title=title, scene_url=join_url(href, base), query=ctx.title, search_date=ctx.search_date, cur_id=pack_cur_id([join_url(href, base)])
                    )
                )
                return

        for a in sel.xpath('//div[contains(@class,"card-scene")]//div[contains(@class,"card-scene__text")]/a'):
            title = first_attr(a, 'normalize-space(.)')
            href = first_attr(a, '@href')
            if not title or not href:
                continue
            results.append(
                build_search_result(
                    title=title, scene_url=join_url(href, base), query=ctx.title, search_date=ctx.search_date, cur_id=pack_cur_id([join_url(href, base)])
                )
            )

    async def _date_crawl(self, ctx: SearchContext, base: str) -> list[SearchResult]:
        assert ctx.search_date is not None
        target = _iso_date_obj(ctx.search_date)
        if target is None:
            return []
        delta_days = max(0, (date.today() - target).days)
        page = max(math.ceil(delta_days / _PER_PAGE), 1)

        for _ in range(_MAX_CRAWL_PAGES):
            url = f'{base}/new-videos/{page}'
            loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] dateCrawl p{page}')
            if not loaded:
                break
            date_els = loaded['sel'].xpath('//div[contains(@class,"card-scene__time")]/div[contains(@class,"label--time")][2]')
            if not date_els:
                break

            first_date = _iso_date_obj(date_els[0].xpath('string(.)').get() or '')
            if first_date and target > first_date and page > 1:
                page -= 1
                continue
            last_date = _iso_date_obj(date_els[-1].xpath('string(.)').get() or '')
            if last_date and target < last_date:
                page += 1
                continue

            results: list[SearchResult] = []
            for card in loaded['sel'].xpath('//div[contains(@class,"card-scene")]'):
                title = (card.xpath('(.//div[contains(@class,"card-scene__text")]/a)[1]').xpath('string(.)').get() or '').strip()
                href = first_attr(card, '(.//a)[1]/@href')
                if not title or not href:
                    continue
                scene_date_text = (card.xpath('(.//div[contains(@class,"label--time")])[2]').xpath('string(.)').get() or '').strip()
                scene_date = _iso_date_obj(scene_date_text)
                if scene_date is None:
                    continue
                days_diff = abs((target - scene_date).days)
                if days_diff >= 3:
                    continue
                results.append(
                    build_search_result(
                        title=title,
                        scene_url=join_url(href, base),
                        query=ctx.title,
                        display_date=scene_date_text,
                        search_date=ctx.search_date,
                        score=100 - days_diff * 10,
                        cur_id=pack_cur_id([x for x in (join_url(href, base), scene_date_text) if x]),
                    )
                )
            return results
        return []

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//title)[1]').xpath('string(.)').get() or '').strip()
        metadata.title = _clean_title(raw) if raw else ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = (scene.sel.xpath('(//div[text()="Description:"]/following-sibling::div)[1]').xpath('string(.)').get() or '').strip()

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//i[contains(@class,"bi-calendar")])[1]').xpath('string(.)').get() or '').strip()
        if raw:
            metadata.release_date = iso_date(raw)
            return
        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//div[contains(@class,"genres-list")]//a')]
        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        entries = [ActorResult(name=first_attr(a, 'normalize-space(.)')) for a in scene.sel.xpath('//h1[contains(@class,"watch__title")]//a')]
        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        coll = self.image_collector()
        for raw in scene.sel.xpath('//video/@data-poster').getall():
            coll['push'](raw)
        metadata.art = coll['list']
