from __future__ import annotations

import re

import httpx2
from parsel import Selector

from phoenixadult.clients.base import Client, LoadedScene
from phoenixadult.models.capture import RawCaptureEntry
from phoenixadult.models.scrape import SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text, meta_content, script_match, web_search_urls
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.logging.best_effort import best_effort

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


def _tagline(url: str) -> str:
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

        with best_effort(search_data.site_info.name, 'webSearch'):
            for url in await web_search_urls(search_data.title, search_data.site_info):
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
                    site=search_data.site_info,
                    title=title,
                    scene_url=content_url,
                    query=search_data.title,
                    display_date=date,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([x for x in (content_url, date) if x]),
                )
            )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = (details_page_elements.xpath('normalize-space((//h2[contains(@class,"vidtitle")])[1])').get() or '').replace('"', '').strip()

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//div[contains(@class,"vidinfo")]//p')

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = _tagline(scene.url)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [_tagline(scene.url)]

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
            for genre_name in meta_content(details_page_elements, 'keywords', 'name').split(','):
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

        def extract_photo(sel: Selector) -> str:
            raw = first_attr(sel, '(//div[contains(@class,"row") and contains(@class,"mainrow")]//img/@src)[1]')
            if not raw:
                return ''
            return raw if raw.startswith('http') else f'{base}/t1/{raw}'

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('//h3[contains(@class,"releases")]//a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name:
                refs.append((actor_name, f'{base}/t1/{href}' if href else ''))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture, label='actor')

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')
        images = self.image_collector(lambda image: image if 'http' in image else f'{base}/t1/{image}')
        script = details_page_elements.xpath('string((//div[contains(@class,"movie-big")]//script)[1])').get() or ''
        images.push(script_match(script, _IMAGE_RE).strip())

        for image_url in details_page_elements.xpath('//div[contains(@class,"movie-trailer")]//img/@src').getall():
            images.push((image_url or '').strip())

        metadata.art = images.items
