from __future__ import annotations

import re
from typing import Any

from parsel import Selector

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import build_search_result, iso_date, join_url, load_site_json, pack_cur_id, strip_query
from app.utils.helpers.html_helpers import first_attr, web_search_urls

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


class RadicalCashOtherClient(Client):
    def _profile(self, site_name: str) -> dict[str, Any]:
        return _PROFILES[_profile_key(site_name)]

    def _profile_date(self, raw: str, fmt: str) -> str | None:
        cleaned = _strip_ordinals(raw.split(':')[-1].strip() if ':' in raw else raw)
        if not cleaned:
            return None

        return (iso_date(cleaned, fmt) if fmt else None) or iso_date(cleaned)

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        p = self._profile(search_data.site_info.name)
        base = search_data.site_info.base_url.rstrip('/')
        seen: set[str] = set()

        raw_path = search_data.site_info.search_path.replace('{query}', search_data.title.strip().lower())
        search_url = raw_path if re.match(r'^https?://', raw_path, re.IGNORECASE) else f'{base}{raw_path}'
        search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {search_url}')
        if search_results:
            for search_result in search_results['sel'].xpath(f'//{p["search_results"]}'):
                title = (search_result.xpath(f'(.//{p["search_title"]})[1]').xpath('string(.)').get() or '').strip()
                href = (search_result.xpath(f'(.//{p["search_link"]})[1]/@href').get() or '').strip()
                if not title or not href:
                    continue

                scene_url = join_url(href, base).split('?')[0]
                if scene_url in seen:
                    continue

                seen.add(scene_url)
                raw_date = (search_result.xpath(f'(.//{p["search_date"]})[1]').xpath('string(.)').get() or '').strip()
                date = self._profile_date(raw_date, p['search_date_format']) if raw_date else search_data.search_date

                results.append(
                    build_search_result(
                        title=title,
                        scene_url=scene_url,
                        query=search_data.title,
                        display_date=date,
                        search_date=search_data.search_date,
                        cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
                    )
                )

        for raw in await web_search_urls(search_data.title, search_data.site_info, include=['/view/', '/model/'], exclude=['photoset']):
            url = strip_query(raw).replace('dev.', '')
            if '/model/' in url:
                model_page_elements = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] model crawl {url}')
                if not model_page_elements:
                    continue

                for href in model_page_elements['sel'].xpath(f'//{p["model_crawl_scene_link"]}/@href').getall():
                    href = href.strip()
                    if not href or '/join' in href:
                        continue

                    scene_url = join_url(href, base).split('?')[0]
                    if scene_url in seen:
                        continue

                    seen.add(scene_url)

                    results.append(
                        build_search_result(
                            title=search_data.title,
                            scene_url=scene_url,
                            query=search_data.title,
                            search_date=search_data.search_date,
                            cur_id=pack_cur_id([scene_url]),
                        )
                    )
            elif url not in seen:
                seen.add(url)

                results.append(
                    build_search_result(
                        title=search_data.title, scene_url=url, query=search_data.title, search_date=search_data.search_date, cur_id=pack_cur_id([url])
                    )
                )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        p = self._profile(scene.site.name)

        metadata.title = (details_page_elements.xpath(f'(//{p["title"]})[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        p = self._profile(scene.site.name)
        parts = [first_attr(el) for el in details_page_elements.xpath(f'//{p["summary"]}')]
        parts = [t for t in parts if t]

        metadata.summary = '\n\n'.join(parts) if parts else ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        studio: str = self._profile(scene.site.name)['studio']

        metadata.studio = studio

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        p = self._profile(scene.site.name)
        if p['release_date']:
            date = (details_page_elements.xpath(f'(//{p["release_date"]})[1]').xpath('string(.)').get() or '').strip()
            if date:
                metadata.release_date = iso_date(_strip_ordinals(date), p['date_format']) or iso_date(_strip_ordinals(date))
                return

        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = details_page_elements.xpath('(//meta[@name="keywords"])[1]/@content').get() or ''
        values: list[str | None] = [genre_name.strip() for genre_name in raw.split(',')]

        metadata.genres = self.dedup_strings(values) or []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        p = self._profile(scene.site.name)
        base = scene.site.base_url.rstrip('/')
        actors: list[ActorResult] = []
        seen: set[str] = set()

        if p['actor_mode'] == 'inline':
            for block in details_page_elements.xpath(f'//{p["actors"]}'):
                if p['actor_name_inline']:
                    actor_name = (block.xpath(f'(.//{p["actor_name_inline"]})[1]').xpath('string(.)').get() or '').strip()
                else:
                    actor_name = first_attr(block)

                if not actor_name or actor_name in seen:
                    continue

                seen.add(actor_name)
                photo = (block.xpath(f'(.//{p["actor_photo_inline"]})[1]/@src').get() or '').strip() if p['actor_photo_inline'] else ''
                actors.append(ActorResult(name=actor_name, photo_url=photo))

            metadata.actors = actors or []
            return

        attr = p['actor_photo_page_attr'] or 'src'

        def extract_photo(sel: Selector) -> str:
            return (sel.xpath(f'(//{p["actor_photo_page"]})[1]/@{attr}').get() or '').strip()

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath(f'//{p["actors"]}'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name:
                refs.append((actor_name, join_url(href, base) if (href and p['actor_photo_page']) else ''))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=None) or []

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        director = self._profile(scene.site.name)['director']

        metadata.directors = [ActorResult(name=director)] if director else None

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')
        images = self.image_collector(lambda image: join_url(image, base))
        xpaths = (
            '//div[contains(@class,"photo-wrap")]//a/@href',
            '//div[@id="photo-carousel"]//a/@href',
            '//video/@poster',
        )
        for xpath in xpaths:
            for image_url in details_page_elements.xpath(xpath).getall():
                images['push'](image_url)

        metadata.art = images['list'] or []
