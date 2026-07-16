from __future__ import annotations

import re
from urllib.parse import urlsplit

import httpx2
from parsel import Selector

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, RawCaptureEntry, SceneDetail, SearchContext, SearchResult
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


def _tagline_for(url: str) -> str:
    for token, tagline in _TOUR_TAGLINES:
        if token in url:
            return tagline

    return 'PlumperPass'


class PlumperPassClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')

        def refstat(scene_id: str) -> str:
            return f'{base}/t1/refstat.php?lid={scene_id}&sid=584'

        ref_urls: list[str] = []
        if search_data.scene_id:
            ref_urls.append(refstat(search_data.scene_id))

        host = urlsplit(search_data.site_info.base_url).hostname or ''
        with best_effort(search_data.site_info.name, 'webSearch'):
            for url in await web_search(SearchOptions(query=search_data.title, site=host, num=10)):
                m = _SCENE_ID_RE.search(url)
                if m and 'content' in url:
                    ref = refstat(m.group(0))
                    if ref not in ref_urls:
                        ref_urls.append(ref)

        for ref_url in ref_urls:
            try:
                r = await self.http.get(ref_url)
            except httpx2.HTTPError:
                continue

            content_url = str(r.url)
            if 'content' not in content_url:
                continue

            if search_data.capture is not None:
                search_data.capture.append(RawCaptureEntry(f'GET {ref_url} -> {content_url}', 'html', r.text))

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
                    query=search_data.title,
                    display_date=date,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([x for x in (content_url, date) if x]),
                )
            )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = (details_page_elements.xpath('normalize-space((//h2[contains(@class,"vidtitle")])[1])').get() or '').replace('"', '').strip()

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//div[contains(@class,"vidinfo")]//p')

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'PlumperPass'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = _tagline_for(scene.url)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [_tagline_for(scene.url)]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres: list[str] = []
        tag_links = details_page_elements.xpath('//p[contains(@class,"tags") and contains(@class,"clearfix")]//a')
        if tag_links:
            for a in tag_links:
                genre_name = first_attr(a, 'normalize-space(.)')
                if genre_name and genre_name not in genres:
                    genres.append(genre_name)
        else:
            for genre_name in (details_page_elements.xpath('(//meta[@name="keywords"]/@content)[1]').get() or '').split(','):
                t = genre_name.strip()
                if t and t not in genres:
                    genres.append(t)

        cast = len(details_page_elements.xpath('//h3[contains(@class,"releases")]//a'))
        if (group := self.group_genre_for(cast)) and group not in genres:
            genres.append(group)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')
        actors: list[ActorResult] = []
        for actor_link in details_page_elements.xpath('//h3[contains(@class,"releases")]//a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            if not actor_name:
                continue

            photo = ''
            href = first_attr(actor_link, '@href')
            if href:
                model_page_elements = await self.fetch_and_load(f'{base}/t1/{href}', FetchCtx(capture=scene.capture), f'GET {href} (actor)')
                raw = (
                    first_attr(model_page_elements['sel'], '(//div[contains(@class,"row") and contains(@class,"mainrow")]//img/@src)[1]')
                    if model_page_elements
                    else ''
                )
                photo = (raw if raw.startswith('http') else f'{base}/t1/{raw}') if raw else ''

            actors.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')
        images = self.image_collector(lambda image: image if 'http' in image else f'{base}/t1/{image}')
        script = details_page_elements.xpath('string((//div[contains(@class,"movie-big")]//script)[1])').get() or ''
        m = _IMAGE_RE.search(script)
        if m:
            images['push']((m.group(1) or '').strip())

        for image_url in details_page_elements.xpath('//div[contains(@class,"movie-trailer")]//img/@src').getall():
            images['push']((image_url or '').strip())

        metadata.art = images['list']
