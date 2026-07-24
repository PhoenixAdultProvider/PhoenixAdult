from __future__ import annotations

import dataclasses
import re
from urllib.parse import quote

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.clients.sites.clips4sale import Clips4SaleClient
from phoenixadult.models.scraper_config import ScraperConfig
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id, unpack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_attr

STUDIO = 'Family Therapy'
_C4S_STUDIO_ID = '81593'
_C4S_BASE = 'https://clips4sale.com'
_STARRING_RE = re.compile(r"(?:Starring|starring)\s+(\w[\w'-]*\s\w[\w'-]*(?:\s&\s\w[\w'-]*\s\w[\w'-]*)*)")


def _to_title_case(s: str) -> str:
    return ' '.join((w[0].upper() + w[1:]) if w else w for w in s.lower().split())


class FamilyTherapyClient(Client):
    def __init__(self) -> None:
        super().__init__()
        self._clips4sale = Clips4SaleClient()

    def _c4s_site(self, site: ResolvedSiteInfo, name: str | None = None) -> ResolvedSiteInfo:
        return dataclasses.replace(
            site,
            name=name or site.name,
            base_url=_C4S_BASE,
            search_path='/studio/',
            scraper_config=ScraperConfig(type='clips4sale'),
        )

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        url = base + search_data.site_info.search_path.replace('{query}', quote(search_data.title))
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"')

        if search_results:
            for search_result in search_results['sel'].xpath('//article'):
                a = search_result.xpath('(.//h2//a)[1]')
                title = first_attr(a)
                href = first_attr(a, '@href')
                if not title or not href:
                    continue

                scene_url = absolute_url(href, search_data.site_info.base_url)
                date = iso_date((search_result.xpath('(.//p//span)[1]').xpath('string(.)').get() or '').strip())

                results.append(
                    build_search_result(
                        title=title,
                        scene_url=scene_url,
                        query=search_data.title,
                        display_date=date,
                        search_date=search_data.search_date,
                        cur_id=pack_cur_id([scene_url, f'{date or ""}|0']),
                    )
                )

        if not results:
            actress = ' '.join(search_data.title.strip().split()[:2])
            if actress:
                c4s_query = f'{_C4S_STUDIO_ID} {actress}'
                c4s_ctx = dataclasses.replace(
                    search_data, title=c4s_query, encoded=quote(c4s_query), site_info=self._c4s_site(search_data.site_info, 'Family Therapy (C4S)')
                )
                c4s_results: list[SearchResult] = []
                await self._clips4sale.search(c4s_results, c4s_ctx)
                for r in c4s_results:
                    head = unpack_cur_id(r.cur_id)['head'] or ''

                    results.append(dataclasses.replace(r, cur_id=pack_cur_id([head, '|1'])))

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        first_pipe = payload.find('|')
        url = payload[:first_pipe] if first_pipe >= 0 else payload
        tail = payload[first_pipe + 1 :] if first_pipe >= 0 else ''
        tail_parts = tail.split('|')
        fallback_date = tail_parts[0] if tail_parts else ''
        mode = tail_parts[1] if len(tail_parts) > 1 else '0'

        if mode == '1':
            c4s_detail = await self._clips4sale.fetch_scene_detail(url, self._c4s_site(site), ctx)
            if not c4s_detail:
                return None

            return LoadedScene(
                url=url,
                site=site,
                capture=ctx.capture if ctx else None,
                extra={'mode': '1', 'c4s': c4s_detail},
                subsite=ctx.subsite if ctx else None,
            )

        details_page_elements = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture if ctx else None), f'[{site.name}] detail {url}')
        if not details_page_elements:
            return None

        sel = details_page_elements['sel']
        if not (sel.xpath('(//h1)[1]').xpath('string(.)').get() or '').strip():
            return None

        return LoadedScene(
            url=url,
            site=site,
            scene_date=fallback_date or None,
            capture=ctx.capture if ctx else None,
            sel=sel,
            html=details_page_elements['html'],
            extra={'mode': '0'},
            subsite=ctx.subsite if ctx else None,
        )

    async def update(self, metadata: SceneDetail, scene: LoadedScene) -> None:
        extra = scene.extra or {}
        if extra.get('mode') == '1':
            c4s = extra['c4s']
            for f in dataclasses.fields(c4s):
                setattr(metadata, f.name, getattr(c4s, f.name))

            metadata.studio = STUDIO
            metadata.collections = [STUDIO]
            return

        details_page_elements = scene.require_sel()

        # Title
        metadata.title = _to_title_case((details_page_elements.xpath('(//h1)[1]').xpath('string(.)').get() or '').strip())

        # Summary
        nodes = details_page_elements.xpath('//div[contains(@class,"entry-content")]/p')
        summary = (
            nodes[0].xpath('string(.)').get() if nodes else details_page_elements.xpath('(//div[contains(@class,"entry-content")])[1]').xpath('string(.)').get()
        ) or ''
        metadata.summary = summary.strip()

        # Studio
        metadata.studio = STUDIO

        # Collection(s)
        metadata.collections = [STUDIO]

        # Release Date
        date_raw = (details_page_elements.xpath('(//p[contains(@class,"post-meta")]//span)[1]').xpath('string(.)').get() or '').strip()
        metadata.release_date = iso_date(date_raw, '%b %d, %Y') or scene.scene_date or None

        # Genres
        metadata.genres = self.dedup_strings([first_attr(row) for row in details_page_elements.xpath('//a[@rel="category tag"]')])

        # Actor(s)
        seen: set[str] = set()
        for row in details_page_elements.xpath('//div[contains(@class,"entry-content")]//p'):
            m = _STARRING_RE.search(row.xpath('string(.)').get() or '')
            if not m:
                continue

            for name in (s.strip() for s in m.group(1).split('&')):
                if name and name not in seen:
                    seen.add(name)
                    metadata.actors.append(ActorResult(name=name))

        # Posters
        metadata.art = []
