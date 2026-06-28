from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urlparse

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, load_site_json, slugify
from app.utils.helpers.html_helpers import first_attr
from app.utils.logging.logger import logger
from app.utils.searchengines import SearchOptions, web_search, web_search_available

STUDIO = 'BellaPass'

_STUDIO_OVERRIDES: dict[str, str] = load_site_json(__file__, 'bellapass_studios')
_TITLE_SELECTORS: dict[str, str] = load_site_json(__file__, 'bellapass_title_selectors')

_PUNCT_RE = re.compile(r'\s*[^\w\s]+')


def _studio_for(name: str) -> str:
    return _STUDIO_OVERRIDES.get(name, STUDIO)


def _title_selector_for(name: str) -> str:
    return _TITLE_SELECTORS.get(name, 'h3')


def _strip_punct(s: str) -> str:
    return _PUNCT_RE.sub('', s).strip()


def _title_from(sel: Any, primary: str) -> str:
    t = (sel.xpath(f'(//{primary})[1]').xpath('string(.)').get() or '').strip()
    if not t:
        other = 'h3' if primary == 'h1' else 'h1'
        t = (sel.xpath(f'(//{other})[1]').xpath('string(.)').get() or '').strip()
    return t


__testing__ = {'strip_punct': _strip_punct, 'studio_for': _studio_for, 'title_selector_for': _title_selector_for}


class BellaPassClient(Client):
    # ── Search (direct URL + on-site search + web-search augmentation) ───────────

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        candidates: list[str] = [f'{base}/trailers/{slugify(ctx.title)}.html']

        # On-site search.
        enc = ctx.encoded.replace('%20', '-').lower()
        search_url = base + ctx.site_info.search_path.replace('{query}', enc)
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'GET {search_url}')
        if loaded:
            for el in loaded['sel'].xpath('//div[contains(@class,"item-video")]'):
                href = first_attr(el, '(./div)[1]//a[1]/@href')
                time = first_attr(el, '(.//div[contains(@class,"time")])[1]/text()')
                if not href or not re.match(r'^\d[\d:]*$', time):
                    continue
                abs_url = absolute_url(href, ctx.site_info.base_url)
                if abs_url not in candidates:
                    candidates.append(abs_url)

        # Legacy web-search augmentation (gated on an engine being available).
        if web_search_available():
            host = urlparse(ctx.site_info.base_url).netloc
            try:
                found = await web_search(SearchOptions(query=ctx.title, site=host))
            except Exception as err:  # noqa: BLE001 - best-effort
                found = []
                logger.warn(ctx.site_info.name, f'web search failed: {err}')
            for url in found:
                if '/trailers/' in url and url not in candidates:
                    candidates.append(url)

        # Fetch each candidate → SearchResult.
        primary = _title_selector_for(ctx.site_info.name)
        results: list[SearchResult] = []
        for scene_url in candidates:
            page = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'GET {scene_url}')
            if not page:
                continue
            title = _title_from(page['sel'], primary)
            if not title:
                continue
            date_raw = (page['sel'].xpath('(//div[contains(@class,"videoInfo")]//p)[1]').xpath('string(.)').get() or '').strip()
            release = iso_date(date_raw) or ctx.search_date
            results.append(build_search_result(title=title, scene_url=scene_url, query=ctx.title, display_date=release, search_date=ctx.search_date))
        return results

    # ── Field hooks ───────────────────────────────────────────────────────────

    def _title_of(self, scene: LoadedScene) -> str:
        assert scene.sel is not None
        return _title_from(scene.sel, _title_selector_for(scene.site.name))

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        return self._title_of(scene) or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//div[contains(@class,"videoDetails")]//p)[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return _studio_for(scene.site.name)

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        # Only the umbrella keeps a tagline; sub-brands stand alone (legacy).
        return scene.site.name if _studio_for(scene.site.name) == STUDIO else None

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//div[contains(@class,"videoInfo")]//p)[1]').xpath('string(.)').get() or '').strip()
        return iso_date(raw) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres = [
            g
            for g in (first_attr(a, 'normalize-space(.)') for a in scene.sel.xpath('//div[contains(@class,"featuring")]//a[contains(@href,"/categories/")]'))
            if g
        ]
        cast = len(scene.sel.xpath('//div[contains(@class,"featuring")]//a[contains(@href,"/models/")]'))
        if cast == 3:
            genres.append('Threesome')
        elif cast == 4:
            genres.append('Foursome')
        elif cast > 4:
            genres.append('Orgy')
        return genres or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        refs: list[tuple[str, str]] = []
        for el in scene.sel.xpath('//div[contains(@class,"featuring")]//a[contains(@href,"/models/")]'):
            name = _strip_punct(first_attr(el, 'normalize-space(.)'))
            href = first_attr(el, '@href')
            if name:
                refs.append((name, absolute_url(href, scene.site.base_url)))
        actors: list[ActorResult] = []
        for name, actor_url in refs:
            loaded = await self.fetch_and_load(actor_url, None, f'GET {actor_url} (actor)')
            rel = first_attr(loaded['sel'], '(//div[@class="profile-pic"]//img)[1]/@src0_3x') if loaded else ''
            photo = (rel if rel.startswith('http') else base + rel) if rel else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        out: list[str] = []

        def add(rel: str) -> None:
            if not rel:
                return
            abs_url = rel if rel.startswith('http') else base + rel
            if abs_url not in out:
                out.append(abs_url)

        xpaths = (
            '//img[contains(@class,"thumbs")]/@src0_3x',
            '//div[contains(@class,"item-thumb")]//img/@src0_3x',
        )
        for xpath in xpaths:
            for raw in scene.sel.xpath(xpath).getall():
                add(raw)

        set_id = (
            scene.sel.xpath('(//img[contains(@class,"thumbs")])[1]/@id').get()
            or scene.sel.xpath('(//div[contains(@class,"item-thumb")]//img)[1]/@id').get()
            or ''
        ).strip()
        title = self._title_of(scene)
        if set_id and title:
            enc = quote(title, safe='').replace('%20', '+')
            search_page = base + scene.site.search_path.replace('{query}', enc)
            sloaded = await self.fetch_and_load(search_page, None, 'photoset search')
            if sloaded:
                cnt_raw = sloaded['sel'].xpath(f'(//img[@id="{set_id}"])[1]/@cnt').get() or '0'
                try:
                    cnt = int(cnt_raw)
                except ValueError:
                    cnt = 0
                for i in range(cnt):
                    add((sloaded['sel'].xpath(f'(//img[@id="{set_id}"])[1]/@src{i}_3x').get() or '').strip())

            preview = await self.fetch_and_load(scene.url.replace('/trailers/', '/preview/'), None, 'preview page')
            if preview:
                for src in preview['sel'].xpath(f'//img[@id="{set_id}"]/@src0_3x').getall():
                    add(src)
        return out or None
