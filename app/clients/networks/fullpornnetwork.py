from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr
from app.utils.searchengines import SearchOptions, web_search, web_search_available

STUDIO = 'Full Porn Network'


def _after_colon(text: str) -> str:
    i = text.find(':')
    return (text[i + 1 :] if i >= 0 else text).strip()


class FullPornNetworkClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        host = urlsplit(ctx.site_info.base_url).netloc.removeprefix('www.')
        q = ctx.title.strip()

        google: list[str] = []
        if web_search_available():
            try:
                google = await web_search(SearchOptions(query=q, site=host, num=10))
            except Exception:  # noqa: BLE001 - best-effort
                google = []

        direct_slug = q.replace(' ', '-').lower() if q.count(' ') > 1 else q.replace(' ', '')
        model_urls: list[str] = [f'{base}/models/{direct_slug}.html']
        trailer_urls: list[str] = []
        for url in google:
            if '/trailers/' in url and url not in trailer_urls:
                trailer_urls.append(url)
            if '/models/' in url and 'models_' not in url and 'join' not in url and url not in model_urls:
                model_urls.append(url)

        results: list[SearchResult] = []
        seen: set[str] = set()

        for scene_url in trailer_urls:
            if scene_url in seen:
                continue
            loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] trailer {scene_url}')
            if not loaded:
                continue
            title = _after_colon(loaded['sel'].xpath('(//h1[contains(@class,"title_bar")])[1]').xpath('string(.)').get() or '')
            if not title:
                continue
            date_raw = (loaded['sel'].xpath('(//div[contains(@class,"video-info")]//p)[1]').xpath('string(.)').get() or '').strip()
            date_iso = iso_date(date_raw) if date_raw else None
            seen.add(scene_url)
            carried = date_iso or ctx.search_date or ''
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=q,
                    display_date=date_iso,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, carried) if x]),
                )
            )

        def harvest(sel: Any) -> None:
            for el in sel.xpath('//div[contains(@class,"latest-updates")]//div[@data-setid]'):
                href = first_attr(el, '(.//a[@class="updateimg"])[1]/@href')
                if not href:
                    continue
                scene_url = absolute_url(href, ctx.site_info.base_url)
                if scene_url in seen:
                    continue
                title = _after_colon(el.xpath('string(.)').get() or '')
                if not title:
                    continue
                seen.add(scene_url)
                results.append(build_search_result(title=title, scene_url=scene_url, query=q, search_date=ctx.search_date))

        for model_url in model_urls:
            loaded = await self.fetch_and_load(model_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] model {model_url}')
            if not loaded:
                continue
            harvest(loaded['sel'])
            next_href = first_attr(loaded['sel'], '(//a[contains(@class,"pagenav")])[1]/@href')
            if next_href:
                nxt = await self.fetch_and_load(absolute_url(next_href, ctx.site_info.base_url), FetchCtx(capture=ctx.capture), 'GET model page 2')
                if nxt:
                    harvest(nxt['sel'])

        return results

    # ── Field hooks ───────────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return _after_colon(scene.sel.xpath('(//h1[contains(@class,"title_bar")])[1]').xpath('string(.)').get() or '') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (
            scene.sel.xpath('(//div[contains(@class,"video-description")]//p[contains(@class,"description-text")])[1]').xpath('string(.)').get() or ''
        ).strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//div[contains(@class,"video-info")]//p)[1]').xpath('string(.)').get() or '').strip()
        return (iso_date(raw) if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        out = [
            g
            for g in (
                first_attr(a, 'normalize-space(.)')
                for a in scene.sel.xpath('//div[contains(@class,"video-info")]//a[contains(@href,"/categories/")]')
            )
            if g
        ]
        return out or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        refs: list[tuple[str, str]] = []
        for a in scene.sel.xpath('//div[contains(@class,"video-info")]//a[contains(@href,"/models/")]'):
            name = first_attr(a, 'normalize-space(.)')
            href = first_attr(a, '@href')
            if name and href:
                refs.append((name, absolute_url(href, base)))
        if not refs:
            return None
        actors: list[ActorResult] = []
        for name, href in refs:
            page = await self.fetch_and_load(href, None, f'GET {href} (model)')
            raw = first_attr(page['sel'], '(//img[@alt="model"])[1]/@src0_3x') if page else ''
            actors.append(ActorResult(name=name, photo_url=absolute_url(raw, base) if raw else ''))
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        coll = self.image_collector(lambda raw: (raw if 'http' in raw else absolute_url(raw, scene.site.base_url)).replace('-1x.jpg', '-3x.jpg'))
        for raw in scene.sel.xpath('//video/@poster').getall():
            coll['push'](raw)
        images: list[str] = coll['list']
        return images or None
