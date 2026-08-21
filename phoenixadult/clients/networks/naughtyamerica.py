from __future__ import annotations

import re
from typing import Any

from phoenixadult.clients.aggregators.data18 import mapping_slug
from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id, slugify, to_https
from phoenixadult.utils.helpers.html_helpers import first_attr
from phoenixadult.utils.http.rate_limit_helper import ScenePacer
from phoenixadult.utils.people.sources import scene_image_pref

_SCENE_BASE = 'https://www.naughtyamerica.com'
_LASTPAGE_RE = re.compile(r'\d+(?=#)')
_IMAGES_CDN_RE = re.compile(r'images\d+', re.IGNORECASE)
STUDIO = 'Naughty America'
_PACE_SECONDS = 5.0
_PACE_JITTER = 3.0
_SCENE_COOLDOWN = 7.0
_PACE_TAG = 'NaughtyAmerica:pace'

_CARD_XP = '//div[contains(@class,"scene-item")] | //div[@class="scene-grid-item"]'


def _scene_path(href: str) -> str:
    if '/scene/' in href:
        return 'scene/' + href.split('/scene/', 1)[1].lstrip('/')

    return href.lstrip('/')


class NaughtyAmericaClient(Client):
    title_xpath = '(//div[contains(@class,"scene-info")]//h1)[1]'
    genres_xpath = '//div[contains(@class,"categories") and contains(@class,"grey-text")]//a'

    def __init__(self, extra_headers: dict[str, str] | None = None) -> None:
        super().__init__(extra_headers)
        self.pacer: ScenePacer = ScenePacer(_PACE_TAG, pace_seconds=_PACE_SECONDS, pace_jitter=_PACE_JITTER, cooldown_seconds=_SCENE_COOLDOWN)

    async def _paced(self, url: str, ctx: FetchCtx | None = None, label: str | None = None) -> dict[str, Any] | None:
        if ctx is None:
            ctx = FetchCtx()

        ctx.use_bypass = True
        await self.pacer.pace(label or url)
        return await self.fetch_and_load(url, ctx, label)

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        async with self.pacer.search_gate(bool(search_data.allow_slow)):
            await self._search(results, search_data)

    # ── Search Helpers ────────────────────────────────────────────────────────

    async def _search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')

        if search_data.scene_id and await self._search_by_scene_id(results, search_data):
            return

        search_url = f'{base}/search?term={slugify(search_data.title).replace("-", "+")}&_gl=1'
        loaded = await self._paced(search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {search_url}')
        if not loaded:
            return

        page_sel = loaded['sel']
        is_search_mode = bool(page_sel.xpath('//div[contains(@class,"scene-item")]'))
        last_href = page_sel.xpath('(//li/a[./i[contains(@class,"double")]])[1]/@href').get() or ''
        m = _LASTPAGE_RE.search(last_href)
        pagination = int(m.group(0)) + 2 if m else 3

        seen: set[str] = set()
        for idx in range(2, pagination):
            for card in page_sel.xpath(_CARD_XP):
                anchor = card.xpath('(.//a[contains(@href,"/scene/")])[1]')
                href = first_attr(anchor, '@href')
                raw_title = first_attr(anchor, '@title')
                if not href or not raw_title:
                    continue

                path = _scene_path(href)
                if path in seen:
                    continue

                seen.add(path)
                date = iso_date((card.xpath('(.//p[contains(@class,"entry-date")])[1]').xpath('string(.)').get() or '').strip())

                results.append(
                    build_search_result(
                        site=search_data.site_info,
                        title=raw_title,
                        scene_url=f'{_SCENE_BASE}/{path}',
                        query=search_data.title,
                        display_date=date,
                        search_date=search_data.search_date,
                        cur_id=pack_cur_id([path]),
                    )
                )

            if pagination > 1 and pagination != idx + 1:
                next_url = f'{search_url}&page={idx}' if is_search_mode else f'{base}/pornstar/{slugify(search_data.title)}?related_page={idx}'
                nxt = await self._paced(next_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search page {idx}')
                if not nxt:
                    break

                page_sel = nxt['sel']

    async def _search_by_scene_id(self, results: list[SearchResult], search_data: SearchContext) -> bool:
        loaded = await self._paced(
            f'{_SCENE_BASE}/scene/0{search_data.scene_id}',
            FetchCtx(capture=search_data.capture),
            f'[{search_data.site_info.name}] sceneID {search_data.scene_id}',
        )
        if not loaded:
            return False

        sel = loaded['sel']
        title = (sel.xpath('(//div[contains(@class,"scene-info")]//h1)[1]').xpath('string(.)').get() or '').strip()
        if not title:
            return False

        canonical = sel.xpath('(//link[@rel="canonical"]/@href | //meta[@property="og:url"]/@content)[1]').get() or ''
        path = _scene_path(canonical) if '/scene/' in canonical else f'scene/0{search_data.scene_id}'
        date = iso_date((sel.xpath('(//div[contains(@class,"date-tags")]//span[contains(@class,"entry-date")])[1]').xpath('string(.)').get() or '').strip())

        results.append(
            build_search_result(
                site=search_data.site_info,
                title=title,
                scene_url=f'{_SCENE_BASE}/{path}',
                query=search_data.title,
                display_date=date,
                search_date=search_data.search_date,
                score=100,
                cur_id=pack_cur_id([path]),
            )
        )
        return True

    # ── Context Loader (curID is the scene URL slug path) ────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        path = payload.split('|')[0].lstrip('/')
        url = f'{_SCENE_BASE}/{path}'
        loaded = await self._paced(url, FetchCtx(capture=ctx.capture if ctx else None, use_bypass=site.use_bypass), f'[{site.name}] detail {url}')
        if not loaded:
            return None

        return LoadedScene(url=url, site=site, capture=ctx.capture if ctx else None, sel=loaded['sel'], html=loaded['html'])

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _tagline_of(self, scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        return (details_page_elements.xpath('(//a[contains(@class,"site-title")])[1]').xpath('string(.)').get() or '').strip()

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        div = details_page_elements.xpath('(//div[contains(@class,"synopsis") and contains(@class,"grey-text")])[1]')

        metadata.summary = ''.join(div.xpath('.//text()[not(ancestor::h2)]').getall()).strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline_of(scene) or ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        tag = self._tagline_of(scene)

        metadata.collections = [tag] if tag else None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (
            details_page_elements.xpath('(//div[contains(@class,"date-tags")]//span[contains(@class,"entry-date")])[1]').xpath('string(.)').get() or ''
        ).strip()

        metadata.release_date = iso_date(date) or None

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        names = [
            actor_name
            for actor_name in (
                first_attr(actor_link, 'normalize-space(.)') for actor_link in details_page_elements.xpath('//div[contains(@class,"performer-list")]//a')
            )
            if actor_name
        ]
        _, scene_first = scene_image_pref()

        actors: list[ActorResult] = []
        for actor_name in names:
            photo_url = ''
            if scene_first:
                slug = actor_name.lower().replace(' ', '-').replace("'", '')
                page = await self._paced(f'{_SCENE_BASE}/pornstar/{slug}', None, f'GET pornstar {slug}')
                raw = first_attr(page['sel'], '(//img[contains(@class,"performer-pic")])[1]/@data-src') if page else ''
                photo_url = to_https(raw) if raw else ''

            actors.append(ActorResult(name=actor_name, photo_url=photo_url))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda u: _IMAGES_CDN_RE.sub('images1', to_https(u), 1))
        xpaths = (
            '//div[contains(@class,"contain-scene-images") and contains(@class,"desktop-only")]/a/@href',
            '//a[@class="play-trailer"]/picture[1]//source[contains(@data-srcset,"jpg")]/@data-srcset',
            '//dl8-video/@poster[contains(.,"jpg")]',
        )
        for xpath in xpaths:
            for image_url in details_page_elements.xpath(xpath).getall():
                images.push(image_url)

        metadata.art = images.items

        await self.enrich_from_data18(
            metadata,
            scene.site,
            scene_id=mapping_slug(metadata.title, scene.site.name),
            providers=[scene.site.name],
        )
