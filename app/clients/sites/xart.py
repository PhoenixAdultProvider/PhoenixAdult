from __future__ import annotations

import re
from typing import Any

import app.utils.images.fansite_adapters  # noqa: F401 - registers the fansite adapters
from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, load_site_json, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text
from app.utils.images.fanart import FindFanArtOptions, find_fan_art, register_fanart_overrides
from app.utils.searchengines import SearchOptions, web_search

STUDIO = 'X-Art'
_MANUAL_MATCHES: dict[str, dict[str, str]] = load_site_json(__file__, 'xart_manual_matches')
_FANART_SITES = ['XartFan.com', 'HQSluts.com', 'ImagePost.com', 'CoedCherry.com', 'Nude-Gals.com']
_HARVEST_XPATHS = (
    '//img[@alt="thumb"]/@src',
    '//div[contains(@class,"video-tour")]//a//img/@src',
    '//div[contains(@class,"gallery-item")]//img/@src',
)
_COLUMNS = 'contains(@class,"small-12") and contains(@class,"medium-12") and contains(@class,"large-12") and contains(@class,"columns")'
_TITLE_XP = f'//div[contains(@class,"row") and contains(@class,"info")]//div[{_COLUMNS}]'
_SUMMARY_XP = f'//div[{_COLUMNS} and contains(@class,"info")]//p'

_overrides = load_site_json(__file__, 'xart_fanart_overrides')
register_fanart_overrides(no_match=_overrides.get('noMatch'), bad_match=_overrides.get('badMatch'))


class XartClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        search_url = f'{base}{ctx.site_info.search_path}?input_search_sm={ctx.encoded}'
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')

        seen: set[str] = set()

        if loaded:
            for a in loaded['sel'].xpath('//a[contains(@href,"videos")]'):
                title = first_attr(a, '(.//img[contains(@src,"videos")]/@alt)[1]')
                href = first_attr(a, '@href')
                if not title or not href:
                    continue
                scene_url = absolute_url(href, ctx.site_info.base_url)
                if scene_url in seen:
                    continue
                seen.add(scene_url)
                raw_date = first_text(a, '(.//h2)[2]')
                release_date = iso_date(raw_date) if raw_date else None
                results.append(
                    build_search_result(
                        title=title,
                        scene_url=scene_url,
                        query=ctx.title,
                        display_date=release_date,
                        search_date=ctx.search_date,
                        cur_id=pack_cur_id([p for p in (scene_url, release_date) if p]),
                    )
                )

        manual = _MANUAL_MATCHES.get(ctx.title)
        if manual:
            cur = manual['curID']
            scene_url = cur if cur.startswith('http') else base + cur
            if scene_url not in seen:
                results.append(
                    build_search_result(
                        title=manual['title'], scene_url=scene_url, query=ctx.title, search_date=ctx.search_date, score=100, cur_id=pack_cur_id([scene_url])
                    )
                )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        metadata.title = first_text(sel, _TITLE_XP) or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        parts = [t for t in (p.xpath('normalize-space(.)').get() or '' for p in sel.xpath(_SUMMARY_XP)) if t]
        metadata.summary = '\n\n'.join(parts) or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [STUDIO]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        raw = re.sub(r'.$', '', first_text(sel, '(//h2)[3]'))
        if not raw:
            return
        metadata.release_date = iso_date(raw, '%b %d, %Y') or iso_date(raw)

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        genres = ['Artistic', 'Glamorous']
        count = len(sel.xpath('//h2//a'))
        if (group := self.group_genre_for(count)) and group not in genres:
            genres.append(group)
        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        base = scene.site.base_url
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in sel.xpath('//h2//a'):
            name = first_attr(el, 'normalize-space(.)')
            href = re.sub(r'^http:', 'https:', first_attr(el, '@href'))
            if not name or not href or name in seen:
                continue
            seen.add(name)
            actor_url = absolute_url(href, base)
            page = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
            photo = first_attr(page['sel'], '(//img[contains(@class,"info-img")]/@src)[1]') if page else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        coll = self.image_collector(lambda raw: (raw or '').strip())

        def harvest(sel: Any) -> None:
            if sel is None:
                return
            for xp in _HARVEST_XPATHS:
                for raw in sel.xpath(xp).getall():
                    url = (raw or '').strip()
                    if 'videos' not in url:
                        continue
                    coll['push'](url)
                    if url.endswith('_1.jpg'):
                        coll['push'](url.replace('_1.jpg', '_2.jpg'))
                    elif url.endswith('_1-lrg.jpg'):
                        coll['push'](url.replace('_1-lrg.jpg', '_2-lrg.jpg'))

        gallery_url = scene.url.replace('/videos/', '/galleries/')
        if gallery_url != scene.url:
            gallery = await self.fetch_and_load(gallery_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] gallery')
            harvest(gallery['sel'] if gallery else None)
        harvest(sel)

        title = first_text(sel, _TITLE_XP) or ''
        actor_names = self.dedup_strings([first_attr(el, 'normalize-space(.)') for el in sel.xpath('//h2//a')])

        if title and actor_names:

            async def fetch_page(url: str) -> Any:
                page = await self.fetch_and_load(url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] fanart {url}')
                return page['sel'] if page else None

            async def do_search(query: str, domain: str, limit: int) -> list[str]:
                return await web_search(SearchOptions(query=query, site=domain, num=limit))

            fan = await find_fan_art(FindFanArtOptions(sites=_FANART_SITES, title=title, actor_names=actor_names, fetch_page=fetch_page, web_search=do_search))
            for u in fan.images:
                coll['push'](u)

        metadata.art = coll['list']
