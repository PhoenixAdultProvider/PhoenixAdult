from __future__ import annotations

import re
from urllib.parse import urlsplit

import httpx2
from parsel import Selector

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, RawCaptureEntry, SearchContext, SearchResult
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text
from app.utils.logging.best_effort import best_effort
from app.utils.searchengines import SearchOptions, web_search

_SCENE_ID_RE = re.compile(r'(?:(?<=\dpp/)|(?<=\dbbwd/)|(?<=\dhsp/)|(?<=\dbbbj/)|(?<=\dpatp/)|(?<=\dftf/)|(?<=\dbgb/))\d+(?=/)')
_IMAGE_RE = re.compile(r'image:\s*"([^"]+)"')
_TOUR_TAGLINES: list[tuple[str, str]] = [
    ('bbwd/', 'BBW Dreams'),
    ('bbbj/', 'Big Babe Blowjobs'),
    ('hsp/', 'Hot Sexy Plumpers'),
    ('patp/', 'Plumpers At Play'),
    ('ftf/', 'First Time Fatties'),
    ('bgb/', 'BBWs Gone Black'),
]


def _release_text(sel: Selector) -> str:
    for t in sel.xpath('//h3[contains(@class,"releases")]/text()').getall():
        t = t.strip()
        if t:
            return t
    return ''


class PlumperPassClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')

        def refstat(scene_id: str) -> str:
            return f'{base}/t1/refstat.php?lid={scene_id}&sid=584'

        ref_urls: list[str] = []
        if ctx.scene_id:
            ref_urls.append(refstat(ctx.scene_id))
        host = urlsplit(ctx.site_info.base_url).hostname or ''
        with best_effort(ctx.site_info.name, 'webSearch'):
            for url in await web_search(SearchOptions(query=ctx.title, site=host, num=10)):
                m = _SCENE_ID_RE.search(url)
                if m and 'content' in url:
                    ref = refstat(m.group(0))
                    if ref not in ref_urls:
                        ref_urls.append(ref)

        results: list[SearchResult] = []
        for ref_url in ref_urls:
            try:
                r = await self.http.get(ref_url)
            except httpx2.HTTPError:
                continue
            content_url = str(r.url)
            if 'content' not in content_url:
                continue
            if ctx.capture is not None:
                ctx.capture.append(RawCaptureEntry(f'GET {ref_url} -> {content_url}', 'html', r.text))
            sel = Selector(text=r.text)
            title = (sel.xpath('normalize-space((//h2[contains(@class,"vidtitle")])[1])').get() or '').replace('"', '').strip()
            if not title:
                continue
            raw_date = _release_text(sel)
            date = iso_date(raw_date, '%B %d, %Y') if raw_date else None
            results.append(
                build_search_result(
                    title=title,
                    scene_url=content_url,
                    query=ctx.title,
                    display_date=date,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([x for x in (content_url, date) if x]),
                )
            )
        return results

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('normalize-space((//h2[contains(@class,"vidtitle")])[1])').get() or '').replace('"', '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"vidinfo")]//p') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'PlumperPass'

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        for token, tagline in _TOUR_TAGLINES:
            if token in scene.url:
                return tagline
        return 'PlumperPass'

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [await self.fetch_tagline(scene) or 'PlumperPass']

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        return scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres: list[str] = []
        tag_links = scene.sel.xpath('//p[contains(@class,"tags") and contains(@class,"clearfix")]//a')
        if tag_links:
            for a in tag_links:
                g = first_attr(a, 'normalize-space(.)')
                if g and g not in genres:
                    genres.append(g)
        else:
            for g in (scene.sel.xpath('(//meta[@name="keywords"]/@content)[1]').get() or '').split(','):
                t = g.strip()
                if t and t not in genres:
                    genres.append(t)
        cast = len(scene.sel.xpath('//h3[contains(@class,"releases")]//a'))
        if cast == 3:
            genres.append('Threesome')
        elif cast == 4:
            genres.append('Foursome')
        elif cast > 4:
            genres.append('Orgy')
        return genres

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        actors: list[ActorResult] = []
        for el in scene.sel.xpath('//h3[contains(@class,"releases")]//a'):
            name = first_attr(el, 'normalize-space(.)')
            if not name:
                continue
            photo = ''
            href = first_attr(el, '@href')
            if href:
                loaded = await self.fetch_and_load(f'{base}/t1/{href}', FetchCtx(capture=scene.capture), f'GET {href} (actor)')
                raw = first_attr(loaded['sel'], '(//div[contains(@class,"row") and contains(@class,"mainrow")]//img/@src)[1]') if loaded else ''
                photo = (raw if raw.startswith('http') else f'{base}/t1/{raw}') if raw else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        images: list[str] = []

        def push(raw: str) -> None:
            raw = (raw or '').strip()
            if not raw:
                return
            abs_url = raw if 'http' in raw else f'{base}/t1/{raw}'
            if abs_url not in images:
                images.append(abs_url)

        script = scene.sel.xpath('string((//div[contains(@class,"movie-big")]//script)[1])').get() or ''
        m = _IMAGE_RE.search(script)
        if m:
            push(m.group(1))
        for raw in scene.sel.xpath('//div[contains(@class,"movie-trailer")]//img/@src').getall():
            push(raw)
        return images
