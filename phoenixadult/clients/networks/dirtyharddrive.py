from __future__ import annotations

import re

import httpx2

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, title_distance_score
from phoenixadult.utils.helpers.html_helpers import first_attr
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.searchengines import SearchOptions, web_search_available, web_search_filtered

STUDIO = 'Dirty Hard Drive'
_URL_CONTAINS = '/tour1/'
_URL_ENDS_WITH = '.html'
_PLAYLIST_RE = re.compile(r"""['"]playlistfile['"]\s*:\s*['"]([^'"]+playlist\.xml)['"]""", re.IGNORECASE)
_BOOKEND_IMG_RE = re.compile(r"""['"]image['"]\s*:\s*['"]([^'"]+bookend\.jpg)['"]""", re.IGNORECASE)
_PLAYLIST_THUMB_RE = re.compile(r"""<media:thumbnail[^>]*\burl=["']([^"']+)["']""", re.IGNORECASE)


class DirtyHardDriveClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        if not web_search_available():
            return

        host = httpx2.URL(search_data.site_info.base_url).host
        try:
            candidates = await web_search_filtered(
                SearchOptions(query=search_data.title, site=host, num=10), url_contains=_URL_CONTAINS, url_ends_with=_URL_ENDS_WITH
            )
        except Exception:  # noqa: BLE001 - search is best-effort
            return

        for url in candidates:
            details_page_elements = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] candidate {url}')
            if not details_page_elements:
                continue

            title = (details_page_elements['sel'].xpath('(//h1)[1]').xpath('string(.)').get() or '').strip()
            if not title:
                continue

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=url,
                    query=search_data.title,
                    search_date=search_data.search_date,
                    score=title_distance_score(search_data.title, title),
                )
            )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = (details_page_elements.xpath('(//h1)[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = (details_page_elements.xpath('(//div[@id="video-page-desc"])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name if scene.site.name != STUDIO else ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = scene.scene_date or None

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        spans = details_page_elements.xpath('//div[@id="video-specs"]//span')
        if not spans:
            return

        last = spans[-1]
        actor_name = first_attr(last)
        href = (last.xpath('(.//a)[1]/@href').get() or last.xpath('@href').get() or '').strip()

        if not actor_name and href:
            tail = href.split('/')[-1]
            actor_name = re.sub(r'\.html$', '', tail, flags=re.IGNORECASE).replace('pornstar_', '', 1).replace('_', ' ').strip().title()

        if not actor_name:
            return

        photo = ''
        if href:
            model_page_elements = await self.fetch_and_load(absolute_url(href, scene.site.base_url), None, f'[{scene.site.name}] actor')
            if model_page_elements:
                raw = first_attr(model_page_elements['sel'], '(//div[@id="global-model-img"]//img)[1]/@src')
                if raw:
                    photo = absolute_url(raw, scene.site.base_url)

        metadata.actors = [ActorResult(name=actor_name, photo_url=photo)]

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        if not scene.html:
            return

        m = _PLAYLIST_RE.search(scene.html)
        if m:
            playlist_url = absolute_url(m.group(1), scene.site.base_url)
            try:
                r = await self.http.get(playlist_url)
                if r.status_code < 400:
                    thumb = _PLAYLIST_THUMB_RE.search(r.text)
                    if thumb:
                        metadata.art = [absolute_url(thumb.group(1), scene.site.base_url)]
                        return
            except httpx2.HTTPError as err:
                logger.debug(f'playlist fetch {playlist_url} failed: {err}')

        fallback = _BOOKEND_IMG_RE.search(scene.html)
        if fallback:
            metadata.art = [absolute_url(fallback.group(1), scene.site.base_url)]
