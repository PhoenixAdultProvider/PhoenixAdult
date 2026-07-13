from __future__ import annotations

import re
from urllib.parse import quote

from parsel import Selector

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text

_LEADING_ID_RE = re.compile(r'^(\d+)\s*(.*)$')
_GENRES_LIST_FIRST_A = '//div[contains(@class,"genres-list")]//a'


class AnalVidsClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        m = _LEADING_ID_RE.match(ctx.title.strip())
        source_id = m.group(1) if m else None
        text = (m.group(2).strip() if m else ctx.title.strip()) or ctx.title.strip()

        data = await self.fetch_json(
            f'{base}/api/autocomplete/search?q={quote(text)}',
            FetchCtx(capture=ctx.capture),
            label=f'[{ctx.site_info.name}] AnalVids search "{text}"',
        )

        for term in (data or {}).get('terms', []):
            if term.get('type') != 'scene' or not term.get('url') or not term.get('name'):
                continue
            url = term['url']
            scene_url = absolute_url(url, ctx.site_info.base_url)
            direct_hit = source_id is not None and str(term.get('source_id', '')) == source_id
            results.append(
                build_search_result(
                    title=term['name'].strip(),
                    scene_url=scene_url,
                    query=text,
                    search_date=ctx.search_date,
                    score=100 if direct_hit else None,
                    cur_id=pack_cur_id([scene_url]),
                )
            )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//h1[contains(@class,"watch__title")]')
        metadata.title = raw.split('featuring')[0].strip()

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = first_text(scene.sel, '//div[contains(@class,"text-mob-more")]')

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'AnalVids'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.tagline = first_text(scene.sel, _GENRES_LIST_FIRST_A) or None

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        tagline = first_text(scene.sel, _GENRES_LIST_FIRST_A)
        metadata.collections = [tagline] if tagline else None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//i[contains(@class,"bi-calendar3")]')
        metadata.release_date = iso_date(raw) or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        values: list[str | None] = [
            a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//div[contains(@class,"genres-list")]//a[contains(@href,"/genre/")]')
        ]
        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None

        def extract_photo(sel: Selector) -> str:
            return first_attr(sel, '(//div[contains(@class,"model")]//img/@src)[1]')

        refs: list[tuple[str, str]] = []
        for el in scene.sel.xpath('//a[contains(@href,"/model/")]'):
            href = first_attr(el, '@href')
            name = first_attr(el, 'normalize-space(.)')
            if not name or not href or 'forum' in href:
                continue
            refs.append((name, absolute_url(href, scene.site.base_url)))
        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture)

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        directors: list[ActorResult] = []
        seen: set[str] = set()

        def add(name: str) -> None:
            n = name.strip()
            if n and n not in seen:
                seen.add(n)
                directors.append(ActorResult(name=n))

        tagline = first_text(scene.sel, _GENRES_LIST_FIRST_A)
        if tagline in ('Giorgio Grandi', "Giorgio's Lab"):
            add('Giorgio Grandi')
        for el in scene.sel.xpath('//p[contains(@class,"director")]//a'):
            add(el.xpath('normalize-space(.)').get() or '')
        metadata.directors = directors or None

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        poster = first_attr(scene.sel, '(//div[contains(@class,"watch__video")]//video/@data-poster)[1]')
        metadata.raw_image_urls = [poster] if poster else []
