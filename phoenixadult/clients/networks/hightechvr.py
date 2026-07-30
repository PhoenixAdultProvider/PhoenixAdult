from __future__ import annotations

import re

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import build_search_result, iso_date, join_url, load_data, pack_cur_id, slugify
from phoenixadult.utils.helpers.html_helpers import first_attr

_PROFILES: dict[str, dict[str, str]] = load_data(__file__, 'hightechvr_profiles')
_SEXBABES_RE = re.compile(r'videos_screenshots/(.+?)/\d+x\d+/')
_STYLE_URL_RE = re.compile(r'url\(\s*[\'"]?([^\'")]+)[\'"]?\s*\)')


def _profile(site_name: str) -> dict[str, str]:
    return _PROFILES.get(site_name, _PROFILES['RealJamVR'])


def _rewrite_sexbabes(url: str) -> str:
    return _SEXBABES_RE.sub(r'videos_sources/\1/screenshots/', url)


def _tagline_from_title(raw: str) -> str:
    t = raw.strip()
    if '|' in t:
        return t.split('|')[1].strip()

    if '-' in t:
        return t.split('-')[0].strip()

    return t


class HighTechVRClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        scene_url = base + search_data.site_info.search_path.replace('{query}', slugify(search_data.title))
        direct_page_elements = await self.fetch_and_load(
            scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] directScene {scene_url}'
        )
        if not direct_page_elements:
            return

        title = (direct_page_elements['sel'].xpath('(//h1)[1]').xpath('string(.)').get() or '').strip()
        if not title:
            return

        results.append(
            build_search_result(
                site=search_data.site_info,
                title=title,
                scene_url=scene_url,
                query=search_data.title,
                search_date=search_data.search_date,
                score=100,
                cur_id=pack_cur_id([scene_url]),
            )
        )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _tagline(self, scene: LoadedScene) -> str | None:
        details_page_elements = scene.require_sel()

        raw = (details_page_elements.xpath('(//title)[1]').xpath('string(.)').get() or '').strip()
        return _tagline_from_title(raw) if raw else None

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = (details_page_elements.xpath('(//h1)[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        p = _profile(scene.site.name)

        metadata.summary = (details_page_elements.xpath(f'({p["summary"]})[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline(scene) or ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        tagline = self._tagline(scene)

        metadata.collections = [tagline] if tagline else None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        p = _profile(scene.site.name)
        row = details_page_elements.xpath(f'({p["release_date"]})[1]')
        date = (row.xpath(f'@{p["date_attr"]}').get() if p['date_attr'] else row.xpath('string(.)').get()) or ''
        date = date.strip()

        metadata.release_date = iso_date(date) if date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        p = _profile(scene.site.name)
        values: list[str | None] = [genre_link.xpath('string(.)').get() or '' for genre_link in details_page_elements.xpath(p['genres'])]

        metadata.genres = self.dedup_strings(values) or []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        p = _profile(scene.site.name)
        base = scene.site.base_url.rstrip('/')

        def extract_photo(sel: Selector) -> str:
            return (sel.xpath(f'({p["actor_photo"]})[1]/@src').get() or '').strip()

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath(p['actors']):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name:
                refs.append((actor_name, join_url(href, base) if href else ''))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        p = _profile(scene.site.name)
        is_sexbabes = scene.site.name == 'SexBabesVR'
        images: list[str] = []

        def push(raw: str) -> None:
            if not raw:
                return

            url = _rewrite_sexbabes(raw) if is_sexbabes else raw
            if url.startswith('http') and url not in images:
                images.append(url)

        for row in details_page_elements.xpath(p['gallery']):
            push((row.xpath(f'@{p["gallery_attr"]}').get() or '').strip())

        poster_el = details_page_elements.xpath(f'({p["poster"]})[1]')
        if poster_el:
            poster_attr = first_attr(poster_el, '@poster')
            if poster_attr:
                push(poster_attr)
            else:
                style = poster_el.xpath('@style').get() or ''
                m = _STYLE_URL_RE.search(style)
                if m:
                    push(m.group(1))

        metadata.art = images or []
