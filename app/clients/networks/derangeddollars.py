from __future__ import annotations

import re
from urllib.parse import urlsplit

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date
from app.utils.helpers.html_helpers import first_attr
from app.utils.searchengines import SearchOptions, web_search_available, web_search_filtered

STUDIO = 'Deranged Dollars'
_URL_CONTAINS = '/session/'
_QUOTED_URL_RE = re.compile(r"""['"]([^'"]+\.(?:jpg|jpeg|png|webp))['"]""", re.IGNORECASE)
_NAME_SPLIT_RE = re.compile(r',|&|/| And ', re.IGNORECASE)
_NURSE_RE = re.compile(r'\bNurses?\b')


class DerangedDollarsClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        if not web_search_available():
            return
        host = urlsplit(ctx.site_info.base_url).netloc
        try:
            candidates = await web_search_filtered(SearchOptions(query=ctx.title, site=host, num=10), url_contains=_URL_CONTAINS)
        except Exception:  # noqa: BLE001 - search is best-effort
            return

        for url in candidates:
            loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] candidate {url}')
            if not loaded:
                continue
            title = (loaded['sel'].xpath('(//h3[contains(@class,"mas_title")])[1]').xpath('string(.)').get() or '').strip()
            if not title:
                continue
            lch = (loaded['sel'].xpath('(//div[contains(@class,"lch")]//span)[1]').xpath('string(.)').get() or '').strip()
            date_raw = ','.join(lch.split(',')[-2:]).strip()
            date_iso = iso_date(date_raw) if date_raw else None
            results.append(build_search_result(title=title, scene_url=url, query=ctx.title, display_date=date_iso, search_date=ctx.search_date))

    # ── Field hooks ───────────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = (scene.sel.xpath('(//h3[contains(@class,"mas_title")])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = (scene.sel.xpath('(//p[contains(@class,"mas_longdescription")])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    def _tagline(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = scene.sel.xpath('(//title)[1]').xpath('string(.)').get() or ''
        segments = [s.strip() for s in raw.split('|')]
        if len(segments) < 2:
            return None
        return re.sub(r'\.com$', '', segments[1], flags=re.IGNORECASE).strip() or None

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline(scene)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        tag = self._tagline(scene)
        metadata.collections = [tag] if tag else None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.genres = [g for g in (first_attr(a, 'normalize-space(.)') for a in scene.sel.xpath('//p[contains(@class,"tags")]//a')) if g]

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        lch = (scene.sel.xpath('(//div[contains(@class,"lch")]//span)[1]').xpath('string(.)').get() or '').strip()
        blob = ','.join(lch.split(',')[:-2]).strip()
        if not blob:
            return
        if ':' in blob:
            blob = blob.split(':', 1)[1].strip()
        raw_names = [n for n in (_NURSE_RE.sub('', re.sub(r'\W+', ' ', s)).strip() for s in _NAME_SPLIT_RE.split(blob)) if n]
        if not raw_names:
            return

        model_dir = await self._load_model_directory(scene)
        out: list[ActorResult] = []
        for raw_name in raw_names:
            name, photo = raw_name, ''
            for match_text, display_name, photo_url in model_dir:
                if raw_name.lower() in match_text.lower():
                    name, photo = display_name, photo_url
                    break
            out.append(ActorResult(name=name, photo_url=photo))
        metadata.actors = out

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        base = scene.site.base_url
        coll = self.image_collector(lambda raw: absolute_url(raw, base))
        for src in scene.sel.xpath('//div[contains(@class,"stills") and contains(@class,"clearfix")]//img/@src').getall():
            coll['push'](src)
        for script in scene.sel.xpath('//div[contains(@class,"mainpic")]//script'):
            text = script.xpath('string(.)').get() or ''
            for m in _QUOTED_URL_RE.findall(text):
                coll['push'](m)
        images: list[str] = coll['list']
        metadata.raw_image_urls = images

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _load_model_directory(self, scene: LoadedScene) -> list[tuple[str, str, str]]:
        base = scene.site.base_url.rstrip('/')
        entries: list[tuple[str, str, str]] = []
        for url in (f'{base}/?models', f'{base}/?models/2'):
            loaded = await self.fetch_and_load(url, None, f'models page {url}')
            if not loaded:
                continue
            for el in loaded['sel'].xpath('//div[contains(@class,"item")]'):
                raw = first_attr(el)
                if not raw:
                    continue
                name = raw.split(':', 1)[1].strip() if ':' in raw else raw
                photo_rel = first_attr(el, '(.//img)[1]/@src')
                photo = absolute_url(photo_rel, scene.site.base_url) if photo_rel else ''
                entries.append((name, name, photo))
        return entries
