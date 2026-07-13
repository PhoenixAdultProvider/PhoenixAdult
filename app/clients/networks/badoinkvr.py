from __future__ import annotations

import re
from urllib.parse import quote

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

    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        cleaned = _mangle(ctx.title)

        if ctx.scene_id:
            url = f'{base}/vrpornvideo/{ctx.scene_id}'
            loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'GET {url}')
            if loaded:
                title = (loaded['sel'].xpath('(//h1[contains(@class,"video-title")])[1]').xpath('string(.)').get() or '').strip()
                if title:
                    thumb = first_attr(loaded['sel'], '(//img[contains(@class,"video-image")])[1]/@src')
                    results.append(
                        build_search_result(title=title, scene_url=url, query=ctx.title, search_date=ctx.search_date, score=100, thumb_url=thumb or None)
                    )
                    return

        query_clean_lower = cleaned.lower()
        enc = quote(cleaned, safe='')
        enc = re.sub(r'a%20Parody', '', enc, flags=re.IGNORECASE)
        enc = enc.replace('180', '')
        enc = re.sub(r'Parody', '', enc, flags=re.IGNORECASE)
        search_url = base + ctx.site_info.search_path.replace('{query}', enc)
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'GET {search_url}')
        if not loaded:
            return
        for el in loaded['sel'].xpath('//div[contains(@class,"tile-grid-item")]'):
            a = el.xpath('(.//a[contains(@class,"video-card-title")])[1]')
            title_attr = (a.xpath('@title').get() or a.xpath('string(.)').get() or '').strip()
            href = first_attr(a, '@href')
            if not title_attr or not href:
                continue
            abs_href = absolute_url(href, ctx.site_info.base_url)
            date_raw = first_attr(el, '(.//span[contains(@class,"video-card-upload-date")])[1]/@content')
            release = iso_date(date_raw)
            if ctx.search_date and release:
                score: float = date_distance_score(ctx.search_date, release)
            else:
                score = title_distance_score(query_clean_lower, _title_clean_lower(title_attr))
            results.append(
                build_search_result(title=title_attr, scene_url=abs_href, query=ctx.title, display_date=release, search_date=ctx.search_date, score=score)
            )

    # ── Field hooks ───────────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = (scene.sel.xpath('(//h1[contains(@class,"video-title")])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = (scene.sel.xpath('(//p[contains(@class,"video-description")])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name if scene.site.name != STUDIO else None

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = first_attr(scene.sel, '(//p[@itemprop="uploadDate"])[1]/@content')
        metadata.release_date = iso_date(raw) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        genres = [g for g in (first_attr(a, 'normalize-space(.)') for a in scene.sel.xpath('//a[contains(@class,"video-tag")]')) if g]
        metadata.genres = genres or []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        base = scene.site.base_url
        refs: list[tuple[str, str]] = []
        for el in scene.sel.xpath('//a[contains(@class,"video-actor-link")]'):
            name = first_attr(el, 'normalize-space(.)')
            href = first_attr(el, '@href')
            if name and href:
                refs.append((name, absolute_url(href, base)))
        actors: list[ActorResult] = []
        for name, href in refs:
            loaded = await self.fetch_and_load(href, None, f'GET {href} (actor)')
            # Full resolved photo URL (no ?-strip), per the image-URL policy.
            photo = first_attr(loaded['sel'], '(//img[contains(@class,"girl-details-photo")])[1]/@src') if loaded else ''
            actors.append(ActorResult(name=name, photo_url=photo, gender='female'))
        metadata.actors = actors or []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        out: list[str] = []
        video_img = first_attr(scene.sel, '(//img[contains(@class,"video-image")])[1]/@src')
        if video_img:
            out.append(video_img)

        gallery_big = first_attr(scene.sel, '(//div[contains(@class,"gallery-item")])[1]/@data-big-image')
        if gallery_big:
            base_img = re.sub(r'_\d+\.jpg.*$', '', gallery_big)
            base_img = re.sub(r'\.jpg.*$', '', base_img)
            zip_info = scene.sel.xpath('(//span[contains(@class,"gallery-zip-info")])[1]').xpath('string(.)').get() or ''
            m = re.search(r'(\d+)\s*photos', zip_info, re.IGNORECASE)
            count = int(m.group(1)) if m else 0
            for i in range(1, count + 2):
                out.append(f'{base_img}_{i}.jpg')

        deduped = list(dict.fromkeys(u for u in out if u))
        metadata.art = deduped or []
