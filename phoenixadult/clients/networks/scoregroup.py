from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx2
from parsel import Selector

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id, same_scene
from phoenixadult.utils.helpers.html_helpers import first_attr, web_search_urls
from phoenixadult.utils.logging.logger import logger

STUDIO = 'Score Group'
_SEARCH_PATH = '/search-es'
_SEARCH_FILTERS = {'s_filters[type]': 'videos', 's_filters[site]': 'current'}
_LATEST_RE = re.compile(r'Latest.*Videos')
_ID_RE = re.compile(r'/(\d+)/')
_READ_MORE_RE = re.compile(r'\s*Read More\s*»?', re.IGNORECASE)
_POSTER_RE = re.compile(r"posterImage:\s*'([^']+)'")
_POSTERTHUMBS_RE = re.compile(r'(?<=PosterThumbs)/\d\d')
_SCRIPT_POSTER_RE = re.compile(r"(?<=poster: ')[^']*")
_SHOT_RE = re.compile(r'^(?P<prefix>(?:https?:)?//[^/]+/(?P<site>[^/]+)/scenes/[^/]+)/Screenshots/', re.IGNORECASE)
_GALLERY_CAP = 60
_GALLERY_BATCH = 8
_DATE_XPATHS = ('//div[./span[contains(., "Date:")]]//span[@class="value"]', '(//div//span[@class="value"])[2]')


def _clean_title(raw: str) -> str:
    return raw.replace('Coming Soon:', '').strip()


def _scene_date(sel: Selector) -> str:
    for xpath in _DATE_XPATHS:
        raw = (sel.xpath(xpath).xpath('string(.)').get() or '').strip()
        parsed = iso_date(raw) if raw else None
        if parsed:
            return parsed

    return ''


def _keywords(search_data: SearchContext) -> str:
    digits = search_data.scene_id or re.sub(r'\D', '', search_data.title)
    if not digits:
        return search_data.title

    return re.sub(r'\s+', ' ', search_data.title.replace(digits, '', 1)).strip() or search_data.title


class ScoreGroupClient(Client):
    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        base = search_data.site_info.base_url.rstrip('/')
        url = base + _SEARCH_PATH
        form = {'keywords': _keywords(search_data), **_SEARCH_FILTERS}
        ctx = FetchCtx(capture=search_data.capture, use_bypass=search_data.site_info.use_bypass)
        search_results = await self.fetch_and_load(url, ctx, f'[{search_data.site_info.name}] search {url}', form=form)
        sources: list[Any] = list(search_results['sel'].xpath('//div[contains(@class,"compact") and contains(@class,"video")]')) if search_results else []

        video_list_path = search_data.site_info.search_path or '/'
        candidate_urls: list[str] = []

        if not search_data.scene_id and search_data.full_title:
            all_digits = re.sub(r'\D', '', search_data.full_title)
            actor_slug = re.sub(r'\s\d.*', '', search_data.full_title).replace(' ', '-')
            if all_digits and actor_slug:
                candidate_urls.append(f'{base}{video_list_path}{actor_slug}/{all_digits}/')

        for u in await web_search_urls(search_data.title, search_data.site_info, include=[video_list_path], exclude=['?']):
            if not any(same_scene(u) == same_scene(known) for known in candidate_urls):
                candidate_urls.append(u)

        sources.extend({'_url': u} for u in candidate_urls)
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def build_search_results(self, source: Any, loaded: LoadedSearch, results: list[SearchResult]) -> None:
        ctx = loaded.ctx
        if isinstance(source, dict) and '_url' in source:
            fetch_ctx = FetchCtx(capture=ctx.capture, use_bypass=loaded.site.use_bypass)
            details_page_elements = await self.fetch_and_load(source['_url'], fetch_ctx, f'[{loaded.site.name}] candidate {source["_url"]}')
            if not details_page_elements:
                return

            title = (details_page_elements['sel'].xpath('(//h1)[1]').xpath('string(.)').get() or '').strip()
            if not title or '404' in title or _LATEST_RE.search(title):
                return

            page_date = _scene_date(details_page_elements['sel'])
            found = _ID_RE.search(source['_url'])
            packed = json.dumps({'url': source['_url'], 'date': page_date or ctx.search_date, 'title': title})

            results.append(
                build_search_result(
                    site=loaded.site,
                    title=_clean_title(title),
                    scene_url=source['_url'],
                    query=ctx.title,
                    search_date=ctx.search_date,
                    display_date=page_date or None,
                    score=100 if ctx.scene_id and found and found.group(1) == ctx.scene_id else None,
                    cur_id=pack_cur_id([packed]),
                )
            )
            return

        anchor = source.xpath('(.//a[contains(@class,"title")])[1]')
        raw_title = first_attr(anchor)
        href = first_attr(anchor, '@href').split('?')[0]
        if not raw_title or not href:
            return

        scene_url = absolute_url(href, loaded.site.base_url)
        m = _ID_RE.search(scene_url)
        if not m:
            return

        score = 100 if ctx.scene_id and m.group(1) == ctx.scene_id else None
        packed = json.dumps(
            {
                'url': scene_url,
                'date': ctx.search_date,
                'title': raw_title,
                'actors': (source.xpath('(.//small[contains(@class,"i-model")])[1]').xpath('string(.)').get() or '').strip(),
                'img': first_attr(source, '(.//img)[1]/@src'),
            }
        )

        results.append(
            build_search_result(
                site=loaded.site,
                title=_clean_title(raw_title),
                scene_url=scene_url,
                query=ctx.title,
                search_date=ctx.search_date,
                score=score,
                cur_id=pack_cur_id([packed]),
            )
        )

    # ── Context Loader ──────────────────────────────────────────────────────────

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

        details_page_elements = await self.fetch_and_load(
            packed['url'], FetchCtx(capture=ctx.capture if ctx else None, use_bypass=site.use_bypass), f'[{site.name}] scene {packed["url"]}'
        )
        if not details_page_elements:
            return None

        is_latest = bool(_LATEST_RE.search((details_page_elements['sel'].xpath('(//h1)[1]').xpath('string(.)').get() or '').strip()))
        return LoadedScene(
            url=packed['url'],
            site=site,
            scene_date=packed.get('date') or None,
            capture=ctx.capture if ctx else None,
            sel=details_page_elements['sel'],
            html=details_page_elements['html'],
            extra={'packed': packed, 'is_latest': is_latest},
        )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _data(self, scene: LoadedScene) -> tuple[dict[str, Any], bool]:
        extra = scene.extra or {}
        return extra.get('packed', {'url': scene.url}), bool(extra.get('is_latest'))

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        packed, is_latest = self._data(scene)
        if is_latest and packed.get('title'):
            metadata.title = _clean_title(packed['title'])
            return

        raw = (details_page_elements.xpath('(//h1)[1]').xpath('string(.)').get() or '').strip()
        if not raw:
            names = [n for n in (first_attr(a, 'normalize-space(.)') for a in details_page_elements.xpath('//div//span[@class="value"]/a')) if n]
            raw = ' and '.join(names)

        metadata.title = _clean_title(raw) if raw else ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        node = details_page_elements.xpath('(//div[contains(@class,"p-desc")] | //div[contains(@class,"desc")])[1]')
        own = ' '.join(' '.join(node.xpath('./h2//text() | ./text()').getall()).split())
        if own:
            metadata.summary = own
            return

        whole = ' '.join((node.xpath('string(.)').get() or '').split())
        metadata.summary = _READ_MORE_RE.split(whole)[0].strip()

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        found = _scene_date(details_page_elements)
        if found:
            metadata.release_date = found
            return

        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            genre_link.xpath('normalize-space(.)').get()
            for genre_link in details_page_elements.xpath(
                '//div[@class="mb-3"]//a | //div[contains(@class,"desc")]//a[contains(@href,"tag") or contains(@href,"category")]'
            )
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        packed, is_latest = self._data(scene)
        actors: list[ActorResult] = []
        seen: set[str] = set()

        if is_latest:
            for raw in (packed.get('actors') or '').split(','):
                actor_name = raw.strip()
                if actor_name and actor_name not in seen:
                    seen.add(actor_name)
                    actors.append(ActorResult(name=actor_name))

            metadata.actors = actors
            return

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            return first_attr(sel, '(//div[contains(@class,"item-img")]//img)[1]/@src')

        refs: list[tuple[str, str]] = []
        genders: dict[str, str] = {}
        for actor_link in details_page_elements.xpath('//div//span[@class="value"]/a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href').split('?')[0]
            if not actor_name or actor_name.lower() == 'extra' or actor_name in seen:
                continue

            seen.add(actor_name)
            genders[actor_name] = 'male' if '/male-' in href else ''
            refs.append((actor_name, absolute_url(href, base) if href else ''))

        resolved = await self.resolve_actor_photos(refs, extract_photo, label=scene.site.name, use_bypass=scene.site.use_bypass)
        actors = [ActorResult(name=a.name, photo_url=a.photo_url, gender=genders.get(a.name, '')) for a in resolved]

        if scene.site.name == 'Christy Marks' and not any(a.name == 'Christy Marks' for a in actors):
            actors.append(ActorResult(name='Christy Marks'))

        metadata.actors = actors

    async def _reachable(self, url: str) -> bool:
        try:
            probe = await self.http.head(url)
        except httpx2.HTTPError as err:
            logger.debug(f'[scoregroup] gallery probe {url} threw: {err!r}')
            return False

        if probe.status_code >= 400 and probe.status_code not in (404, 410):
            logger.debug(f'[scoregroup] gallery probe {url} -> HTTP {probe.status_code}, ending the run there')

        return probe.status_code < 400

    async def _gallery_images(self, shot: str) -> list[str]:
        found = _SHOT_RE.match(shot)
        if not found:
            return []

        prefix = found.group('prefix')
        base = f'{prefix if prefix.startswith("http") else "https:" + prefix}/Gallys/{found.group("site")}'
        urls: list[str] = []
        for start in range(1, _GALLERY_CAP + 1, _GALLERY_BATCH):
            batch = [f'{base}/{n:02d}.jpg' for n in range(start, min(start + _GALLERY_BATCH, _GALLERY_CAP + 1))]
            for url, alive in zip(batch, await asyncio.gather(*(self._reachable(u) for u in batch)), strict=True):
                if not alive:
                    return urls

                urls.append(url)

        return urls

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

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

        for block in details_page_elements.xpath('//script[@type]/text()').getall():
            for poster in _SCRIPT_POSTER_RE.findall(block):
                push(poster)

        xpaths = (
            '//div[contains(@class,"thumb")]//img/@src',
            '//div[contains(@class,"p-image")]//a//img/@src',
            '//div[contains(@class,"dl-opts")]//a//img/@src',
            '//div[contains(@class,"p-photos")]//a/@href',
            '//div[contains(@class,"gallery")]//a/@href',
        )
        for xpath in xpaths:
            for image_url in details_page_elements.xpath(xpath).getall():
                push(image_url.replace('_tn.', '.').split('&')[0])

        probed: set[str] = set()
        derived: set[str] = set()
        superseded: set[str] = set()
        gallery: list[str] = []
        for shot in [u for u in images if '/Screenshots/' in u]:
            found = _SHOT_RE.match(shot)
            if not found:
                continue

            prefix = found.group('prefix')
            if prefix not in probed:
                probed.add(prefix)
                pages = await self._gallery_images(shot)
                if pages:
                    derived.add(prefix)
                    gallery.extend(pages)

            if prefix in derived:
                superseded.add(shot)

        if gallery:
            images[:] = [u for u in images if u not in superseded]
            for page in gallery:
                push(page)

        metadata.art = images
