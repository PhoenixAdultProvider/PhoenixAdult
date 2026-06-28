from __future__ import annotations

import re
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id, slugify
from app.utils.helpers.html_helpers import first_attr, web_search_urls

STUDIO = 'PervCity'
_SHARED_BASE = 'https://pervcity.com'
_NON_WORD_RE = re.compile(r'\W')


class PervCityClient(Client):
    def __init__(self) -> None:
        super().__init__({'Cookie': 'warning_cookie=1'})

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        results: list[SearchResult] = []
        seen: set[str] = set()

        if (ctx.site_info.search_path or '').strip():
            slug = slugify(ctx.title).replace('-', '+')
            url = base + ctx.site_info.search_path.replace('{query}', slug)
            loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {url}')
            if loaded:
                for card in loaded['sel'].xpath('//div[@class="videoBlock"]'):
                    title = (card.xpath('(.//h2 | .//h3)[1]').xpath('string(.)').get() or '').strip()
                    href = first_attr(card, '(.//h2//a | .//h3//a)[1]/@href')
                    if not title or not href:
                        continue
                    scene_url = absolute_url(href, ctx.site_info.base_url)
                    if scene_url in seen:
                        continue
                    seen.add(scene_url)
                    raw_date = (card.xpath('(.//div[@class="date"])[1]').xpath('string(.)').get() or '').strip()
                    date = iso_date(raw_date) if raw_date else ctx.search_date
                    results.append(
                        build_search_result(
                            title=title,
                            scene_url=scene_url,
                            query=ctx.title,
                            display_date=date,
                            search_date=ctx.search_date,
                            cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
                        )
                    )

        for raw in await web_search_urls(ctx.title, ctx.site_info, include=['trailers'], exclude=['as3']):
            scene_url = raw.replace('www.', '')
            if scene_url in seen or raw in seen:
                continue
            seen.add(scene_url)
            page = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] fallback {scene_url}')
            if not page:
                continue
            title = (page['sel'].xpath('(//h1)[1]').xpath('string(.)').get() or '').strip()
            if not title:
                continue
            date = ctx.search_date
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=ctx.title,
                    display_date=date,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
                )
            )
        return results

    # ── Context loader (resolves cast; crawls model pages for a date) ───────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        pipe = payload.find('|')
        url = payload[:pipe] if pipe >= 0 else payload
        fallback = payload[pipe + 1 :].strip() if pipe >= 0 else None
        capture = ctx.capture if ctx else None

        loaded = await self.fetch_and_load(url, FetchCtx(capture=capture), f'[{site.name}] scene {url}')
        if not loaded:
            return None
        sel = loaded['sel']
        clean_scene = _NON_WORD_RE.sub('', (sel.xpath('(//h1)[1]').xpath('string(.)').get() or '').strip()).lower()

        actors: list[ActorResult] = []
        seen: set[str] = set()
        crawled_date: str | None = None
        for el in sel.xpath('//h2/span/a | //h3/span/a'):
            name = first_attr(el, 'normalize-space(.)')
            href = first_attr(el, '@href')
            if not name or name in seen:
                continue
            seen.add(name)
            photo = ''
            if href:
                page = await self._fetch_actor_page(href, site.base_url, capture)
                if page is not None:
                    photo = first_attr(page, '(//div[@class="starPic"]//img | //div[@class="bioBPic"]//img)[1]/@src')
                    if not fallback:
                        crawled_date = self._crawl_date(page, clean_scene) or crawled_date
            actors.append(ActorResult(name=name, photo_url=photo))

        return LoadedScene(
            url=url,
            site=site,
            scene_date=fallback or None,
            capture=capture,
            sel=sel,
            html=loaded['html'],
            extra={'actors': actors, 'crawled_date': crawled_date},
        )

    async def _fetch_actor_page(self, href: str, site_base: str, capture: Any) -> Any:
        cur = site_base.replace('www.', '')
        primary = href.replace(cur, _SHARED_BASE)
        if not primary.startswith('http'):
            primary = absolute_url(primary, site_base)
        page = await self.fetch_and_load(primary, FetchCtx(capture=capture), f'GET {primary} (actor)')
        if page:
            return page['sel']
        fallback = href.replace('www.', '')
        if not fallback.startswith('http'):
            fallback = absolute_url(fallback, site_base)
        page = await self.fetch_and_load(fallback, FetchCtx(capture=capture), f'GET {fallback} (actor)')
        return page['sel'] if page else None

    def _crawl_date(self, page: Any, clean_scene: str) -> str | None:
        for block in page.xpath('//div[@class="videoBlock" or @class="videoContent"]'):
            h2 = _NON_WORD_RE.sub('', (block.xpath('(.//h2)[1]').xpath('string(.)').get() or '').replace('...', '').strip()).lower()
            h3 = _NON_WORD_RE.sub('', (block.xpath('(.//h3/a)[1]').xpath('string(.)').get() or '').replace('...', '').strip()).lower()
            if (h2 and h2 in clean_scene) or (h3 and h3 in clean_scene):
                raw = (page.xpath('(//div[@class="date"])[1]').xpath('string(.)').get() or '').strip()
                if raw:
                    return iso_date(raw)
        return None

    # ── Detail field hooks ────────────────────────────────────────────────────

    def _tagline_for(self, scene: LoadedScene) -> str:
        assert scene.sel is not None
        about = (scene.sel.xpath('(//div[@class="about"]//h3)[1]').xpath('string(.)').get() or '').replace('About', '').strip()
        if about:
            return about
        if scene.site.name.replace(' ', '') != STUDIO:
            return scene.site.name
        return STUDIO

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//h1)[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        info = (scene.sel.xpath('(//div[contains(@class,"infoBox")]//p)[1]').xpath('string(.)').get() or '').strip()
        if info:
            return info
        return (scene.sel.xpath('(//h3[@class="description"])[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return self._tagline_for(scene)

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [self._tagline_for(scene)]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        if scene.scene_date:
            return iso_date(scene.scene_date) or scene.scene_date
        return (scene.extra or {}).get('crawled_date')

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//div[@class="tagcats"]/a')]
        return self.dedup_strings(values) or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        actors = (scene.extra or {}).get('actors') or []
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        images: list[str] = []
        for raw in scene.sel.xpath('//div[@class="snap"]//img/@src0_3x').getall():
            if not raw:
                continue
            abs_url = absolute_url(raw, base)
            if abs_url not in images:
                images.append(abs_url)
        return images or None
