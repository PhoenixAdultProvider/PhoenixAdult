from __future__ import annotations

import re
from urllib.parse import urlsplit

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import build_search_result, iso_date, load_site_json, pack_cur_id, sceneid_distance_score
from app.utils.helpers.html_helpers import first_attr, meta_content
from app.utils.helpers.javbus_images import push_javbus_images
from app.utils.logging.logger import logger
from app.utils.processors.title_case import title_case
from app.utils.searchengines import SearchOptions, web_search

_TABLES = load_site_json(__file__, 'javlibrary_tables')
_ACTORS: dict[str, list[str]] = _TABLES['actors']
_CROSS_SITE: dict[str, str] = _TABLES['crossSite']
_IGNORE_LIST: list[str] = _TABLES['ignoreList']


class JavLibraryClient(Client):
    async def _web_search_vjav(self, query: str, base_url: str) -> list[str]:
        host = urlsplit(base_url).hostname or ''
        found = await web_search(SearchOptions(query=query, site=host, num=10))
        out: list[str] = []
        for url in found:
            if '?v=jav' not in url or 'videoreviews' in url:
                continue
            normalized = url.replace('/ja/', '/en/').replace('/tw/', '/en/').replace('/cn/', '/en/')
            if not normalized.lower().startswith('http'):
                normalized = f'http://{normalized}'
            if normalized not in out:
                out.append(normalized)
        return out

    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        tokens = ctx.title.strip().split()
        if tokens:
            tokens[0] = re.sub(r'^(13dsvr|3dsvr)', 'dsvr', tokens[0], flags=re.IGNORECASE)
        search_javid = f'{tokens[0]}-{tokens[1]}' if len(tokens) > 1 and re.fullmatch(r'\d+', tokens[1]) else None
        encoded = search_javid or ctx.encoded

        seen: set[str] = set()

        def add(scene_url: str, jav_id: str, title: str, score: float | None = None) -> None:
            if scene_url in seen:
                return
            seen.add(scene_url)
            results.append(
                build_search_result(
                    title=f'[{jav_id}] {title}',
                    scene_url=scene_url,
                    query=search_javid or ctx.title,
                    search_date=ctx.search_date,
                    score=score,
                    cur_id=pack_cur_id([p for p in (scene_url, ctx.search_date) if p]),
                )
            )

        search_url = f'{base}{ctx.site_info.search_path.replace("{query}", encoded)}'
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {search_url}')
        if loaded:
            cards = loaded['sel'].xpath('//div[contains(@class,"video")]')
            if cards:
                for card in cards:
                    title = first_attr(card, '(.//a/@title)[1]')
                    href = first_attr(card, '(.//a/@href)[1]')
                    if not title or not href:
                        continue
                    jav_id = title.split(' ')[0]
                    scene_url = f'{base}/en{href.split(".")[-1]}'
                    add(scene_url, jav_id, title, sceneid_distance_score(search_javid.lower(), jav_id.lower()) if search_javid else None)
            else:
                og_url = meta_content(loaded['sel'], 'og:url')
                if '?v=jav' in og_url:
                    og = meta_content(loaded['sel'], 'og:title')
                    if og:
                        add(og_url.replace('//www', 'https://www'), og.split(' ')[0], og, 100)

        try:
            query = ' '.join(tokens[:2]) or ctx.title
            for candidate_url in await self._web_search_vjav(query, ctx.site_info.base_url):
                detail = await self.fetch_and_load(candidate_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] {candidate_url}')
                if not detail:
                    continue
                post_title = first_attr(detail['sel'], '(//h3[contains(@class,"post-title") and contains(@class,"text")]//a)[1]/text()')
                if not post_title:
                    continue
                title = ' '.join(post_title.split(' ')[1:])
                jav_id = (detail['sel'].xpath('(//td[contains(.,"ID:")])[1]/following-sibling::td[1]').xpath('normalize-space(.)').get() or '').strip()
                og_url = meta_content(detail['sel'], 'og:url')
                scene_url = (og_url or candidate_url).replace('//www', 'https://www')
                add(scene_url, jav_id, title, sceneid_distance_score(search_javid.lower(), jav_id.lower()) if search_javid else None)
        except Exception as err:  # noqa: BLE001
            logger.debug(ctx.site_info.name, f'webSearch fallback: {err}')

    # ── Detail field hooks ────────────────────────────────────────────────────

    def _table_link(self, scene: LoadedScene, label: str) -> str:
        assert scene.sel is not None
        return (scene.sel.xpath(f'(//td[contains(.,"{label}")])[1]/following-sibling::td[1]//span//a[1]/text()').get() or '').strip()

    def _og_jav_id(self, scene: LoadedScene) -> str:
        assert scene.sel is not None
        return meta_content(scene.sel, 'og:title').split(' ')[0]

    def _og_title_parts(self, scene: LoadedScene) -> tuple[str, str]:
        assert scene.sel is not None
        og = meta_content(scene.sel, 'og:title')
        if not og:
            return '', ''
        jav_id = og.split(' ')[0]
        title = ' '.join(og.split(' ')[1:]).replace(' - JAVLibrary', '').replace(jav_id, '').strip()
        return jav_id, title

    def _release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//td[contains(.,"Release Date:")])[1]/following-sibling::td[1]').xpath('normalize-space(.)').get() or '').strip()
        return (iso_date(raw, '%Y-%m-%d') if raw else None) or scene.scene_date or None

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        jav_id, title = self._og_title_parts(scene)
        if not jav_id:
            return
        metadata.title = f'[{jav_id.upper()}] {title}'

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        _, title = self._og_title_parts(scene)
        metadata.summary = title_case(title) if len(title) > 80 else ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = self._table_link(scene, 'Maker:') or ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._table_link(scene, 'Label:') or None

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        label = self._table_link(scene, 'Label:')
        maker = self._table_link(scene, 'Maker:')
        metadata.collections = [label or maker or 'Japan Adult Video']

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = self._release_date(scene)

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//a[@rel="category tag"]')]
        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()

        def add(name: str) -> None:
            n = name.strip()
            if n and n.lower() not in seen:
                seen.add(n.lower())
                actors.append(ActorResult(name=n))

        jav_id = self._og_jav_id(scene)
        for name, ids in _ACTORS.items():
            if any(i.lower() == jav_id.lower() for i in ids):
                add(name)
        for el in scene.sel.xpath('//span[contains(@class,"star")]//a'):
            add(el.xpath('normalize-space(.)').get() or '')
        metadata.actors = actors

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        name = self._table_link(scene, 'Director:')
        metadata.directors = [ActorResult(name=name)] if name else None

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        coll = self.image_collector(lambda raw: (raw or '').strip())

        poster = first_attr(scene.sel, '(//img[@id="video_jacket_img"]/@src)[1]')
        if poster and 'https' not in poster:
            poster = f'https:{poster}'
        coll['push'](poster)

        for thumb in scene.sel.xpath('//div[contains(@class,"previewthumbs")]//img/@src').getall():
            thumb = (thumb or '').strip()
            m = re.search(r'-([1-9]+)\.jpg', thumb)
            coll['push'](f'{thumb[: m.start()]}jp{thumb[m.start() :]}' if m else thumb)

        jav_id = self._og_jav_id(scene)
        if jav_id:
            for lib_id, bus_id in _CROSS_SITE.items():
                if jav_id.lower() == lib_id.lower():
                    jav_id = bus_id
                    break
            await push_javbus_images(self.http, coll, jav_id, _IGNORE_LIST, self._release_date(scene))
        metadata.raw_image_urls = coll['list']
