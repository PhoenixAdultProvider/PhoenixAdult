from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote, urlparse

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, date_distance_score, iso_date, strip_query, title_distance_score
from app.utils.helpers.html_helpers import first_attr
from app.utils.logging.logger import logger
from app.utils.searchengines import SearchOptions, web_search, web_search_available

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
    # ── Search (web-search augmentation + on-page grid) ─────────────────────────

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        results: list[SearchResult] = []
        seen: set[str] = set()

        if web_search_available():
            host = urlparse(ctx.site_info.base_url).netloc
            try:
                found = await web_search(SearchOptions(query=ctx.title, site=host))
            except Exception as err:  # noqa: BLE001 - search engines are best-effort
                found = []
                logger.warn(ctx.site_info.name, f'web search failed: {err}')
            for raw in found:
                url = strip_query(raw)
                if 'com/video/' not in url or 'index.php/' in url or url in seen:
                    continue
                seen.add(url)
                loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'GET {url}')
                if not loaded:
                    continue
                ld = _find_video_ld(loaded['sel'])
                if not ld:
                    continue
                title = _strip_html(ld.get('name'))
                if not title:
                    continue
                release = iso_date(ld['datePublished']) if ld.get('datePublished') else None
                results.append(build_search_result(title=_bangify(title), scene_url=url, query=ctx.title, display_date=release, search_date=ctx.search_date))

        enc = quote(ctx.title, safe='').replace('%20', '+')
        search_url = base + ctx.site_info.search_path.replace('{query}', enc)
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'GET {search_url}')
        if loaded:
            for el in loaded['sel'].xpath('//div[contains(@class,"movie-preview") or contains(@class,"video_container")]'):
                href = first_attr(el, '(.//a[contains(@class,"group")])[1]/@href')
                if not href:
                    continue
                if 'dvd' in href:
                    title = (el.xpath('(.//a//div)[1]').xpath('string(.)').get() or '').strip()
                else:
                    title = (el.xpath('(.//a//span)[1]').xpath('string(.)').get() or '').strip()
                if not title:
                    continue
                scene_url = absolute_url(href, ctx.site_info.base_url)
                if scene_url in seen:
                    continue
                seen.add(scene_url)
                date_part = (el.xpath('(.//span[@class="hidden xs:inline-block truncate"])[1]').xpath('string(.)').get() or '').split('•')[-1].strip()
                release = iso_date(date_part)
                # Score uses the pre-bangify title (the bangified value would skew it).
                score = date_distance_score(ctx.search_date, release) if ctx.search_date and release else title_distance_score(ctx.title, title)
                results.append(
                    build_search_result(
                        title=_bangify(title), scene_url=scene_url, query=ctx.title, display_date=release, search_date=ctx.search_date, score=score
                    )
                )
        return results

    # ── Field hooks ───────────────────────────────────────────────────────────

    def _studio_of(self, scene: LoadedScene) -> str:
        assert scene.sel is not None
        ld = _find_video_ld(scene.sel)
        raw = ''
        if ld:
            company = ld.get('productionCompany')
            if isinstance(company, dict):
                raw = (company.get('name') or '').strip()
        return _bangify(raw or STUDIO)

    def _tagline_of(self, scene: LoadedScene) -> str:
        assert scene.sel is not None
        for el in scene.sel.xpath('//p[contains(.,"eries:")]//a'):
            href = el.xpath('@href').get() or ''
            if 'originals' in href or 'videos' in href:
                return _bangify(first_attr(el, 'normalize-space(.)'))
        return ''

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        ld = _find_video_ld(scene.sel)
        raw = _strip_html(ld.get('name')) if ld and ld.get('name') else (scene.sel.xpath('(//h1)[1]').xpath('string(.)').get() or '').strip()
        return _bangify(raw) or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        ld = _find_video_ld(scene.sel)
        if ld and ld.get('description'):
            return _strip_html(ld['description']) or None
        desc = (scene.sel.xpath('(//div[contains(@class,"description")])[1]').xpath('string(.)').get() or '').strip()
        if desc:
            return desc
        meta = first_attr(scene.sel, '(//meta[@name="description"])[1]/@content')
        og = first_attr(scene.sel, '(//meta[@property="og:description"])[1]/@content')
        return meta or og or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return self._studio_of(scene)

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return self._tagline_of(scene) or None

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        tagline = self._tagline_of(scene)
        collections = [tagline] if tagline else [self._studio_of(scene)]
        dvd_title = (scene.sel.xpath('(//p[contains(.,"Movie")]//a[contains(@href,"dvd")])[1]').xpath('string(.)').get() or '').strip()
        if dvd_title:
            collections.append(_bangify(dvd_title))
        return collections

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        ld = _find_video_ld(scene.sel)
        iso = iso_date(ld['datePublished']) if ld and ld.get('datePublished') else None
        return iso or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres = [
            g
            for g in (first_attr(a, 'normalize-space(.)') for a in scene.sel.xpath('//div[contains(@class,"actions")]//a | //a[contains(@class,"genres")]'))
            if g
        ]
        return genres or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        scene_els = scene.sel.xpath('//div[contains(@class,"name")]/a[contains(@href,"pornstar") and not(@aria-label)]')
        if scene_els:
            actors: list[ActorResult] = []
            for el in scene_els:
                name = (el.xpath('(.//span)[1]').xpath('normalize-space(.)').get() or '').strip() or first_attr(el, 'normalize-space(.)')
                img = first_attr(el, '(ancestor::div[1]/parent::*//img)[1]/@src')
                photo = img if img and 'placeholder' not in img else ''
                if name:
                    actors.append(ActorResult(name=name, photo_url=photo))
            return actors or None

        dvd_actors: list[ActorResult] = []
        for el in scene.sel.xpath('//div[contains(@class,"clear-both")]//a[contains(@href,"pornstar")]'):
            name = first_attr(el, 'normalize-space(.)')
            href = first_attr(el, '@href')
            if not name or not href:
                continue
            loaded = await self.fetch_and_load(absolute_url(href, scene.site.base_url), None, 'actor')
            photo = ''
            if loaded:
                for s in loaded['sel'].xpath('//script[@type="application/ld+json"]'):
                    try:
                        blob = json.loads(s.xpath('string(.)').get() or '')
                    except (ValueError, TypeError):
                        continue
                    if isinstance(blob, dict) and blob.get('@type') == 'Person' and isinstance(blob.get('image'), str):
                        photo = blob['image'].strip()
                        break
            dvd_actors.append(ActorResult(name=name, photo_url=photo))
        return dvd_actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        ld = _find_video_ld(scene.sel)
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

        # XPath fallback (full URLs kept, per the image-URL policy).
        if not out:
            og = first_attr(scene.sel, '(//meta[@property="og:image"])[1]/@content')
            if og:
                out.append(og)
            for poster in scene.sel.xpath('//video/@poster').getall():
                if poster:
                    out.append(poster)
            for el in scene.sel.xpath('//img[contains(@class,"object-cover") and contains(@class,"aspect-cover")]'):
                src = first_attr(el, '@src')
                if src:
                    out.append(src)
                srcset = el.xpath('@srcset').get() or ''
                for part in srcset.split(','):
                    token = part.strip().split(' ')[0].strip()
                    if token:
                        out.append(token)

        deduped: list[str] = []
        for u in out:
            if u and u not in deduped:
                deduped.append(u)
        return deduped or None
