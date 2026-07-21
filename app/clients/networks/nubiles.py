from __future__ import annotations

import asyncio
import random
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from parsel import Selector

from app.clients.aggregators.data18 import mapping_slug
from app.clients.base import ActorResult, Client, LoadedScene, RawCaptureEntry, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.captcha.pow import get_verified_cookies
from app.utils.helpers.helpers import build_search_result, iso_date, load_data, pack_cur_id, to_https
from app.utils.helpers.html_helpers import first_attr
from app.utils.http.rate_limit_helper import ScenePacer
from app.utils.images.image_fetcher import fetch_image
from app.utils.logging.logger import logger
from app.utils.people.sources import scene_image_pref
from app.utils.processors.actor_strip import best_title_score
from app.utils.processors.studio_name import normalize_studio

STUDIO = 'Nubiles'
_DEFAULT_PREFIX = '/video/gallery/'
_SHARED_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
}
_POSTER_SAMPLE_RE = re.compile(r'/videos/(.+)/sample')
_WATCH_ID_RE = re.compile(r'/video/watch/(\d+)')
_EPISODE_TAG_RE = re.compile(r'\s*-\s*S\d+\s*:?\s*E\d+\s*$', re.IGNORECASE)
_PACE_SECONDS = 7.0
_SCENE_COOLDOWN = 7.0
_PACE_JITTER = 3.0
_MAX_RETRIES = 3
_MAX_BACKOFF = 120.0
_IMAGE_CONCURRENCY = 4
_PACE_TAG = 'Nubiles:pace'


def strip_episode_tag(title: str) -> str:
    """Drop a trailing " - S2:E1"-style episode tag; interior hyphens are untouched."""
    return _EPISODE_TAG_RE.sub('', title).strip()


def _jittered(base: float) -> float:
    """A delay of `base` seconds plus up to _PACE_JITTER of randomness, so the cadence
    is not a fixed machine-perfect interval."""
    return base + random.uniform(0.0, _PACE_JITTER)


def _retry_after_seconds(resp: Any) -> float | None:
    """The Retry-After header as seconds (numeric or HTTP-date form), capped at
    _MAX_BACKOFF; None when the header is absent or unparseable."""
    val = (resp.headers.get('retry-after') or '').strip()
    if not val:
        return None
    if val.isdigit():
        return min(float(val), _MAX_BACKOFF)
    try:
        when = parsedate_to_datetime(val)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, min((when - datetime.now(UTC)).total_seconds(), _MAX_BACKOFF))


_SUMMARY_ACTORS: list[str] = load_data(__file__, 'nubiles_summary_actors')


def _best_variant(candidates: list[str]) -> str | None:
    """Largest photo variant among an img's src + srcset candidates. The size lives in
    the parent path segment — full-size has none, /459/ is a width, /tn/ a thumbnail —
    and the srcset width descriptors are unreliable (full-size can be labeled 50w)."""

    def rank(u: str) -> tuple[int, int]:
        parts = u.split('?')[0].split('/')
        parent = parts[-2] if len(parts) >= 2 else ''
        if parent == 'tn':
            return (0, 0)
        if parent.isdigit():
            return (1, int(parent))
        return (2, 0)

    pool = [u for u in candidates if u and not u.startswith('data:')]
    return max(pool, key=rank) if pool else None


class NubilesClient(Client):
    def __init__(self) -> None:
        super().__init__(_SHARED_HEADERS)
        self.pacer: ScenePacer = ScenePacer(_PACE_TAG, pace_seconds=_PACE_SECONDS, pace_jitter=_PACE_JITTER, cooldown_seconds=_SCENE_COOLDOWN)

    async def after_scene_scrape(self, detail: SceneDetail) -> None:
        await self._warm_images(detail)

    async def _warm_images(self, detail: SceneDetail) -> None:
        """Fetch the scene's images now, inside the scene gate and at most _IMAGE_CONCURRENCY
        at a time (a browser opens ~4-6 connections per host), so galleries of 100-250 photos
        never burst the shared CDN; the mapper then reads them from the image cache."""
        urls = [u for u in detail.art if u]
        if not urls:
            return
        referers = [detail.art_referer] if detail.art_referer else None
        cookies = [detail.art_cookie] if detail.art_cookie else None
        sem = asyncio.Semaphore(_IMAGE_CONCURRENCY)

        async def _warm_one(url: str) -> bool:
            async with sem:
                try:
                    await fetch_image(url, referers, cookies)
                    return True
                except Exception:  # noqa: BLE001 - a failed warm just falls back to the mapper
                    return False

        ok = sum(await asyncio.gather(*(_warm_one(u) for u in urls)))
        logger.info(_PACE_TAG, f'warmed {ok}/{len(urls)} scene images (<={_IMAGE_CONCURRENCY} concurrent)')

    async def _pow_pace(self) -> None:
        await self.pacer.pace('pow warm-up')

    async def _cookie_header_for(self, site: ResolvedSiteInfo) -> str:
        verified = await get_verified_cookies(site.base_url, challenge_path=site.search_path or _DEFAULT_PREFIX, pace=self._pow_pace) or {}
        cookies = {'18-plus-modal': 'hidden', **verified}
        return '; '.join(f'{k}={v}' for k, v in cookies.items())

    async def _get(self, url: str, site: ResolvedSiteInfo, capture: list[RawCaptureEntry] | None, label: str) -> Selector | None:
        cookie = await self._cookie_header_for(site)
        for attempt in range(1, _MAX_RETRIES + 1):
            await self.pacer.pace(label)
            try:
                r = await self.http.get(url, headers={'Cookie': cookie})
            except Exception as err:  # noqa: BLE001 - network errors yield no page
                logger.warn('Nubiles', f'{label} failed: {err!r}')
                return None
            if r.status_code != 429:
                break
            backoff = _retry_after_seconds(r) or _jittered(_PACE_SECONDS)
            logger.warn(_PACE_TAG, f'429 on {label}; backing off {backoff:.1f}s (attempt {attempt}/{_MAX_RETRIES})')
            await asyncio.sleep(backoff)
        else:
            logger.warn('Nubiles', f'{label} still rate-limited after {_MAX_RETRIES} attempts')
            return None

        if capture is not None:
            capture.append(RawCaptureEntry(label, 'html', r.text))

        return Selector(text=r.text)

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        """Searches ride the SAME gap track as scene updates: each search consumes a
        turn and arms the SCENE_GAP+jitter gap, deferring to the background when a
        Plex-facing request would have to wait it out."""
        async with self.pacer.search_gate(bool(search_data.allow_slow)):
            await self._search(results, search_data)

    async def _search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')

        scene_id = search_data.scene_id or None
        if scene_id:
            url = f'{base}/video/watch/{scene_id}'
            search_results = await self._get(url, search_data.site_info, search_data.capture, f'GET {url}')
            if search_results is not None:
                title = strip_episode_tag(
                    (search_results.xpath('(//div[contains(@class,"content-pane-title")]//h2)[1]').xpath('string(.)').get() or '').strip()
                )
                date = iso_date(
                    (search_results.xpath('(//div[contains(@class,"content-pane-title")]//span[@class="date"])[1]').xpath('string(.)').get() or '').strip()
                )
                if title:
                    results.append(
                        SearchResult(
                            title=title,
                            scene_url=url,
                            cur_id=pack_cur_id([x for x in (scene_id, date) if x]),
                            thumb_url=(search_results.xpath('(//video)[1]/@poster').get() or None),
                            release_date=date or search_data.search_date or None,
                            display_date=date,
                            score=100,
                        )
                    )

        if search_data.search_date:
            prefix = (search_data.site_info.search_path or _DEFAULT_PREFIX).rstrip('/') + '/'
            date_url = f'{base}{prefix}date/{search_data.search_date}/{search_data.search_date}'
            search_results = await self._get(date_url, search_data.site_info, search_data.capture, f'GET {date_url}')
            if search_results is not None:
                seen = {r.cur_id for r in results}
                for search_result in search_results.xpath('//div[contains(@class,"content-grid-item")]'):
                    title_a = search_result.xpath('(.//span[@class="title"]/a)[1]')
                    link_raw = first_attr(title_a, '@href')
                    raw_title = title_a.xpath('string(.)').get() or ''
                    parts = [p.strip() for p in raw_title.split('-')]
                    display_title = strip_episode_tag(f'{parts[0]} - {" - ".join(parts[1:])}' if len(parts) > 1 else parts[0])
                    segs = link_raw.split('/')
                    sid = segs[3] if len(segs) > 3 else ''
                    if not sid:
                        continue
                    raw_site = first_attr(search_result, 'string((.//a[contains(@class,"site-link")])[1])')
                    subsite = normalize_studio(re.sub(r'\.(?:com|net|xxx)$', '', raw_site, flags=re.IGNORECASE))

                    release_date = iso_date((search_result.xpath('(.//span[@class="date"])[1]').xpath('string(.)').get() or '').strip())
                    enc = pack_cur_id([x for x in (sid, release_date) if x])
                    if enc in seen:
                        continue

                    seen.add(enc)

                    results.append(
                        build_search_result(
                            title=display_title,
                            scene_url=link_raw if link_raw.startswith('http') else base + link_raw,
                            query=search_data.title,
                            display_date=release_date,
                            search_date=search_data.search_date or None,
                            cur_id=enc,
                            subsite=subsite or None,
                            score=best_title_score(search_data.title, display_title, search_data.site_info),
                        )
                    )

    # ── Context loader (curID is a numeric scene id) ────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        parts = payload.split('|')
        scene_id = parts[0]
        fallback = parts[1] if len(parts) > 1 else ''
        url = f'{site.base_url.rstrip("/")}/video/watch/{scene_id}'
        details_page_elements = await self._get(url, site, ctx.capture if ctx else None, f'GET {url}')
        if details_page_elements is None:
            return None

        return LoadedScene(
            url=url,
            site=site,
            scene_date=fallback or None,
            capture=ctx.capture if ctx else None,
            sel=details_page_elements,
            html='',
            art_referer=url,
            art_cookie=await self._cookie_header_for(site),
        )

    async def update(self, metadata: SceneDetail, scene: LoadedScene) -> None:
        await super().update(metadata, scene)
        subsite = scene.site.name
        subgroup = scene.site.sub_group
        title = strip_episode_tag(metadata.title)
        await self.enrich_from_data18(
            metadata,
            scene.site,
            scene_id=mapping_slug(title, subsite),
            providers=[p for p in (subsite, subgroup, STUDIO, 'Nubiles NET') if p],
            title=title,
        )

    # ── Field hooks ────────────────────────────────────────────────────────────

    def _summary_of(self, scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        block = (
            details_page_elements.xpath('(//div[contains(@class,"col-12") and contains(@class,"content-pane-column")]/div)[1]').xpath('string(.)').get() or ''
        )
        if block:
            return block.split('Show More')[0].strip()

        paragraphs = [first_attr(p) for p in details_page_elements.xpath('//div[contains(@class,"col-12") and contains(@class,"content-pane-column")]//p')]
        return '\n\n'.join(p for p in paragraphs if p).strip()

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = (details_page_elements.xpath('(//div[contains(@class,"content-pane-title")]//h2)[1]').xpath('string(.)').get() or '').strip()
        parts = [p.strip() for p in raw.split('-')]

        metadata.title = strip_episode_tag((f'{parts[0]} - {" - ".join(parts[1:])}' if len(parts) > 1 else parts[0]) or '')

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.summary = self._summary_of(scene)

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.sub_group if scene.site.sub_group else STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name if scene.site.name != metadata.studio else None

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (details_page_elements.xpath('(//div[contains(@class,"content-pane")]//span[@class="date"])[1]').xpath('string(.)').get() or '').strip()

        metadata.release_date = (iso_date(date) if date else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres: list[str] = []
        for genre_link in details_page_elements.xpath('//div[@class="categories"]/a'):
            genre_name = first_attr(genre_link, 'normalize-space(.)')
            lc = genre_name.lower()
            if genre_name and '.com' not in lc and '.xxx' not in lc:
                genres.append(genre_name)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')
        _, scene_first = scene_image_pref()
        actors: list[ActorResult] = []
        for actor_link in details_page_elements.xpath('//div[contains(@class,"content-pane-performer")]/a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if not actor_name or not href:
                continue

            if scene_first:
                actors.append(await self._fetch_actor(actor_name, href if href.startswith('http') else base + href, scene.site))
            else:
                actors.append(ActorResult(name=actor_name, photo_url=''))

        summary = self._summary_of(scene)
        existing = {a.name.lower() for a in actors}
        for candidate in _SUMMARY_ACTORS:
            if candidate in summary and candidate.lower() not in existing:
                actors.append(ActorResult(name=candidate, gender='male'))
                existing.add(candidate.lower())

        metadata.actors = actors

    async def _fetch_actor(self, actor_name: str, profile_url: str, site: ResolvedSiteInfo) -> ActorResult:
        model_page_elements = await self._get(profile_url, site, None, f'GET {profile_url} (actor)')
        if model_page_elements is None:
            return ActorResult(name=actor_name)

        photo = to_https(first_attr(model_page_elements, '(//div[contains(@class,"model-profile")]//img)[1]/@src'))
        gender = 'female' if model_page_elements.xpath('//p[@class="model-profile-subheading"][contains(.,"Figure")]') else ''
        return ActorResult(name=actor_name, photo_url=photo, gender=gender)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        out: list[str] = []
        poster = first_attr(details_page_elements, '(//video)[1]/@poster')
        if poster:
            out.append(to_https(poster))

        m = _WATCH_ID_RE.search(scene.url)
        scene_id = m.group(1) if m else ''
        gallery_url = self._find_gallery_url(details_page_elements, scene.site.base_url.rstrip('/'), scene_id)
        if gallery_url:
            gallery_page_elements = await self._get(gallery_url, scene.site, None, f'GET {gallery_url} (gallery)')
            if gallery_page_elements is not None:
                imgs = gallery_page_elements.xpath('//figure[contains(@class,"photo-thumb")]//div[@class="img-wrapper"]//picture/img')
                if imgs:
                    for img in imgs:
                        srcset = img.attrib.get('srcset') or ''
                        candidates = [img.attrib.get('src') or '', *(c.strip().split(' ')[0] for c in srcset.split(',') if c.strip())]
                        if best := _best_variant(candidates):
                            out.append(to_https(best))
                else:
                    for srcset in gallery_page_elements.xpath('//div[@class="img-wrapper"]//picture/source/@srcset').getall():
                        first = srcset.split(',')[0].strip().split(' ')[0]
                        if first and not first.startswith('data:'):
                            out.append(to_https(first))

        metadata.art = out

    def _find_gallery_url(self, sel: Any, base: str, scene_id: str) -> str | None:
        for a in sel.xpath('//div[contains(@class,"content-pane-related-links")]/a'):
            if 'Pic' in (a.xpath('string(.)').get() or ''):
                href = first_attr(a, '@href')
                if href:
                    return href if href.startswith('http') else base + href

        poster = (sel.xpath('(//video)[1]/@poster').get() or sel.xpath('(//div[@class="fake-video-player"]/img)[1]/@src').get() or '').strip()
        m = _POSTER_SAMPLE_RE.search(poster)
        if m:
            return f'{base}/galleries/{m.group(1)}/screenshots'

        if scene_id:
            return f'{base}/galleries/{scene_id}/screenshots'

        return None
