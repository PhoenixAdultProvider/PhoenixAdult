from __future__ import annotations

import re
from urllib.parse import quote

from app.clients.aggregators.data18 import mapping_slug
from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, date_distance_score, iso_date, title_distance_score
from app.utils.helpers.html_helpers import first_attr

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


class BadoinkVrClient(Client):
    # ── Search (full override: direct sceneID lookup + search page) ──────────────

    async def search(self, results: list[SearchResult], searchData: SearchContext) -> None:
        base = searchData.site_info.base_url.rstrip('/')
        cleaned = _mangle(searchData.title)

        if searchData.scene_id:
            url = f'{base}/vrpornvideo/{searchData.scene_id}'
            directPageElements = await self.fetch_and_load(url, FetchCtx(capture=searchData.capture), f'GET {url}')
            if directPageElements:
                title = (directPageElements['sel'].xpath('(//h1[contains(@class,"video-title")])[1]').xpath('string(.)').get() or '').strip()
                if title:
                    thumb = first_attr(directPageElements['sel'], '(//img[contains(@class,"video-image")])[1]/@src')
                    results.append(
                        build_search_result(
                            title=title, scene_url=url, query=searchData.title, search_date=searchData.search_date, score=100, thumb_url=thumb or None
                        )
                    )
                    return

        query_clean_lower = cleaned.lower()
        enc = quote(cleaned, safe='')
        search_url = base + searchData.site_info.search_path.replace('{query}', enc)
        searchResults = await self.fetch_and_load(search_url, FetchCtx(capture=searchData.capture), f'GET {search_url}')
        if not searchResults:
            return

        for searchResult in searchResults['sel'].xpath('//div[contains(@class,"tile-grid-item")]'):
            a = searchResult.xpath('(.//a[contains(@class,"video-card-title")])[1]')
            title_attr = (a.xpath('@title').get() or a.xpath('string(.)').get() or '').strip()
            href = first_attr(a, '@href')
            if not title_attr or not href:
                continue

            abs_href = absolute_url(href, searchData.site_info.base_url)

            date_raw = first_attr(searchResult, '(.//span[contains(@class,"video-card-upload-date")])[1]/@content')
            release = iso_date(date_raw)
            if searchData.search_date and release:
                score: float = date_distance_score(searchData.search_date, release)
            else:
                score = title_distance_score(query_clean_lower, _title_clean_lower(title_attr))

            results.append(
                build_search_result(
                    title=title_attr, scene_url=abs_href, query=searchData.title, display_date=release, search_date=searchData.search_date, score=score
                )
            )

    # ── Field hooks ───────────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        detailsPageElements = scene.require_sel()
        metadata.title = (detailsPageElements.xpath('(//h1[contains(@class,"video-title")])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        detailsPageElements = scene.require_sel()
        metadata.summary = (detailsPageElements.xpath('(//p[contains(@class,"video-description")])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name if scene.site.name != STUDIO else None

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        detailsPageElements = scene.require_sel()

        date = first_attr(detailsPageElements, '(//p[@itemprop="uploadDate"])[1]/@content')
        metadata.release_date = iso_date(date) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        detailsPageElements = scene.require_sel()

        genres = [genre for genre in (first_attr(a, 'normalize-space(.)') for a in detailsPageElements.xpath('//a[contains(@class,"video-tag")]')) if genre]
        metadata.genres = genres or []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        detailsPageElements = scene.require_sel()

        refs: list[tuple[str, str]] = []
        for actorLink in detailsPageElements.xpath('//a[contains(@class,"video-actor-link")]'):
            actorName = first_attr(actorLink, 'normalize-space(.)')
            actorPhotoURL = first_attr(actorLink, '@href')

            if actorName and actorPhotoURL:
                refs.append((actorName, absolute_url(actorPhotoURL, scene.site.base_url)))

        actors: list[ActorResult] = []
        for actorName, href in refs:
            modelPageElements = await self.fetch_and_load(href, None, f'GET {href} (actor)')
            actorPhotoURL = first_attr(modelPageElements['sel'], '(//img[contains(@class,"girl-details-photo")])[1]/@src') if modelPageElements else ''

            actors.append(ActorResult(name=actorName, photo_url=actorPhotoURL, gender='female'))

        metadata.actors = actors or []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        detailsPageElements = scene.require_sel()
        images: list[str] = []

        video_img = first_attr(detailsPageElements, '(//img[contains(@class,"video-image")])[1]/@src')
        if video_img:
            images.append(video_img)

        gallery_imgs = detailsPageElements.xpath('(//div[contains(@class,"gallery-item")])/@data-big-image')
        images.extend(u for u in gallery_imgs.getall() if u)

        gallery_big = first_attr(detailsPageElements, '(//div[contains(@class,"gallery-item")])[1]/@data-big-image')
        if gallery_big:
            raw_img_url = re.sub(r'_\d+\.jpg.*$', '', gallery_big)
            base_img = re.sub(r'\.jpg.*$', '', raw_img_url)
            zip_info = detailsPageElements.xpath('(//span[contains(@class,"gallery-zip-info")])[1]').xpath('string(.)').get() or ''
            m = re.search(r'(\d+)\s*photos', zip_info, re.IGNORECASE)
            count = int(m.group(1)) if m else 0
            if '@' in base_img:
                parts = re.match(r'^(.*/\d+)_\d+_(\d+@.*)$', base_img)
                if parts:
                    images.extend(f'{parts.group(1)}_{i}_{parts.group(2)}.jpg' for i in range(1, count + 1))
                else:
                    images.append(f'{base_img}.jpg')
            elif base_img:
                images.extend(f'{base_img}_{i}.jpg' for i in range(1, count + 2))

        deduped = list(dict.fromkeys(u for u in images if u))
        metadata.art = deduped or []

        # Posters from Data18
        await self.enrich_from_data18(
            metadata, scene.site, scene_id=mapping_slug(metadata.title, scene.site.name), providers=[scene.site.name, STUDIO], allow_square=False
        )
