from __future__ import annotations

import re
from typing import Any

from parsel import Selector

from app.clients.aggregators.data18 import mapping_slug
from app.clients.base import ActorResult, Client, LoadedScene, RawCaptureEntry, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.captcha.pow import get_verified_cookies
from app.utils.helpers.helpers import iso_date, load_site_json, pack_cur_id, title_distance_score, to_https
from app.utils.helpers.html_helpers import first_attr
from app.utils.logging.logger import logger

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
_POSTER_SAMPLE_RE = re.compile(r'/videos/([^/]+)/.*sample')
_WATCH_ID_RE = re.compile(r'/video/watch/(\d+)')

_SUMMARY_ACTORS: list[str] = load_site_json(__file__, 'nubiles_summary_actors')


class NubilesClient(Client):
    def __init__(self) -> None:
        super().__init__(_SHARED_HEADERS)

    async def _cookie_header_for(self, base_url: str) -> str:
        verified = await get_verified_cookies(base_url) or {}
        cookies = {'18-plus-modal': 'hidden', **verified}
        return '; '.join(f'{k}={v}' for k, v in cookies.items())

    async def _get(self, url: str, base_url: str, capture: list[RawCaptureEntry] | None, label: str) -> Selector | None:
        try:
            r = await self.http.get(url, headers={'Cookie': await self._cookie_header_for(base_url)})
        except Exception as err:  # noqa: BLE001 - network errors yield no page
            logger.warn('Nubiles', f'{label} failed: {err}')
            return None
        if capture is not None:
            capture.append(RawCaptureEntry(label, 'html', r.text))
        return Selector(text=r.text)

    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')

        scene_id = ctx.scene_id or None
        if scene_id:
            url = f'{base}/video/watch/{scene_id}'
            sel = await self._get(url, ctx.site_info.base_url, ctx.capture, f'GET {url}')
            if sel is not None:
                title = (sel.xpath('(//div[contains(@class,"content-pane-title")]//h2)[1]').xpath('string(.)').get() or '').strip()
                date = iso_date((sel.xpath('(//div[contains(@class,"content-pane-title")]//span[@class="date"])[1]').xpath('string(.)').get() or '').strip())
                if title:
                    results.append(
                        SearchResult(
                            title=title,
                            scene_url=url,
                            cur_id=pack_cur_id([x for x in (scene_id, date) if x]),
                            thumb_url=(sel.xpath('(//video)[1]/@poster').get() or None),
                            release_date=date or ctx.search_date or None,
                            display_date=date,
                            score=100,
                        )
                    )

        if ctx.search_date:
            prefix = (ctx.site_info.sub_group or _DEFAULT_PREFIX).rstrip('/') + '/'
            date_url = f'{base}{prefix}date/{ctx.search_date}/{ctx.search_date}'
            sel = await self._get(date_url, ctx.site_info.base_url, ctx.capture, f'GET {date_url}')
            if sel is not None:
                seen = {r.cur_id for r in results}
                for el in sel.xpath('//div[contains(@class,"content-grid-item")]'):
                    title_a = el.xpath('(.//span[@class="title"]/a)[1]')
                    link_raw = first_attr(title_a, '@href')
                    raw_title = title_a.xpath('string(.)').get() or ''
                    parts = [p.strip() for p in raw_title.split('-')]
                    display_title = f'{parts[0]} - {" - ".join(parts[1:])}' if len(parts) > 1 else parts[0]
                    segs = link_raw.split('/')
                    sid = segs[3] if len(segs) > 3 else ''
                    if not sid:
                        continue
                    release = iso_date((el.xpath('(.//span[@class="date"])[1]').xpath('string(.)').get() or '').strip())
                    enc = pack_cur_id([x for x in (sid, release) if x])
                    if enc in seen:
                        continue
                    seen.add(enc)
                    results.append(
                        SearchResult(
                            title=display_title,
                            scene_url=link_raw if link_raw.startswith('http') else base + link_raw,
                            cur_id=enc,
                            release_date=release or ctx.search_date or None,
                            display_date=release,
                            score=title_distance_score(ctx.title, parts[0]),
                        )
                    )

    # ── Context loader (curID is a numeric scene id) ────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        parts = payload.split('|')
        scene_id = parts[0]
        fallback = parts[1] if len(parts) > 1 else ''
        url = f'{site.base_url.rstrip("/")}/video/watch/{scene_id}'
        sel = await self._get(url, site.base_url, ctx.capture if ctx else None, f'GET {url}')
        if sel is None:
            return None
        return LoadedScene(url=url, site=site, scene_date=fallback or None, capture=ctx.capture if ctx else None, sel=sel, html='')

    async def update(self, metadata: SceneDetail, scene: LoadedScene) -> None:
        await super().update(metadata, scene)
        subsite = scene.site.name
        await self.enrich_from_data18(metadata, scene.site, scene_id=mapping_slug(metadata.title, subsite), providers=[subsite, STUDIO])

    # ── Field hooks ────────────────────────────────────────────────────────────

    def _summary_of(self, scene: LoadedScene) -> str:
        sel = scene.require_sel()
        block = sel.xpath('(//div[contains(@class,"col-12") and contains(@class,"content-pane-column")]/div)[1]').xpath('string(.)').get() or ''
        if block:
            return block.split('Show More')[0].strip()
        paragraphs = [first_attr(p) for p in sel.xpath('//div[contains(@class,"col-12") and contains(@class,"content-pane-column")]//p')]
        return '\n\n'.join(p for p in paragraphs if p).strip()

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        raw = (sel.xpath('(//div[contains(@class,"content-pane-title")]//h2)[1]').xpath('string(.)').get() or '').strip()
        parts = [p.strip() for p in raw.split('-')]
        metadata.title = (f'{parts[0]} - {" - ".join(parts[1:])}' if len(parts) > 1 else parts[0]) or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.summary = self._summary_of(scene)

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name if scene.site.name != STUDIO else None

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        raw = (sel.xpath('(//div[contains(@class,"content-pane")]//span[@class="date"])[1]').xpath('string(.)').get() or '').strip()
        metadata.release_date = (iso_date(raw) if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        genres: list[str] = []
        for a in sel.xpath('//div[@class="categories"]/a'):
            g = first_attr(a, 'normalize-space(.)')
            lc = g.lower()
            if g and '.com' not in lc and '.xxx' not in lc:
                genres.append(g)
        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        base = scene.site.base_url.rstrip('/')
        actors: list[ActorResult] = []
        for el in sel.xpath('//div[contains(@class,"content-pane-performer")]/a'):
            name = first_attr(el, 'normalize-space(.)')
            href = first_attr(el, '@href')
            if not name or not href:
                continue
            actors.append(await self._fetch_actor(name, href if href.startswith('http') else base + href, scene.site.base_url))

        summary = self._summary_of(scene)
        existing = {a.name.lower() for a in actors}
        for candidate in _SUMMARY_ACTORS:
            if candidate in summary and candidate.lower() not in existing:
                actors.append(ActorResult(name=candidate, gender='male'))
                existing.add(candidate.lower())
        metadata.actors = actors

    async def _fetch_actor(self, name: str, profile_url: str, base_url: str) -> ActorResult:
        sel = await self._get(profile_url, base_url, None, f'GET {profile_url} (actor)')
        if sel is None:
            return ActorResult(name=name)
        photo = to_https(first_attr(sel, '(//div[contains(@class,"model-profile")]//img)[1]/@src'))
        gender = 'female' if sel.xpath('//p[@class="model-profile-subheading"][contains(.,"Figure")]') else ''
        return ActorResult(name=name, photo_url=photo, gender=gender)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        out: list[str] = []
        poster = first_attr(sel, '(//video)[1]/@poster')
        if poster:
            out.append(to_https(poster))

        m = _WATCH_ID_RE.search(scene.url)
        scene_id = m.group(1) if m else ''
        gallery_url = self._find_gallery_url(sel, scene.site.base_url.rstrip('/'), scene_id)
        if gallery_url:
            gsel = await self._get(gallery_url, scene.site.base_url, None, f'GET {gallery_url} (gallery)')
            if gsel is not None:
                for srcset in gsel.xpath('//div[@class="img-wrapper"]//picture/source/@srcset').getall():
                    first = srcset.split(',')[0].strip().split(' ')[0]
                    if first:
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
