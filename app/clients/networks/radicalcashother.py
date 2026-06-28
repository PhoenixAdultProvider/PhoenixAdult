from __future__ import annotations

import re
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import build_search_result, iso_date, load_site_json, pack_cur_id
from app.utils.helpers.html_helpers import web_search_urls

_ORDINAL_RE = re.compile(r'(\d)(st|nd|rd|th)', re.IGNORECASE)
_PROFILES: dict[str, dict[str, Any]] = load_site_json(__file__, 'radicalcashother_profiles')


def _strip_ordinals(s: str) -> str:
    return _ORDINAL_RE.sub(r'\1', s).strip()


def _profile_key(site_name: str) -> str:
    if site_name == 'PurgatoryX':
        return 'purgatoryx'
    if site_name == 'Gonzo Living':
        return 'gonzoliving'
    if site_name in ('Teen Gonzo', 'Milf Gonzo'):
        return 'gonzo'
    if site_name == 'ToughLoveX':
        return 'toughlovex'
    return 'hitzefrei'


def _abs(href: str, base: str) -> str:
    if href.startswith('http'):
        return href
    return base + (href if href.startswith('/') else f'/{href}')


class RadicalCashOtherClient(Client):
    def _profile(self, site_name: str) -> dict[str, Any]:
        return _PROFILES[_profile_key(site_name)]

    def _profile_date(self, raw: str, fmt: str) -> str | None:
        cleaned = _strip_ordinals(raw.split(':')[-1].strip() if ':' in raw else raw)
        if not cleaned:
            return None
        return (iso_date(cleaned, fmt) if fmt else None) or iso_date(cleaned)

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        p = self._profile(ctx.site_info.name)
        base = ctx.site_info.base_url.rstrip('/')
        results: list[SearchResult] = []
        seen: set[str] = set()

        raw_path = ctx.site_info.search_path.replace('{query}', ctx.title.strip().lower())
        search_url = raw_path if re.match(r'^https?://', raw_path, re.IGNORECASE) else f'{base}{raw_path}'
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {search_url}')
        if loaded:
            for card in loaded['sel'].xpath(f'//{p["search_results"]}'):
                title = (card.xpath(f'(.//{p["search_title"]})[1]').xpath('string(.)').get() or '').strip()
                href = (card.xpath(f'(.//{p["search_link"]})[1]/@href').get() or '').strip()
                if not title or not href:
                    continue
                scene_url = _abs(href, base).split('?')[0]
                if scene_url in seen:
                    continue
                seen.add(scene_url)
                raw_date = (card.xpath(f'(.//{p["search_date"]})[1]').xpath('string(.)').get() or '').strip()
                date = self._profile_date(raw_date, p['search_date_format']) if raw_date else ctx.search_date
                results.append(
                    build_search_result(
                        title=title,
                        scene_url=scene_url,
                        query=ctx.title,
                        display_date=date,
                        search_date=ctx.search_date,
                        cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
                    )
                )

        for raw in await web_search_urls(ctx.title, ctx.site_info, include=['/view/', '/model/'], exclude=['photoset']):
            url = raw.split('?')[0].replace('dev.', '')
            if '/model/' in url:
                actor_page = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] model crawl {url}')
                if not actor_page:
                    continue
                for href in actor_page['sel'].xpath(f'//{p["model_crawl_scene_link"]}/@href').getall():
                    href = href.strip()
                    if not href or '/join' in href:
                        continue
                    scene_url = _abs(href, base).split('?')[0]
                    if scene_url in seen:
                        continue
                    seen.add(scene_url)
                    results.append(
                        build_search_result(title=ctx.title, scene_url=scene_url, query=ctx.title, search_date=ctx.search_date, cur_id=pack_cur_id([scene_url]))
                    )
            elif url not in seen:
                seen.add(url)
                results.append(build_search_result(title=ctx.title, scene_url=url, query=ctx.title, search_date=ctx.search_date, cur_id=pack_cur_id([url])))
        return results

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        p = self._profile(scene.site.name)
        return (scene.sel.xpath(f'(//{p["title"]})[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        p = self._profile(scene.site.name)
        parts = [(el.xpath('string(.)').get() or '').strip() for el in scene.sel.xpath(f'//{p["summary"]}')]
        parts = [t for t in parts if t]
        return '\n\n'.join(parts) if parts else None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        studio: str = self._profile(scene.site.name)['studio']
        return studio

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        p = self._profile(scene.site.name)
        if p['release_date']:
            raw = (scene.sel.xpath(f'(//{p["release_date"]})[1]').xpath('string(.)').get() or '').strip()
            if raw:
                return iso_date(_strip_ordinals(raw), p['date_format']) or iso_date(_strip_ordinals(raw))
        return (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_directors(self, scene: LoadedScene) -> list[ActorResult] | None:
        director = self._profile(scene.site.name)['director']
        return [ActorResult(name=director)] if director else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        raw = scene.sel.xpath('(//meta[@name="keywords"])[1]/@content').get() or ''
        values: list[str | None] = [g.strip() for g in raw.split(',')]
        return self.dedup_strings(values) or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        p = self._profile(scene.site.name)
        base = scene.site.base_url.rstrip('/')
        actors: list[ActorResult] = []
        seen: set[str] = set()

        if p['actor_mode'] == 'inline':
            for block in scene.sel.xpath(f'//{p["actors"]}'):
                if p['actor_name_inline']:
                    name = (block.xpath(f'(.//{p["actor_name_inline"]})[1]').xpath('string(.)').get() or '').strip()
                else:
                    name = (block.xpath('string(.)').get() or '').strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                photo = (block.xpath(f'(.//{p["actor_photo_inline"]})[1]/@src').get() or '').strip() if p['actor_photo_inline'] else ''
                actors.append(ActorResult(name=name, photo_url=photo))
            return actors or None

        refs: list[tuple[str, str]] = []
        for el in scene.sel.xpath(f'//{p["actors"]}'):
            name = (el.xpath('normalize-space(.)').get() or '').strip()
            href = (el.xpath('@href').get() or '').strip()
            if name:
                refs.append((name, href))
        attr = p['actor_photo_page_attr'] or 'src'
        for name, href in refs:
            if name in seen:
                continue
            seen.add(name)
            photo = ''
            if href and p['actor_photo_page']:
                page = await self.fetch_and_load(_abs(href, base), None, f'[{scene.site.name}] actor {name}')
                if page:
                    photo = (page['sel'].xpath(f'(//{p["actor_photo_page"]})[1]/@{attr}').get() or '').strip()
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        coll = self.image_collector(lambda raw: raw if raw.startswith('http') else f'{base}{raw if raw.startswith("/") else "/" + raw}')
        xpaths = (
            '//div[contains(@class,"photo-wrap")]//a/@href',
            '//div[@id="photo-carousel"]//a/@href',
            '//video/@poster',
        )
        for xpath in xpaths:
            for raw in scene.sel.xpath(xpath).getall():
                coll['push'](raw)
        images: list[str] = coll['list']
        return images or None
