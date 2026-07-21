from __future__ import annotations

from urllib.parse import quote

from parsel import Selector

from app.clients.aggregators.data18 import mapping_slug
from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, RawCaptureEntry, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr
from app.utils.processors.actor_strip import enabled_for, split_actor_prefix

STUDIO = '5Kporn'
_COOKIE = 'nats=MC4wLjMuNTguMC4wLjAuMC4w; ageConfirmed=true'


def _cls(name: str) -> str:
    """Whole-class-token match (CSS `.name`) — avoids `contains` over-matching."""
    return f'contains(concat(" ",normalize-space(@class)," ")," {name} ")'


class Network5KPClient(Client):
    def __init__(self) -> None:
        super().__init__({'Accept': 'application/json,text/html;q=0.9,*/*;q=0.8', 'Cookie': _COOKIE})

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        """The site search is actor-based: with SEARCH_STRIP_ACTORS on, the filename's
        leading actor names become the query; otherwise the full title is sent."""
        actor_query = split_actor_prefix(search_data.title)[0] if enabled_for(search_data.site_info) else search_data.title

        url = search_data.site_info.base_url.rstrip('/') + search_data.site_info.search_path.replace('{query}', quote(actor_query))
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
        for el in sel.xpath(f'//div[{_cls("ep")}]'):
            title = (el.xpath('(.//h3[contains(@class,"ep-title")])[1]').xpath('string(.)').get() or '').strip()
            scene_url = first_attr(el, '(.//a)[1]/@href')
            if not title or not scene_url or scene_url in seen:
                continue

            seen.add(scene_url)

            results.append(
                build_search_result(
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

        details_page_elements = await self.fetch_and_load(scene_url, FetchCtx(capture=capture), f'[{site.name}] detail {scene_url}')
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
        metadata.tagline = tagline if tagline != STUDIO else None
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
        for a in sel.xpath('//h5[contains(.,"Starring")]//a'):
            name = first_attr(a, 'normalize-space(.)')
            href = first_attr(a, '@href')
            if not name or not href:
                continue

            model_page_elements = await self.fetch_and_load(href, FetchCtx(capture=capture), f'GET {href} (actor)')
            photo = first_attr(model_page_elements['sel'], '(//img[contains(@class,"model-image")])[1]/@src') if model_page_elements else ''
            metadata.actors.append(ActorResult(name=name, photo_url=photo))

        # Posters
        for src in sel.xpath('//div[contains(@class,"gal")]//img/@src').getall():
            if src:
                metadata.art.append(src)

        for page_num in (1, 2):
            photo_url = f'{scene_url.rstrip("/")}/photoset?page={page_num}'
            model_page_elements = await self.fetch_and_load(photo_url, FetchCtx(capture=capture), f'GET {photo_url}')
            if not model_page_elements:
                continue

            for src in model_page_elements['sel'].xpath('//img[contains(@class,"card-img-top")]/@src').getall():
                if src and 'full' not in src:
                    metadata.art.append(src)

        # Posters from Data18
        await self.enrich_from_data18(metadata, site, scene_id=mapping_slug(metadata.title, tagline), providers=[tagline, STUDIO])
