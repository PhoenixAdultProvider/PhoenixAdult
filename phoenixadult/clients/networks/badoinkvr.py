from __future__ import annotations

import asyncio
import re
from urllib.parse import quote, urlsplit

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.data18 import mapping_slug
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr
from phoenixadult.utils.helpers.scoring import date_distance_score, title_distance_score
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.helpers.urls import absolute_url
from phoenixadult.utils.images.image_fetcher import fetch_dimensions

STUDIO = 'BaDoink VR'


def _mangle(q: str) -> str:
    q = re.sub(r'a\s+Parody', '', q, flags=re.IGNORECASE)
    q = re.sub(r'\b180\b', '', q)
    q = re.sub(r'Parody', '', q, flags=re.IGNORECASE)
    return q.strip()


def _title_clean_lower(title: str) -> str:
    t = re.sub(r'Parody', '', title, flags=re.IGNORECASE)
    t = re.sub(r'[^\w\s]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip().lower()


__testing__ = {'mangle': _mangle, 'title_clean_lower': _title_clean_lower}

_MAX_GALLERY_IMAGES = 600


class BadoinkVrClient(Client):
    summary_xpath = ('(//div[contains(@class,"video-description-container")])[1]', '(//p[contains(@class,"video-description")])[1]')

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        cleaned = _mangle(search_data.title)

        if search_data.scene_id:
            url = f'{base}/vrpornvideo/{search_data.scene_id}'
            direct_page_elements = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'GET {url}')
            if direct_page_elements:
                title = (direct_page_elements['sel'].xpath('(//h1[contains(@class,"video-title")])[1]').xpath('string(.)').get() or '').strip()
                if title:
                    thumb = first_attr(direct_page_elements['sel'], '(//img[contains(@class,"video-image")])[1]/@src')
                    results.append(
                        build_search_result(
                            site=search_data.site_info,
                            title=title,
                            scene_url=url,
                            query=search_data.title,
                            search_date=search_data.search_date,
                            score=100,
                            thumb_url=thumb or None,
                        )
                    )
                    return

        query_clean_lower = cleaned.lower()
        enc = quote(cleaned, safe='')
        search_url = search_data.search_url(enc)
        search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'GET {search_url}')
        if not search_results:
            return

        for search_result in search_results['sel'].xpath('//div[contains(@class,"tile-grid-item")]'):
            a = search_result.xpath('(.//a[contains(@class,"video-card-title")])[1]')
            title_attr = (a.xpath('@title').get() or a.xpath('string(.)').get() or '').strip()
            href = first_attr(a, '@href')
            if not title_attr or not href:
                continue

            abs_href = absolute_url(href, search_data.site_info.base_url)

            date_raw = first_attr(search_result, '(.//span[contains(@class,"video-card-upload-date")])[1]/@content')
            release = iso_date(date_raw)
            if search_data.search_date and release:
                score: float = date_distance_score(search_data.search_date, release)
            else:
                score = title_distance_score(query_clean_lower, _title_clean_lower(title_attr))

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title_attr,
                    scene_url=abs_href,
                    query=search_data.title,
                    display_date=release,
                    search_date=search_data.search_date,
                    score=score,
                )
            )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    @staticmethod
    def _slug_family(scene_url: str, gallery_big: str, count: int) -> list[str]:
        cdn = re.match(r'^(https?://[^/]+)/content/', gallery_big)
        segments = [s for s in urlsplit(scene_url).path.split('/') if s]
        slug_id = re.match(r'^(.+)-(\d+)$', segments[-1]) if segments else None
        if slug_id:
            slug, scene_id = slug_id.group(1).replace('_', '-'), slug_id.group(2)
        elif len(segments) >= 2 and segments[-2].isdigit():
            slug, scene_id = segments[-1], segments[-2]
        else:
            return []
        if not cdn:
            return []
        base = f'{cdn.group(1)}/content/scenes/{scene_id}/{slug}-{scene_id}'
        return [f'{base}.jpg', *(f'{base}_{i}.jpg' for i in range(1, count + 1))]

    @staticmethod
    async def _existing(urls: list[str]) -> list[str]:
        dims = await asyncio.gather(*(fetch_dimensions(u) for u in urls))
        return [u for u, d in zip(urls, dims, strict=True) if d]

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()
        metadata.title = (details_page_elements.xpath('(//h1[contains(@class,"video-title")])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name if scene.site.name != STUDIO else ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_attr(details_page_elements, '(//p[@itemprop="uploadDate"])[1]/@content')
        metadata.release_date = iso_date(date) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres = [genre for genre in (first_attr(a, 'normalize-space(.)') for a in details_page_elements.xpath('//a[contains(@class,"video-tag")]')) if genre]
        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        def extract_photo(sel: Selector) -> str:
            return first_attr(sel, '(//img[contains(@class,"girl-details-photo")])[1]/@src')

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('//a[contains(@class,"video-actor-link")]'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            actor_photo_url = first_attr(actor_link, '@href')

            if actor_name and actor_photo_url:
                refs.append((actor_name, absolute_url(actor_photo_url, scene.site.base_url)))

        resolved = await self.resolve_actor_photos(refs, extract_photo, label='actor')
        metadata.actors = [ActorResult(name=a.name, photo_url=a.photo_url, gender='female') for a in resolved]

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()
        images: list[str] = []

        video_img = first_attr(details_page_elements, '(//img[contains(@class,"video-image")])[1]/@src')
        if video_img:
            images.append(video_img)

        gallery_imgs = [u for u in details_page_elements.xpath('//div[contains(@class,"gallery-item")]/@data-big-image').getall() if u]
        images.extend(gallery_imgs)

        zip_info = details_page_elements.xpath('(//span[contains(@class,"gallery-zip-info")])[1]').xpath('string(.)').get() or ''
        m = re.search(r'(\d+)\s*photos', zip_info, re.IGNORECASE)
        count = min(int(m.group(1)), _MAX_GALLERY_IMAGES) if m else 0

        candidates: list[str] = []
        gallery_big = gallery_imgs[0] if gallery_imgs else ''
        if gallery_big and count:
            base_img = re.sub(r'\.jpg.*$', '', re.sub(r'_\d+\.jpg.*$', '', gallery_big))
            parts = re.match(r'^(.*/\d+)_\d+_(\d+@.*)$', base_img)
            if parts:
                candidates.extend(f'{parts.group(1)}_{i}_{parts.group(2)}.jpg' for i in range(1, count + 1))
            elif '@' not in base_img and base_img:
                candidates.extend(f'{base_img}_{i}.jpg' for i in range(1, count + 1))
            candidates.extend(self._slug_family(scene.url, gallery_big, count))

        known = set(images)
        fresh = [c for c in dict.fromkeys(candidates) if c not in known]
        images.extend(await self._existing(fresh))

        deduped = list(dict.fromkeys(u for u in images if u))
        metadata.art = deduped

        # Posters from Data18
        await self.enrich_from_data18(
            metadata,
            scene.site,
            scene_id=mapping_slug(metadata.title, scene.site.name),
            providers=[scene.site.name, STUDIO],
            title=metadata.title.replace('Remastered', '').strip(),
            allow_square=False,
        )
