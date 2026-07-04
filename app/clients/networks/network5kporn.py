from __future__ import annotations

from urllib.parse import quote

from parsel import Selector

from app.clients.base import ActorResult, Client, FetchCtx, RawCaptureEntry, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr

STUDIO = '5Kporn'
_COOKIE = 'nats=MC4wLjMuNTguMC4wLjAuMC4w; ageConfirmed=true'


def _cls(name: str) -> str:
    """Whole-class-token match (CSS `.name`) — avoids `contains` over-matching."""
    return f'contains(concat(" ",normalize-space(@class)," ")," {name} ")'


class Network5KPClient(Client):
    def __init__(self) -> None:
        super().__init__({'Accept': 'application/json,text/html;q=0.9,*/*;q=0.8', 'Cookie': _COOKIE})

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        title_no_actors = ' '.join(ctx.title.split(' ')[2:])
        if title_no_actors.startswith('and '):
            title_no_actors = ' '.join(title_no_actors.split(' ')[3:])
        actor_query = ctx.title.replace(title_no_actors, '').strip()

        url = ctx.site_info.base_url.rstrip('/') + ctx.site_info.search_path.replace('{query}', quote(actor_query))
        try:
            r = await self.http.get(url)
        except Exception:  # noqa: BLE001 - upstream failure yields no results
            return []
        try:
            body = r.json() if 'json' in r.headers.get('content-type', '') else None
        except ValueError:
            body = None
        if isinstance(body, dict) and isinstance(body.get('html'), str):
            html = body['html']
        else:
            html = r.text
        if ctx.capture is not None:
            ctx.capture.append(RawCaptureEntry(f'GET {url}', 'json', body if body is not None else html))

        sel = Selector(text=html)
        results: list[SearchResult] = []
        seen: set[str] = set()
        # Whole-token `ep` match (mirrors the TS `div.ep`); a substring contains()
        # also hits nested `ep-*` wrappers and duplicates every card.
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
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, ctx.search_date) if x]),
                )
            )
        return results

    async def fetch_scene_detail(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> SceneDetail | None:
        parts = payload.split('|')
        scene_url = parts[0]
        fallback_date = parts[1] if len(parts) > 1 else ''
        capture = ctx.capture if ctx else None

        loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=capture), f'[{site.name}] detail {scene_url}')
        if not loaded:
            return None
        sel = loaded['sel']

        title = (sel.xpath('(//title)[1]').xpath('string(.)').get() or '').split('|')[0].strip()
        summary = (sel.xpath('(//div[contains(@class,"video-summary")]//p[not(@class) or @class=""])[1]').xpath('string(.)').get() or '').strip()
        tagline = '5Kteens' if '5KT' in scene_url else site.name

        release_date: str | None = None
        for h5 in sel.xpath('//h5'):
            txt = h5.xpath('string(.)').get() or ''
            if 'Published' in txt:
                release_date = iso_date(txt.replace('Published:', '').strip())
                break
        if not release_date and fallback_date:
            release_date = fallback_date

        actors: list[ActorResult] = []
        for a in sel.xpath('//h5[contains(.,"Starring")]//a'):
            name = first_attr(a, 'normalize-space(.)')
            href = first_attr(a, '@href')
            if not name or not href:
                continue
            page = await self.fetch_and_load(href, FetchCtx(capture=capture), f'GET {href} (actor)')
            photo = first_attr(page['sel'], '(//img[contains(@class,"model-image")])[1]/@src') if page else ''
            actors.append(ActorResult(name=name, photo_url=photo))

        raw_images: list[str] = []
        for src in sel.xpath('//div[contains(@class,"gal")]//img/@src').getall():
            if src:
                raw_images.append(src)
        for page_num in (1, 2):
            photo_url = f'{scene_url.rstrip("/")}/photoset?page={page_num}'
            page = await self.fetch_and_load(photo_url, FetchCtx(capture=capture), f'GET {photo_url}')
            if not page:
                continue
            for src in page['sel'].xpath('//img[contains(@class,"card-img-top")]/@src').getall():
                if src and 'full' not in src:
                    raw_images.append(src)

        return SceneDetail(
            title=title,
            summary=summary,
            studio=STUDIO,
            tagline=tagline if tagline != STUDIO else None,
            release_date=release_date or None,
            collections=[tagline],
            genres=[],
            actors=actors,
            raw_image_urls=raw_images,
            scene_url=scene_url,
        )
