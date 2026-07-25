from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote, urlparse

from parsel import Selector

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, date_distance_score, iso_date, strip_query, title_distance_score
from phoenixadult.utils.helpers.html_helpers import first_attr
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.searchengines import SearchOptions, web_search, web_search_available

STUDIO = 'Bang!'

_BANG_RE = re.compile(r'\bbang(?=(?:\s|$))(?!!)', re.IGNORECASE)
_TAG_RE = re.compile(r'<[^>]+>')
_WS_RE = re.compile(r'\s+')


def _bangify(s: str) -> str:
    return _BANG_RE.sub('Bang!', s) if s else s


def _strip_html(s: str | None) -> str:
    if not s:
        return ''

    return _WS_RE.sub(' ', _TAG_RE.sub('', s)).strip()


def _find_video_ld(sel: Any) -> dict[str, Any] | None:
    for script in sel.xpath('//script[@type="application/ld+json"]'):
        txt = (script.xpath('string(.)').get() or '').replace('\n', '').strip()
        try:
            data = json.loads(txt)
        except (ValueError, TypeError):
            continue

        if isinstance(data, dict) and data.get('@type') == 'VideoObject':
            return data

    return None


__testing__ = {'bangify': _bangify, 'strip_html': _strip_html, 'find_video_ld': _find_video_ld}


class BangClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        seen: set[str] = set()

        if web_search_available():
            host = urlparse(search_data.site_info.base_url).netloc
            try:
                found = await web_search(SearchOptions(query=search_data.title, site=host))
            except Exception as err:  # noqa: BLE001 - search engines are best-effort
                found = []
                logger.warn(search_data.site_info.name, f'web search failed: {err}')

            for raw in found:
                url = strip_query(raw)
                if 'com/video/' not in url or 'index.php/' in url or url in seen:
                    continue

                seen.add(url)
                search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'GET {url}')
                if not search_results:
                    continue

                ld = _find_video_ld(search_results['sel'])
                if not ld:
                    continue

                title = _strip_html(ld.get('name'))
                if not title:
                    continue

                release = iso_date(ld['datePublished']) if ld.get('datePublished') else None

                results.append(
                    build_search_result(
                        site=search_data.site_info,
                        title=_bangify(title),
                        scene_url=url,
                        query=search_data.title,
                        display_date=release,
                        search_date=search_data.search_date,
                    )
                )

        enc = quote(search_data.title, safe='').replace('%20', '+')
        search_url = base + search_data.site_info.search_path.replace('{query}', enc)
        search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'GET {search_url}')
        if search_results:
            for search_result in search_results['sel'].xpath('//div[contains(@class,"movie-preview") or contains(@class,"video_container")]'):
                href = first_attr(search_result, '(.//a[contains(@class,"group")])[1]/@href')
                if not href:
                    continue

                if 'dvd' in href:
                    title = (search_result.xpath('(.//a//div)[1]').xpath('string(.)').get() or '').strip()
                else:
                    title = (search_result.xpath('(.//a//span)[1]').xpath('string(.)').get() or '').strip()

                if not title:
                    continue

                scene_url = absolute_url(href, search_data.site_info.base_url)
                if scene_url in seen:
                    continue

                seen.add(scene_url)
                date_part = (
                    (search_result.xpath('(.//span[@class="hidden xs:inline-block truncate"])[1]').xpath('string(.)').get() or '').split('•')[-1].strip()
                )
                release = iso_date(date_part)
                score = (
                    date_distance_score(search_data.search_date, release)
                    if search_data.search_date and release
                    else title_distance_score(search_data.title, title)
                )

                results.append(
                    build_search_result(
                        site=search_data.site_info,
                        title=_bangify(title),
                        scene_url=scene_url,
                        query=search_data.title,
                        display_date=release,
                        search_date=search_data.search_date,
                        score=score,
                    )
                )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _studio_of(self, scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        ld = _find_video_ld(details_page_elements)
        raw = ''
        if ld:
            company = ld.get('productionCompany')
            if isinstance(company, dict):
                raw = (company.get('name') or '').strip()

        return _bangify(raw or STUDIO)

    def _tagline_of(self, scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        for row in details_page_elements.xpath('//p[contains(.,"eries:")]//a'):
            href = row.xpath('@href').get() or ''
            if 'originals' in href or 'videos' in href:
                return _bangify(first_attr(row, 'normalize-space(.)'))

        return ''

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        ld = _find_video_ld(details_page_elements)
        raw = _strip_html(ld.get('name')) if ld and ld.get('name') else (details_page_elements.xpath('(//h1)[1]').xpath('string(.)').get() or '').strip()

        metadata.title = _bangify(raw) or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        ld = _find_video_ld(details_page_elements)
        if ld and ld.get('description'):
            metadata.summary = _strip_html(ld['description']) or ''
            return

        desc = (details_page_elements.xpath('(//div[contains(@class,"description")])[1]').xpath('string(.)').get() or '').strip()
        if desc:
            metadata.summary = desc
            return

        meta = first_attr(details_page_elements, '(//meta[@name="description"])[1]/@content')
        og = first_attr(details_page_elements, '(//meta[@property="og:description"])[1]/@content')

        metadata.summary = meta or og or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = self._studio_of(scene)

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline_of(scene) or ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        tagline = self._tagline_of(scene)
        collections = [tagline] if tagline else [self._studio_of(scene)]
        dvd_title = (details_page_elements.xpath('(//p[contains(.,"Movie")]//a[contains(@href,"dvd")])[1]').xpath('string(.)').get() or '').strip()
        if dvd_title:
            collections.append(_bangify(dvd_title))

        metadata.collections = collections

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        ld = _find_video_ld(details_page_elements)
        iso = iso_date(ld['datePublished']) if ld and ld.get('datePublished') else None

        metadata.release_date = iso or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres = [
            genre_name
            for genre_name in (
                first_attr(genre_link, 'normalize-space(.)')
                for genre_link in details_page_elements.xpath('//div[contains(@class,"actions")]//a | //a[contains(@class,"genres")]')
            )
            if genre_name
        ]

        metadata.genres = genres or []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        scene_els = details_page_elements.xpath('//div[contains(@class,"name")]/a[contains(@href,"pornstar") and not(@aria-label)]')
        if scene_els:
            actors: list[ActorResult] = []
            for row in scene_els:
                actor_name = (row.xpath('(.//span)[1]').xpath('normalize-space(.)').get() or '').strip() or first_attr(row, 'normalize-space(.)')
                img = first_attr(row, '(ancestor::div[1]/parent::*//img)[1]/@src')
                photo = img if img and 'placeholder' not in img else ''
                if actor_name:
                    actors.append(ActorResult(name=actor_name, photo_url=photo))

            metadata.actors = actors or []
            return

        def extract_photo(sel: Selector) -> str:
            for s in sel.xpath('//script[@type="application/ld+json"]'):
                try:
                    blob = json.loads(s.xpath('string(.)').get() or '')
                except (ValueError, TypeError):
                    continue

                if isinstance(blob, dict) and blob.get('@type') == 'Person':
                    img = blob.get('image')
                    if isinstance(img, str):
                        return img.strip()

            return ''

        refs: list[tuple[str, str]] = []
        for row in details_page_elements.xpath('//div[contains(@class,"clear-both")]//a[contains(@href,"pornstar")]'):
            actor_name = first_attr(row, 'normalize-space(.)')
            href = first_attr(row, '@href')
            if actor_name and href:
                refs.append((actor_name, absolute_url(href, scene.site.base_url)))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo) or []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        ld = _find_video_ld(details_page_elements)
        out: list[str] = []

        if ld and isinstance(ld.get('thumbnailUrl'), str):
            thumb = ld['thumbnailUrl']
            if 'covers' in thumb:
                out.append(thumb)
            else:
                m = re.search(r'/shots/(\d+)', thumb)
                if m:
                    out.append(f'https://i.bang.com/covers/{m.group(1)}/front.jpg')

                out.append(thumb)

        if ld and isinstance(ld.get('trailer'), list):
            for t in ld['trailer']:
                if isinstance(t, dict) and t.get('thumbnailUrl'):
                    out.append(t['thumbnailUrl'])

        if not out:
            og = first_attr(details_page_elements, '(//meta[@property="og:image"])[1]/@content')
            if og:
                out.append(og)

            for poster in details_page_elements.xpath('//video/@poster').getall():
                if poster:
                    out.append(poster)

            for row in details_page_elements.xpath('//img[contains(@class,"object-cover") and contains(@class,"aspect-cover")]'):
                src = first_attr(row, '@src')
                if src:
                    out.append(src)

                srcset = row.xpath('@srcset').get() or ''
                for part in srcset.split(','):
                    token = part.strip().split(' ')[0].strip()
                    if token:
                        out.append(token)

        images = self.image_collector()
        for u in out:
            images['push'](u)

        metadata.art = images['list'] or []
