from __future__ import annotations

import re

from parsel import Selector

from app.clients.base import Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import build_search_result, iso_date, join_url, load_site_json, pack_cur_id, slugify
from app.utils.helpers.html_helpers import first_attr

_PROFILES: dict[str, dict[str, str]] = load_site_json(__file__, 'hightechvr_profiles')
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
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        scene_url = base + ctx.site_info.search_path.replace('{query}', slugify(ctx.title))
        loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] directScene {scene_url}')
        if not loaded:
            return
        title = (loaded['sel'].xpath('(//h1)[1]').xpath('string(.)').get() or '').strip()
        if not title:
            return
        results.append(
            build_search_result(title=title, scene_url=scene_url, query=ctx.title, search_date=ctx.search_date, score=100, cur_id=pack_cur_id([scene_url]))
        )

    # ── Field hooks ───────────────────────────────────────────────────────────

    def _tagline(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//title)[1]').xpath('string(.)').get() or '').strip()
        return _tagline_from_title(raw) if raw else None

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = (scene.sel.xpath('(//h1)[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        p = _profile(scene.site.name)
        metadata.summary = (scene.sel.xpath(f'({p["summary"]})[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline(scene)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        tagline = self._tagline(scene)
        metadata.collections = [tagline] if tagline else None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        p = _profile(scene.site.name)
        el = scene.sel.xpath(f'({p["release_date"]})[1]')
        raw = (el.xpath(f'@{p["date_attr"]}').get() if p['date_attr'] else el.xpath('string(.)').get()) or ''
        raw = raw.strip()
        metadata.release_date = iso_date(raw) if raw else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        p = _profile(scene.site.name)
        values: list[str | None] = [a.xpath('string(.)').get() or '' for a in scene.sel.xpath(p['genres'])]
        metadata.genres = self.dedup_strings(values) or []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        p = _profile(scene.site.name)
        base = scene.site.base_url.rstrip('/')

        def extract_photo(sel: Selector) -> str:
            return (sel.xpath(f'({p["actor_photo"]})[1]/@src').get() or '').strip()

        refs: list[tuple[str, str]] = []
        for el in scene.sel.xpath(p['actors']):
            name = first_attr(el, 'normalize-space(.)')
            href = first_attr(el, '@href')
            if name:
                refs.append((name, join_url(href, base) if href else ''))
        metadata.actors = await self.resolve_actor_photos(refs, extract_photo)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        p = _profile(scene.site.name)
        is_sexbabes = scene.site.name == 'SexBabesVR'
        images: list[str] = []

        def push(raw: str) -> None:
            if not raw:
                return
            url = _rewrite_sexbabes(raw) if is_sexbabes else raw
            if url.startswith('http') and url not in images:
                images.append(url)

        for el in scene.sel.xpath(p['gallery']):
            push((el.xpath(f'@{p["gallery_attr"]}').get() or '').strip())

        poster_el = scene.sel.xpath(f'({p["poster"]})[1]')
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
