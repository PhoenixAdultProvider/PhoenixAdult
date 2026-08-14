from __future__ import annotations

import re
from typing import Any, TypedDict

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from phoenixadult.utils.helpers.helpers import decensor, iso_date, load_data, sceneid_distance_score
from phoenixadult.utils.helpers.html_helpers import first_attr, meta_content
from phoenixadult.utils.helpers.javbus_images import push_javbus_images
from phoenixadult.utils.processors.title_case import title_case

_TABLES = load_data(__file__, 'javdatabase_tables')
_SCENE_ACTORS: dict[str, list[str]] = load_data(__file__, 'javdatabase_scene_actors')
_CENSORED: dict[str, str] = _TABLES['censoredWords']
_ACTOR_CORRECTIONS: dict[str, list[str]] = _TABLES['actorCorrections']
_CROSS_SITE: dict[str, list[str]] = _TABLES['crossSite']
_IGNORE_LIST: list[str] = _TABLES['ignoreList']

_LABELS = ('b', 'strong', 'span', 'th', 'dt', 'h4', 'p', 'label')
_LABEL_XP = ' | '.join(f'//{t}' for t in _LABELS)


def _label_text_value(sel: Any, label: str) -> str:
    target = label.strip()
    for row in sel.xpath(_LABEL_XP):
        if first_attr(row, 'normalize-space(.)') != target:
            continue

        for node in row.xpath('following-sibling::text()').getall():
            txt = str(node).strip()
            if txt:
                return txt

    return ''


def _label_link_value(sel: Any, label: str) -> str:
    target = label.strip()
    for row in sel.xpath(_LABEL_XP):
        if first_attr(row, 'normalize-space(.)') != target:
            continue

        return first_attr(row, 'following-sibling::span[1]//a[1]/text()')

    return ''


class _SearchExtra(TypedDict):
    search_javid: str | None
    base: str


class JAVDatabaseClient(Client):
    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        base = search_data.site_info.base_url.rstrip('/')
        tokens = search_data.title.strip().split()
        if tokens:
            tokens[0] = re.sub(r'^(13dsvr|3dsvr)', 'dsvr', tokens[0], flags=re.IGNORECASE)

        search_javid = f'{tokens[0]}-{tokens[1]}' if len(tokens) > 1 and re.fullmatch(r'\d+', tokens[1]) else None
        encoded = search_javid or search_data.encoded
        url = search_data.search_url(encoded)
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {url}')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath('//div[contains(@class,"card h-100")]'))
        extra: _SearchExtra = {'search_javid': search_javid, 'base': base}
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture, extra=extra)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        raw_title = first_attr(source, '(.//div[contains(@class,"mt-auto")]//a)[1]/text()')
        jav_id = first_attr(source, '(.//p//a[contains(@class,"cut-text")])[1]/text()')
        return f'[{jav_id}] {raw_title}' if raw_title else ''

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//p//a[contains(@class,"cut-text")])[1]/@href')
        if not href:
            return ''

        extra: _SearchExtra = loaded.extra
        base = extra['base']
        return href if href.startswith('http') else f'{base}{href}'

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        nodes = source.xpath('(.//div[contains(@class,"mt-auto")])[1]/text()').getall()
        tok = nodes[1].strip() if len(nodes) > 1 else ''
        return iso_date(tok) if tok else None

    async def fetch_search_score(self, source: Any, loaded: LoadedSearch) -> float | None:
        extra: _SearchExtra = loaded.extra
        search_javid = extra['search_javid']
        if not search_javid:
            return None

        jav_id = first_attr(source, '(.//p//a[contains(@class,"cut-text")])[1]/text()')
        return sceneid_distance_score(search_javid.lower(), jav_id.lower())

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _jav_id(self, scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        return meta_content(details_page_elements, 'og:title')

    def _studio(self, scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        studio = _label_link_value(details_page_elements, 'Studio:')
        return decensor(studio, _CENSORED) if studio else ''

    def _release_date(self, scene: LoadedScene) -> str | None:
        details_page_elements = scene.require_sel()

        date = _label_text_value(details_page_elements, 'Release Date:')
        return (iso_date(date, '%Y-%m-%d') if date else None) or scene.scene_date or None

    async def _is_unknown_thumb(self, url: str) -> bool:
        if not url:
            return False

        try:
            r = await self.http.get(url)
            return 'unknown.' in str(r.url)
        except Exception:  # noqa: BLE001 - unreachable thumb keeps the URL
            return False

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        jav_id = self._jav_id(scene)
        raw = decensor(_label_text_value(details_page_elements, 'Title:'), _CENSORED)
        if not raw:
            metadata.title = f'[{jav_id.upper()}]' if jav_id else ''
            return

        metadata.title = f'[{jav_id.upper()}] {raw}'

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = decensor(_label_text_value(details_page_elements, 'Title:'), _CENSORED)

        metadata.summary = title_case(raw) if len(raw) > 80 else ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = self._studio(scene)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [self._studio(scene) or 'Japan Adult Video']

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = self._release_date(scene)

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres: list[str] = []
        for label in details_page_elements.xpath(_LABEL_XP):
            if first_attr(label, 'normalize-space(.)') != 'Genre(s):':
                continue

            for genre_link in label.xpath('following-sibling::*//a'):
                genre_name = first_attr(genre_link, 'normalize-space(.)')
                if genre_name and genre_name not in genres:
                    genres.append(decensor(genre_name, _CENSORED))

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        jav_id = self._jav_id(scene)
        correction = _ACTOR_CORRECTIONS.get(jav_id.upper())
        correction_lower = [n.lower() for n in correction] if correction else None

        candidates: list[dict[str, str]] = []
        for card in details_page_elements.xpath('(//h4[contains(.,"Actress/Idols")])[1]/..//div[contains(@class,"card-body")]'):
            actor_name = first_attr(card, '(.//a[contains(@class,"cut-text")])[1]/text()')
            if not actor_name:
                continue

            if correction_lower is not None and actor_name.lower() not in correction_lower:
                continue

            raw = card.xpath('(.//div[contains(@class,"idol-thumb")]//img/@src)[1]').get() or ''
            candidates.append({'name': actor_name, 'photo': raw.replace('thumb/', 'full/').replace('melody-marks', 'melody-hina-marks')})

        actors: list[ActorResult] = []
        seen: set[str] = set()

        def add(name: str, photo: str) -> None:
            if not name or name.lower() in seen:
                return

            seen.add(name.lower())
            actors.append(ActorResult(name=name, photo_url=photo))

        for c in candidates:
            photo = '' if c['photo'] and await self._is_unknown_thumb(c['photo']) else c['photo']
            add(c['name'], photo)

        for actor_name, ids in _SCENE_ACTORS.items():
            if any(i.lower() == jav_id.lower() for i in ids):
                add(actor_name, '')

        metadata.actors = actors

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        director_name = _label_link_value(details_page_elements, 'Director:')

        metadata.directors = [ActorResult(name=director_name)] if director_name else None

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: image.split('?')[0].strip())

        for src in details_page_elements.xpath('//tr[contains(@class,"moviecovertb")]//img/@src').getall():
            images['push'](src)

        for href in details_page_elements.xpath('(//h2[contains(.,"Images")])[1]/../a/@href').getall():
            images['push'](href)

        jav_id = self._jav_id(scene)
        if jav_id:
            for jav_bus_id, db_ids in _CROSS_SITE.items():
                if any(i.lower() == jav_id.lower() for i in db_ids):
                    jav_id = jav_id.replace(db_ids[0], jav_bus_id)
                    break

            await push_javbus_images(self.http, images, jav_id, _IGNORE_LIST, self._release_date(scene))

        metadata.art = images['list']
