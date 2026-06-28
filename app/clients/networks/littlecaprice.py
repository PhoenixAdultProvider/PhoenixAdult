from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneContext, SearchContext
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, iso_date, join_url, load_site_json
from app.utils.helpers.html_helpers import first_attr

STUDIO = 'LittleCaprice'

_CATEGORY_TAGLINES: dict[str, str] = load_site_json(__file__, 'littlecaprice_category_taglines')


class LittleCapriceClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = f'{base}/?s={ctx.encoded}'
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {url}')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//div[@id="left-area"]/article'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath('(.//h2[contains(@class,"entry-title")]/a)[1]').xpath('string(.)').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//h2[contains(@class,"entry-title")]/a)[1]/@href')
        return absolute_url(href, loaded.site.base_url) if href else ''

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        return iso_date((source.xpath('(.//span[contains(@class,"published")])[1]').xpath('string(.)').get() or '').strip())

    # ── Context loader (two-hop: gallery page → video page) ─────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        pipe = payload.find('|')
        url = payload[:pipe] if pipe >= 0 else payload
        fallback = payload[pipe + 1 :].strip() if pipe >= 0 else None

        gallery = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture if ctx else None), f'[{site.name}] gallery {url}')
        if not gallery:
            return None
        detail = gallery
        video_href = first_attr(gallery['sel'], '(//a[contains(@class,"et_pb_button")])[2]/@href')
        if video_href:
            video = await self.fetch_and_load(absolute_url(video_href, site.base_url), FetchCtx(capture=ctx.capture if ctx else None), f'GET {video_href}')
            if video:
                detail = video
        return LoadedScene(
            url=url,
            site=site,
            scene_date=fallback or None,
            capture=ctx.capture if ctx else None,
            sel=detail['sel'],
            html=detail['html'],
            extra={'gallery': gallery['sel']},
        )

    # ── Detail field hooks ────────────────────────────────────────────────────

    def _tagline_of(self, scene: LoadedScene) -> str:
        assert scene.sel is not None
        cls = scene.sel.xpath('(//div[@id="main-project-content"])[1]/@class').get() or ''
        for token in cls.split():
            if token in _CATEGORY_TAGLINES:
                return _CATEGORY_TAGLINES[token]
        return scene.site.name

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        title = (scene.sel.xpath('(//div[contains(@class,"project-details")]//h1)[1]').xpath('string(.)').get() or '').strip()
        tagline = self._tagline_of(scene)
        if title.lower().startswith(tagline.lower()):
            title = title[len(tagline) :].strip()
        return title or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//div[contains(@class,"desc-text")])[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return self._tagline_of(scene)

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [self._tagline_of(scene)]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        text = scene.sel.xpath('(//div[contains(@class,"relese-date")])[1]').xpath('string(.)').get() or ''
        raw = text.split('Release:')[1].strip() if 'Release:' in text else ''
        return (iso_date(raw) if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres: list[str] = []

        def add(sel: Any) -> None:
            for a in sel.xpath('//div[contains(@class,"project-tags")]/div[contains(@class,"list")]/a'):
                g = first_attr(a, 'normalize-space(.)').lower()
                if g and g not in genres:
                    genres.append(g)

        add(scene.sel)
        gallery = (scene.extra or {}).get('gallery')
        if gallery is not None:
            add(gallery)
        cast = len(scene.sel.xpath('//div[contains(@class,"project-models")]//a'))
        if cast == 3:
            genres.append('Threesome')
        elif cast == 4:
            genres.append('Foursome')
        elif cast > 4:
            genres.append('Orgy')
        return genres or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        actors: list[ActorResult] = []
        for el in scene.sel.xpath('//div[contains(@class,"project-models")]//a'):
            name = first_attr(el, 'normalize-space(.)')
            if not name:
                continue
            if name == 'LittleCaprice':
                name = 'Little Caprice'
            photo = ''
            href = first_attr(el, '@href')
            if href:
                page = await self.fetch_and_load(absolute_url(href, base), None, f'GET {href} (actor)')
                raw = first_attr(page['sel'], '(//img[contains(@class,"img-poster")])[1]/@src') if page else ''
                if raw:
                    photo = absolute_url(raw, base)
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        images: list[str] = []

        def push(raw: str) -> None:
            if not raw:
                return
            abs_url = join_url(raw, base)
            if abs_url not in images:
                images.append(abs_url)

        push(first_attr(scene.sel, '(//meta[@property="og:image"])[1]/@content'))
        gallery = (scene.extra or {}).get('gallery')
        if gallery is not None:
            push(first_attr(gallery, '(//meta[@property="og:image"])[1]/@content'))
            for src in gallery.xpath('//div[contains(@class,"gallery") and contains(@class,"spotlight-group")]//img/@src').getall():
                push(src)
        return images or None
