from __future__ import annotations

import json
import re
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneContext, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import web_search_urls
from app.utils.searchengines import web_search_available

STUDIO = 'Score Group'
_LATEST_RE = re.compile(r'Latest.*Videos')
_ID_RE = re.compile(r'/(\d+)/')
_POSTER_RE = re.compile(r"posterImage:\s*'([^']+)'")
_POSTERTHUMBS_RE = re.compile(r'(?<=PosterThumbs)/\d\d')


def _clean_title(raw: str) -> str:
    return raw.replace('Coming Soon:', '').strip()


class ScoreGroupClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {url}')
        sources: list[Any] = list(loaded['sel'].xpath('//div[contains(@class,"compact") and contains(@class,"video")]')) if loaded else []

        video_list_path = ctx.site_info.sub_group or '/'
        candidate_urls: list[str] = []

        if not ctx.scene_id and ctx.full_title:
            all_digits = re.sub(r'\D', '', ctx.full_title)
            actor_slug = re.sub(r'\s\d.*', '', ctx.full_title).replace(' ', '-')
            if all_digits and actor_slug:
                candidate_urls.append(f'{base}{video_list_path}{actor_slug}/{all_digits}/')

        if web_search_available():
            for u in await web_search_urls(ctx.title, ctx.site_info, include=[video_list_path], exclude=['?']):
                if u not in candidate_urls:
                    candidate_urls.append(u)

        sources.extend({'_url': u} for u in candidate_urls)
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def build_search_results(self, source: Any, loaded: LoadedSearch) -> list[SearchResult]:
        ctx = loaded.ctx
        if isinstance(source, dict) and '_url' in source:
            page = await self.fetch_and_load(source['_url'], FetchCtx(capture=ctx.capture), f'[{loaded.site.name}] candidate {source["_url"]}')
            if not page:
                return []
            title = (page['sel'].xpath('(//h1)[1]').xpath('string(.)').get() or '').strip()
            if not title or '404' in title or _LATEST_RE.search(title):
                return []
            packed = json.dumps({'url': source['_url'], 'date': ctx.search_date, 'title': title})
            return [
                build_search_result(
                    title=_clean_title(title), scene_url=source['_url'], query=ctx.title, search_date=ctx.search_date, cur_id=pack_cur_id([packed])
                )
            ]

        anchor = source.xpath('(.//a[contains(@class,"title")])[1]')
        raw_title = (anchor.xpath('string(.)').get() or '').strip()
        href = (anchor.xpath('@href').get() or '').strip().split('?')[0]
        if not raw_title or not href:
            return []
        scene_url = absolute_url(href, loaded.site.base_url)
        m = _ID_RE.search(scene_url)
        score = 100 if ctx.scene_id and m and m.group(1) == ctx.scene_id else None
        packed = json.dumps(
            {
                'url': scene_url,
                'date': ctx.search_date,
                'title': raw_title,
                'actors': (source.xpath('(.//small[contains(@class,"i-model")])[1]').xpath('string(.)').get() or '').strip(),
                'img': (source.xpath('(.//img)[1]/@src').get() or '').strip(),
            }
        )
        return [
            build_search_result(
                title=_clean_title(raw_title), scene_url=scene_url, query=ctx.title, search_date=ctx.search_date, score=score, cur_id=pack_cur_id([packed])
            )
        ]

    # ── Context loader ──────────────────────────────────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        try:
            packed = json.loads(payload)
            if not isinstance(packed, dict):
                raise ValueError
        except (ValueError, TypeError):
            pipe = payload.find('|')
            packed = {'url': payload[:pipe] if pipe >= 0 else payload}
            if pipe >= 0:
                packed['date'] = payload[pipe + 1 :].strip()
        if not packed.get('url'):
            return None

        loaded = await self.fetch_and_load(packed['url'], FetchCtx(capture=ctx.capture if ctx else None), f'[{site.name}] scene {packed["url"]}')
        if not loaded:
            return None
        is_latest = bool(_LATEST_RE.search((loaded['sel'].xpath('(//h1)[1]').xpath('string(.)').get() or '').strip()))
        return LoadedScene(
            url=packed['url'],
            site=site,
            scene_date=packed.get('date') or None,
            capture=ctx.capture if ctx else None,
            sel=loaded['sel'],
            html=loaded['html'],
            extra={'packed': packed, 'is_latest': is_latest},
        )

    def _data(self, scene: LoadedScene) -> tuple[dict[str, Any], bool]:
        extra = scene.extra or {}
        return extra.get('packed', {'url': scene.url}), bool(extra.get('is_latest'))

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        packed, is_latest = self._data(scene)
        if is_latest and packed.get('title'):
            return _clean_title(packed['title'])
        raw = (scene.sel.xpath('(//h1)[1]').xpath('string(.)').get() or '').strip()
        if not raw:
            names = [n for n in ((a.xpath('normalize-space(.)').get() or '').strip() for a in scene.sel.xpath('//div//span[@class="value"]/a')) if n]
            raw = ' and '.join(names)
        return _clean_title(raw) or None if raw else None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//div[contains(@class,"p-desc")] | //div[contains(@class,"desc")])[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//div//span[@class="value"])[2]').xpath('string(.)').get() or '').strip()
        if raw:
            return iso_date(raw)
        return (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [
            a.xpath('normalize-space(.)').get()
            for a in scene.sel.xpath('//div[@class="mb-3"]//a | //div[contains(@class,"desc")]//a[contains(@href,"tag") or contains(@href,"category")]')
        ]
        return self.dedup_strings(values) or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        packed, is_latest = self._data(scene)
        actors: list[ActorResult] = []
        seen: set[str] = set()

        if is_latest:
            for raw in (packed.get('actors') or '').split(','):
                name = raw.strip()
                if name and name not in seen:
                    seen.add(name)
                    actors.append(ActorResult(name=name))
            return actors or None

        base = scene.site.base_url
        for el in scene.sel.xpath('//div//span[@class="value"]/a'):
            name = (el.xpath('normalize-space(.)').get() or '').strip()
            href = (el.xpath('@href').get() or '').strip().split('?')[0]
            if not name or name.lower() == 'extra' or name in seen:
                continue
            seen.add(name)
            gender = 'male' if '/male-' in href else ''
            photo = ''
            if href:
                page = await self.fetch_and_load(absolute_url(href, base), None, f'[{scene.site.name}] actor {name}')
                photo = (page['sel'].xpath('(//div[contains(@class,"item-img")]//img)[1]/@src').get() or '').strip() if page else ''
            actors.append(ActorResult(name=name, photo_url=photo, gender=gender))

        if scene.site.name == 'Christy Marks' and not any(a.name == 'Christy Marks' for a in actors):
            actors.append(ActorResult(name='Christy Marks'))
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []

        def push(raw: str) -> None:
            if not raw:
                return
            url = raw if raw.startswith('http') else (f'https:{raw}' if raw.startswith('//') else raw)
            if 'shared-bits' in url or '/join' in url:
                return
            m = _POSTERTHUMBS_RE.search(url)
            if m:
                for i in range(1, 7):
                    variant = url.replace(m.group(0), f'/{i:02d}')
                    if variant not in images:
                        images.append(variant)
                return
            if url not in images:
                images.append(url)

        packed, is_latest = self._data(scene)
        if is_latest and packed.get('img'):
            push(packed['img'])

        pm = _POSTER_RE.search(scene.html or '')
        if pm:
            push(pm.group(1))

        xpaths = (
            '//div[contains(@class,"thumb")]//img/@src',
            '//div[contains(@class,"p-image")]//a//img/@src',
            '//div[contains(@class,"p-photos")]//a/@href',
            '//div[contains(@class,"gallery")]//a/@href',
        )
        for xpath in xpaths:
            for raw in scene.sel.xpath(xpath).getall():
                push(raw)
        return images or None
