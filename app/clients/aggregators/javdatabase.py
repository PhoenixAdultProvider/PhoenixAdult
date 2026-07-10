from __future__ import annotations

import re
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import decensor, iso_date, load_site_json, pad_jav_id, sceneid_distance_score
from app.utils.helpers.html_helpers import first_attr, meta_content
from app.utils.helpers.javbus_images import fetch_javbus_images
from app.utils.processors.title_case import title_case

_TABLES = load_site_json(__file__, 'javdatabase_tables')
_SCENE_ACTORS: dict[str, list[str]] = load_site_json(__file__, 'javdatabase_scene_actors')
_CENSORED: dict[str, str] = _TABLES['censoredWords']
_ACTOR_CORRECTIONS: dict[str, list[str]] = _TABLES['actorCorrections']
_CROSS_SITE: dict[str, list[str]] = _TABLES['crossSite']
_IGNORE_LIST: list[str] = _TABLES['ignoreList']

_LABELS = ('b', 'strong', 'span', 'th', 'dt', 'h4', 'p', 'label')
_LABEL_XP = ' | '.join(f'//{t}' for t in _LABELS)


def _label_text_value(sel: Any, label: str) -> str:
    target = label.strip()
    for el in sel.xpath(_LABEL_XP):
        if first_attr(el, 'normalize-space(.)') != target:
            continue
        for node in el.xpath('following-sibling::text()').getall():
            txt = str(node).strip()
            if txt:
                return txt
    return ''


def _label_link_value(sel: Any, label: str) -> str:
    target = label.strip()
    for el in sel.xpath(_LABEL_XP):
        if first_attr(el, 'normalize-space(.)') != target:
            continue
        return first_attr(el, 'following-sibling::span[1]//a[1]/text()')
    return ''


class JAVDatabaseClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        tokens = ctx.title.strip().split()
        if tokens:
            tokens[0] = re.sub(r'^(13dsvr|3dsvr)', 'dsvr', tokens[0], flags=re.IGNORECASE)
        search_javid = f'{tokens[0]}-{tokens[1]}' if len(tokens) > 1 and re.fullmatch(r'\d+', tokens[1]) else None
        encoded = search_javid or ctx.encoded
        url = f'{base}{ctx.site_info.search_path.replace("{query}", encoded)}'
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {url}')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//div[contains(@class,"card h-100")]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture, extra={'search_javid': search_javid, 'base': base})

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        raw_title = first_attr(source, '(.//div[contains(@class,"mt-auto")]//a)[1]/text()')
        jav_id = first_attr(source, '(.//p//a[contains(@class,"cut-text")])[1]/text()')
        return f'[{jav_id}] {raw_title}' if raw_title else ''

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//p//a[contains(@class,"cut-text")])[1]/@href')
        if not href:
            return ''
        base = loaded.extra['base']
        return href if href.startswith('http') else f'{base}{href}'

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        nodes = source.xpath('(.//div[contains(@class,"mt-auto")])[1]/text()').getall()
        tok = nodes[1].strip() if len(nodes) > 1 else ''
        return iso_date(tok) if tok else None

    async def fetch_search_score(self, source: Any, loaded: LoadedSearch) -> float | None:
        search_javid = loaded.extra['search_javid']
        if not search_javid:
            return None
        jav_id = first_attr(source, '(.//p//a[contains(@class,"cut-text")])[1]/text()')
        return sceneid_distance_score(search_javid.lower(), jav_id.lower())

    # ── Detail field hooks ────────────────────────────────────────────────────

    def _jav_id(self, scene: LoadedScene) -> str:
        assert scene.sel is not None
        return meta_content(scene.sel, 'og:title')

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        jav_id = self._jav_id(scene)
        raw = decensor(_label_text_value(scene.sel, 'Title:'), _CENSORED)
        if not raw:
            return f'[{jav_id.upper()}]' if jav_id else None
        return f'[{jav_id.upper()}] {raw}'

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = decensor(_label_text_value(scene.sel, 'Title:'), _CENSORED)
        return title_case(raw) if len(raw) > 80 else None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        studio = _label_link_value(scene.sel, 'Studio:')
        return decensor(studio, _CENSORED) if studio else None

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        studio = await self.fetch_studio(scene)
        return [studio or 'Japan Adult Video']

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = _label_text_value(scene.sel, 'Release Date:')
        return (iso_date(raw, '%Y-%m-%d') if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres: list[str] = []
        for el in scene.sel.xpath(_LABEL_XP):
            if first_attr(el, 'normalize-space(.)') != 'Genre(s):':
                continue
            for a in el.xpath('following-sibling::*//a'):
                g = first_attr(a, 'normalize-space(.)')
                if g and g not in genres:
                    genres.append(decensor(g, _CENSORED))
        return genres

    async def _is_unknown_thumb(self, url: str) -> bool:
        if not url:
            return False
        try:
            r = await self.http.get(url)
            return 'unknown.' in str(r.url)
        except Exception:  # noqa: BLE001 - unreachable thumb keeps the URL
            return False

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        jav_id = self._jav_id(scene)
        correction = _ACTOR_CORRECTIONS.get(jav_id.upper())
        correction_lower = [n.lower() for n in correction] if correction else None

        candidates: list[dict[str, str]] = []
        for card in scene.sel.xpath('(//h4[contains(.,"Actress/Idols")])[1]/..//div[contains(@class,"card-body")]'):
            name = first_attr(card, '(.//a[contains(@class,"cut-text")])[1]/text()')
            if not name:
                continue
            if correction_lower is not None and name.lower() not in correction_lower:
                continue
            raw = card.xpath('(.//div[contains(@class,"idol-thumb")]//img/@src)[1]').get() or ''
            candidates.append({'name': name, 'photo': raw.replace('thumb/', 'full/').replace('melody-marks', 'melody-hina-marks')})

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

        for name, ids in _SCENE_ACTORS.items():
            if any(i.lower() == jav_id.lower() for i in ids):
                add(name, '')
        return actors

    async def fetch_directors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        name = _label_link_value(scene.sel, 'Director:')
        return [ActorResult(name=name)] if name else None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []

        def push(raw: str) -> None:
            url = (raw or '').split('?')[0].strip()
            if url and url not in images:
                images.append(url)

        for src in scene.sel.xpath('//tr[contains(@class,"moviecovertb")]//img/@src').getall():
            push(src)
        for href in scene.sel.xpath('(//h2[contains(.,"Images")])[1]/../a/@href').getall():
            push(href)

        jav_id = self._jav_id(scene)
        if jav_id:
            for jav_bus_id, db_ids in _CROSS_SITE.items():
                if any(i.lower() == jav_id.lower() for i in db_ids):
                    jav_id = jav_id.replace(db_ids[0], jav_bus_id)
                    break
            jav_id = pad_jav_id(jav_id, _IGNORE_LIST)
            date = await self.fetch_release_date(scene)
            for u in await fetch_javbus_images(self.http, jav_id, date):
                push(u)
        return images
