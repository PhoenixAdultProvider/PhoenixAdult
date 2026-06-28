from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date
from app.utils.helpers.html_helpers import first_attr
from app.utils.logging.logger import logger

STUDIO = 'Abby Winters'
_SCENE_URL_BLOCKLIST = ['/nude_girl/', '/shoots/', '/fetish/', '/updates/']
_LOCALE_PREFIXES = ['/cn/', '/de/', '/jp/', '/ja/', '/en/']


def _is_usable_scene_url(url: str) -> bool:
    return not any(bad in url for bad in _SCENE_URL_BLOCKLIST)


def _strip_locale(url: str) -> str:
    out = url
    for p in _LOCALE_PREFIXES:
        out = out.replace(p, '/')
    return out


def _parse_page_title(sel: Any) -> str:
    raw = sel.xpath('(//title)[1]/text()').get() or ''
    return raw.split(':')[-1].split('|')[0].strip()


__testing__ = {
    'is_usable_scene_url': _is_usable_scene_url,
    'strip_locale': _strip_locale,
    'SCENE_URL_BLOCKLIST': _SCENE_URL_BLOCKLIST,
    'LOCALE_PREFIXES': _LOCALE_PREFIXES,
}


class AbbyWintersClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        encoded = ctx.encoded.replace('%20', '+')
        search_url = base + ctx.site_info.search_path.replace('{query}', encoded)

        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'GET {search_url}')
        if not loaded:
            return []
        total_raw = first_attr(loaded['sel'], '(//span[@id="browse-total-count"])[1]/text()')
        if total_raw.isdigit() and int(total_raw) == 0:
            return []

        model_hrefs: list[str] = []
        for href in loaded['sel'].xpath('//div[@id="browse-grid"]//main//article//a[@class]/@href').getall():
            if href:
                abs_url = absolute_url(href, ctx.site_info.base_url)
                if abs_url not in model_hrefs:
                    model_hrefs.append(abs_url)

        scene_urls: list[str] = []
        for model_url in model_hrefs:
            page = await self.fetch_and_load(model_url, FetchCtx(capture=ctx.capture), f'GET {model_url}')
            if not page:
                continue
            for href in page['sel'].xpath('//div[@id="subject-shoots"]//h2//a/@href').getall():
                if not href:
                    continue
                normalized = _strip_locale(absolute_url(href, ctx.site_info.base_url))
                if _is_usable_scene_url(normalized) and normalized not in scene_urls:
                    scene_urls.append(normalized)

        name = ctx.site_info.name
        logger.debug(name, f'AbbyWinters: {len(model_hrefs)} model page(s) -> {len(scene_urls)} scene URL(s)')

        results: list[SearchResult] = []
        actor_cache: dict[str, Any] = {}
        for scene_url in scene_urls:
            page = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'GET {scene_url}')
            if not page:
                continue
            sel = page['sel']
            title = _parse_page_title(sel)
            if not title:
                continue
            sub_site = (sel.xpath('(//div[@id="shoot-featured-image"]//h4)[1]').xpath('string(.)').get() or '').strip()
            display_date = await self._lookup_date(sel, ctx, title, sub_site, actor_cache)
            logger.debug(name, f'AbbyWinters: scene "{title}" [{sub_site}] -> date {display_date or "NOT FOUND"}')
            results.append(build_search_result(title=title, scene_url=scene_url, query=ctx.title, display_date=display_date, search_date=ctx.search_date))
        return results

    async def _lookup_date(self, sel: Any, ctx: SearchContext, title: str, sub_site: str, cache: dict[str, Any]) -> str | None:
        name = ctx.site_info.name
        model_link = sel.xpath('(//tr[contains(.,"Scene")]//a)[1]/@href').get()
        if not model_link:
            logger.debug(name, f'AbbyWinters._lookup_date: no model link for "{title}"')
            return None
        model_abs = absolute_url(model_link, ctx.site_info.base_url)
        model_sel = cache.get(model_abs)
        if model_sel is None:
            page = await self.fetch_and_load(model_abs, FetchCtx(capture=ctx.capture), f'GET {model_abs} (model)')
            if not page:
                logger.debug(name, f'AbbyWinters._lookup_date: model page fetch failed {model_abs}')
                return None
            model_sel = page['sel']
            cache[model_abs] = model_sel
        cards = model_sel.xpath('//article[contains(@class,"card") and contains(@class,"card-shoot")]')
        logger.debug(name, f'AbbyWinters._lookup_date: matching "{title}"/"{sub_site}" against {len(cards)} card(s) on {model_abs}')
        for card in cards:
            # Full descendant text (string(.)) — the title sits inside an <a>, so a
            # bare /text() node-test misses it (the date-resolution bug this fixes).
            h2 = (card.xpath('(.//h2)[1]').xpath('string(.)').get() or '').strip()
            h3 = ''.join(card.xpath('(.//h3)[1]//text()[not(ancestor::span)]').getall()).strip()
            if h2.lower() == title.lower() and h3.lower() == sub_site.lower():
                raw_date = (card.xpath('(.//span)[1]').xpath('string(.)').get() or '').strip()
                logger.debug(name, f'AbbyWinters._lookup_date: matched card -> raw date "{raw_date}"')
                return iso_date(raw_date)
        logger.debug(name, f'AbbyWinters._lookup_date: no card matched "{title}"/"{sub_site}"')
        return None

    # ── Field hooks ───────────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return _parse_page_title(scene.sel) or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//aside//div[contains(@class,"description")])[1]').xpath('string(.)').get() or '').replace('\n', '').strip()
        return raw or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    def _subsite(self, scene: LoadedScene) -> str:
        assert scene.sel is not None
        return (scene.sel.xpath('(//div[@id="shoot-featured-image"]//h4)[1]').xpath('string(.)').get() or '').strip()

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return self._subsite(scene) or None

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        tagline = self._subsite(scene)
        return [tagline] if tagline else [STUDIO]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        return scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres = [
            g for g in (first_attr(a, 'normalize-space(.)') for a in scene.sel.xpath('//aside//div[contains(@class,"description")]//a')) if g
        ]
        return genres or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        refs: list[tuple[str, str]] = []
        seen: set[str] = set()
        for el in scene.sel.xpath('//tr[contains(.,"Scene")]//a'):
            name = first_attr(el, 'normalize-space(.)')
            href = first_attr(el, '@href')
            if name and href and name not in seen:
                seen.add(name)
                refs.append((name, absolute_url(href, base)))
        actors: list[ActorResult] = []
        for name, href in refs:
            page = await self.fetch_and_load(href, None, f'GET {href} (actor)')
            photo = first_attr(page['sel'], '(//img[contains(@class,"img-responsive")]/@src)[1]') if page else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        coll = self.image_collector()
        xpaths = (
            '//div[contains(@class,"tile-image")]//img/@src',
            '//div[contains(@class,"video")]/@data-poster',
        )
        for xpath in xpaths:
            for raw in scene.sel.xpath(xpath).getall():
                coll['push'](raw)
        images: list[str] = coll['list']
        return images or None
