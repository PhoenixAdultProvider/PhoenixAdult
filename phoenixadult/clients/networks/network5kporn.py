from __future__ import annotations

from typing import ClassVar
from urllib.parse import quote

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, RawCaptureEntry, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.data18 import mapping_slug
from phoenixadult.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_attr
from phoenixadult.utils.processors.actor_strip import enabled_for, split_actor_prefix

STUDIO = '5Kporn'
_COOKIE = 'nats=MC4wLjMuNTguMC4wLjAuMC4w; ageConfirmed=true'
_MAX_PHOTOSET_PAGES = 20


def _cls(name: str) -> str:
    return f'contains(concat(" ",normalize-space(@class)," ")," {name} ")'


class Network5KPClient(Client):
    scraper_type: ClassVar[str] = '5kporn'

    def __init__(self) -> None:
        super().__init__({'Accept': 'application/json,text/html;q=0.9,*/*;q=0.8', 'Cookie': _COOKIE})

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        actor_query = split_actor_prefix(search_data.title)[0] if enabled_for(search_data.site_info) else search_data.title

        url = search_data.search_url(quote(actor_query))
        try:
            r = await self.http.get(url)
        except Exception:  # noqa: BLE001 - upstream failure yields no results
            return

        try:
            body = r.json() if 'json' in r.headers.get('content-type', '') else None
        except ValueError:
            body = None

        if isinstance(body, dict) and isinstance(body.get('html'), str):
            html = body['html']
        else:
            html = r.text

        if search_data.capture is not None:
            search_data.capture.append(RawCaptureEntry(f'GET {url}', 'json', body if body is not None else html))

        sel = Selector(text=html)
        seen: set[str] = set()
        for card in sel.xpath(f'//div[{_cls("ep")}]'):
            title = (card.xpath('(.//h3[contains(@class,"ep-title")])[1]').xpath('string(.)').get() or '').strip()
            scene_url = first_attr(card, '(.//a)[1]/@href')
            if not title or not scene_url or scene_url in seen:
                continue

            seen.add(scene_url)

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=actor_query,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, search_data.search_date) if x]),
                )
            )

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        parts = payload.split('|')
        scene_url = parts[0]
        fallback_date = parts[1] if len(parts) > 1 else ''
        capture = ctx.capture if ctx else None

        details_page_elements = await self.fetch_and_load(scene_url, FetchCtx(capture=capture, use_bypass=site.use_bypass), f'[{site.name}] detail {scene_url}')
        if not details_page_elements:
            return None

        return LoadedScene(
            url=scene_url, site=site, scene_date=fallback_date or None, capture=capture, sel=details_page_elements['sel'], html=details_page_elements['html']
        )

    async def update(self, metadata: SceneDetail, scene: LoadedScene) -> None:
        site = scene.site
        sel = scene.sel
        assert sel is not None
        scene_url = scene.url
        capture = scene.capture
        fallback_date = scene.scene_date or ''

        # Title
        metadata.title = (sel.xpath('(//title)[1]').xpath('string(.)').get() or '').split('|')[0].strip()

        # Summary
        metadata.summary = (sel.xpath('(//div[contains(@class,"video-summary")]//p[not(@class) or @class=""])[1]').xpath('string(.)').get() or '').strip()

        # Studio
        metadata.studio = STUDIO

        # Tagline and Collection(s)
        tagline = '5Kteens' if '5KT' in scene_url else site.name
        metadata.tagline = tagline if tagline != STUDIO else ''
        metadata.collections = [tagline]

        # Release Date
        release_date: str | None = None
        for h5 in sel.xpath('//h5'):
            txt = h5.xpath('string(.)').get() or ''
            if 'Published' in txt:
                release_date = iso_date(txt.replace('Published:', '').strip())
                break

        metadata.release_date = release_date or fallback_date or None

        # Genres
        metadata.genres = []

        # Actor(s)
        refs: list[tuple[str, str]] = []
        for a in sel.xpath('//h5[contains(.,"Starring")]//a'):
            name = first_attr(a, 'normalize-space(.)')
            href = first_attr(a, '@href')
            if name and href:
                refs.append((name, href))

        metadata.actors.extend(
            await self.resolve_actor_photos(
                refs, lambda model: first_attr(model, '(//img[contains(@class,"model-image")])[1]/@src'), capture=capture, label='actor'
            )
        )

        # Posters
        for src in sel.xpath('//div[contains(@class,"gal")]//img/@src').getall():
            if src:
                metadata.art.append(src)

        page_num, last_page = 1, 1
        while page_num <= min(last_page, _MAX_PHOTOSET_PAGES):
            photo_url = f'{scene_url.rstrip("/")}/photoset?page={page_num}'
            model_page_elements = await self.fetch_and_load(photo_url, FetchCtx(capture=capture), f'GET {photo_url}')
            if not model_page_elements:
                break
            if page_num == 1:
                numbers = [
                    int(text)
                    for text in model_page_elements['sel'].xpath('//ul[contains(@class,"pagination")]//a[contains(@class,"page-link")]/text()').getall()
                    if text.strip().isdigit()
                ]
                last_page = max(numbers, default=1)

            for src in model_page_elements['sel'].xpath('//img[contains(@class,"card-img-top")]/@src').getall():
                if src and 'full' not in src:
                    metadata.art.append(src)
            page_num += 1

        # Posters from Data18
        await self.enrich_from_data18(metadata, site, scene_id=mapping_slug(metadata.title, tagline), providers=[tagline, STUDIO])
