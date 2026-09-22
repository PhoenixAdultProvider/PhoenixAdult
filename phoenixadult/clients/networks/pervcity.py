from __future__ import annotations

import re
from typing import Any

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id, slugify
from phoenixadult.utils.helpers.html_helpers import first_attr, web_search_urls

STUDIO = 'PervCity'
_SHARED_BASE = 'https://pervcity.com'
_NON_WORD_RE = re.compile(r'\W')


class PervCityClient(Client):
    title_xpath = '(//h1)[1]'
    genres_xpath = '//div[@class="tagcats"]/a'

    def __init__(self) -> None:
        super().__init__({'Cookie': 'warning_cookie=1'})

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        seen: set[str] = set()

        if (search_data.site_info.search_path or '').strip():
            slug = slugify(search_data.title).replace('-', '+')
            url = search_data.search_url(slug)
            search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {url}')
            if search_results:
                for search_result in search_results['sel'].xpath('//div[@class="videoBlock"]'):
                    title = (search_result.xpath('(.//h2 | .//h3)[1]').xpath('string(.)').get() or '').strip()
                    href = first_attr(search_result, '(.//h2//a | .//h3//a)[1]/@href')
                    if not title or not href:
                        continue

                    scene_url = absolute_url(href, search_data.site_info.base_url)
                    if scene_url in seen:
                        continue

                    seen.add(scene_url)
                    raw_date = (search_result.xpath('(.//div[@class="date"])[1]').xpath('string(.)').get() or '').strip()
                    date = iso_date(raw_date) if raw_date else search_data.search_date

                    results.append(
                        build_search_result(
                            site=search_data.site_info,
                            title=title,
                            scene_url=scene_url,
                            query=search_data.title,
                            display_date=date,
                            search_date=search_data.search_date,
                            cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
                        )
                    )

        for raw in await web_search_urls(search_data.title, search_data.site_info, include=['trailers'], exclude=['as3']):
            scene_url = raw.replace('www.', '')
            if scene_url in seen or raw in seen:
                continue

            seen.add(scene_url)
            details_page_elements = await self.fetch_and_load(
                scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] fallback {scene_url}'
            )
            if not details_page_elements:
                continue

            title = (details_page_elements['sel'].xpath('(//h1)[1]').xpath('string(.)').get() or '').strip()
            if not title:
                continue

            date = search_data.search_date

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=date,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
                )
            )

    # ── Context Loader (resolves cast; crawls model pages for a date) ───────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        pipe = payload.find('|')
        url = payload[:pipe] if pipe >= 0 else payload
        fallback = payload[pipe + 1 :].strip() if pipe >= 0 else None
        capture = ctx.capture if ctx else None

        details_page_elements = await self.fetch_and_load(url, FetchCtx(capture=capture, use_bypass=site.use_bypass), f'[{site.name}] scene {url}')
        if not details_page_elements:
            return None

        sel = details_page_elements['sel']
        clean_scene = _NON_WORD_RE.sub('', (sel.xpath('(//h1)[1]').xpath('string(.)').get() or '').strip()).lower()

        actors: list[ActorResult] = []
        seen: set[str] = set()
        crawled_date: str | None = None
        for row in sel.xpath('//h2/span/a | //h3/span/a'):
            name = first_attr(row, 'normalize-space(.)')
            href = first_attr(row, '@href')
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
            html=details_page_elements['html'],
            extra={'actors': actors, 'crawled_date': crawled_date},
        )

    async def _fetch_actor_page(self, href: str, site_base: str, capture: Any) -> Any:
        cur = site_base.replace('www.', '')
        primary = href.replace(cur, _SHARED_BASE)
        if not primary.startswith('http'):
            primary = absolute_url(primary, site_base)

        model_page_elements = await self.fetch_and_load(primary, FetchCtx(capture=capture), f'GET {primary} (actor)')
        if model_page_elements:
            return model_page_elements['sel']

        fallback = href.replace('www.', '')
        if not fallback.startswith('http'):
            fallback = absolute_url(fallback, site_base)

        model_page_elements = await self.fetch_and_load(fallback, FetchCtx(capture=capture), f'GET {fallback} (actor)')
        return model_page_elements['sel'] if model_page_elements else None

    def _crawl_date(self, page: Any, clean_scene: str) -> str | None:
        for block in page.xpath('//div[@class="videoBlock" or @class="videoContent"]'):
            h2 = _NON_WORD_RE.sub('', (block.xpath('(.//h2)[1]').xpath('string(.)').get() or '').replace('...', '').strip()).lower()
            h3 = _NON_WORD_RE.sub('', (block.xpath('(.//h3/a)[1]').xpath('string(.)').get() or '').replace('...', '').strip()).lower()
            if (h2 and h2 in clean_scene) or (h3 and h3 in clean_scene):
                raw = (page.xpath('(//div[@class="date"])[1]').xpath('string(.)').get() or '').strip()
                if raw:
                    return iso_date(raw)

        return None

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _tagline_for(self, scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        about = (details_page_elements.xpath('(//div[@class="about"]//h3)[1]').xpath('string(.)').get() or '').replace('About', '').strip()
        if about:
            return about

        if scene.site.name.replace(' ', '') != STUDIO:
            return scene.site.name

        return STUDIO

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        info = (details_page_elements.xpath('(//div[contains(@class,"infoBox")]//p)[1]').xpath('string(.)').get() or '').strip()
        if info:
            metadata.summary = info
            return

        metadata.summary = (details_page_elements.xpath('(//h3[@class="description"])[1]').xpath('string(.)').get() or '').strip()

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline_for(scene)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [self._tagline_for(scene)]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        if scene.scene_date:
            metadata.release_date = iso_date(scene.scene_date) or scene.scene_date
            return

        metadata.release_date = (scene.extra or {}).get('crawled_date')

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.actors = (scene.extra or {}).get('actors') or []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        images = self.image_collector(lambda image: absolute_url(image, base))
        for image_url in details_page_elements.xpath('//div[@class="snap"]//img/@src0_3x').getall():
            images.push(image_url)

        metadata.art = images.items
