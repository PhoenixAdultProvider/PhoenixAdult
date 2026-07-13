from __future__ import annotations

import re
from dataclasses import dataclass, field

from parsel import Selector

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text

_FULLTITLE_RE = re.compile(r'content/(.*)/')


@dataclass
class _SmtExtra:
    actors: list[ActorResult] = field(default_factory=list)
    release_date: str | None = None


class ScrewMeTooClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        encoded = ctx.title.strip().lower().replace(' ', '+').replace('--', '+')
        url = base + ctx.site_info.search_path.replace('{query}', encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return

        for card in loaded['sel'].xpath('//div[contains(@class,"fsp")]//article'):
            title = first_text(card, './/h4')
            href = first_attr(card, '(.//*[@href]/@href)[1]')
            if not title or not href:
                continue
            scene_url = absolute_url(href, ctx.site_info.base_url)
            date = iso_date(first_text(card, './/div[contains(@class,"fsdate")]//span'))
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=ctx.title,
                    display_date=date,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
                )
            )

    # ── Context loader (model headshots + cross-page release date) ────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        pipe = payload.find('|')
        url = payload[:pipe] if pipe >= 0 else payload
        fallback_date = payload[pipe + 1 :].strip() if pipe >= 0 else ''

        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture if ctx else None), f'[{site.name}] scene {url}')
        if not loaded:
            return None

        actors: list[ActorResult] = []
        last_model_sel: Selector | None = None
        for el in loaded['sel'].xpath('//a[contains(@title,"Model Bio")]'):
            name = first_attr(el, 'normalize-space(.)')
            href = first_attr(el, '@href')
            if not name or not href:
                continue
            model_url = absolute_url(href, site.base_url)
            model = await self.fetch_and_load(model_url, FetchCtx(capture=ctx.capture if ctx else None), f'GET {model_url} (actor)')
            photo = ''
            if model:
                last_model_sel = model['sel']
                raw = first_attr(model['sel'], '(//div[contains(@class,"model-contr-colone")]//*[@src]/@src)[1]')
                photo = (absolute_url(raw, site.base_url)) if raw else ''
            actors.append(ActorResult(name=name, photo_url=photo))

        release_date = fallback_date or None
        m = _FULLTITLE_RE.search(url)
        if last_model_sel is not None and m:
            full_title = m.group(1)
            raw = first_text(last_model_sel, f'//a[contains(@href,"{full_title}")]//div[contains(@class,"fsdate")]')
            release_date = iso_date(raw) or (fallback_date or None)

        return LoadedScene(
            url=url,
            site=site,
            scene_date=fallback_date or None,
            capture=ctx.capture if ctx else None,
            sel=loaded['sel'],
            html=loaded['html'],
            extra=_SmtExtra(actors=actors, release_date=release_date),
        )

    def _extra(self, scene: LoadedScene) -> _SmtExtra:
        return scene.extra if isinstance(scene.extra, _SmtExtra) else _SmtExtra()

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = first_text(scene.sel, '//h1')

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = first_text(scene.sel, '//div[h2]').replace('Read More ...Read Less', '').strip()

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = self._extra(scene).release_date or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        genres: list[str] = []
        category_text = scene.sel.xpath('string((//div[contains(@class,"amp-category")])[1])').get() or ''
        for line in category_text.split('\n'):
            g = line.strip()
            if g and g not in genres:
                genres.append(g)
        cast = len(self._extra(scene).actors)
        if cast == 2:
            genres.append('Threesome')
        elif cast == 3:
            genres.append('Foursome')
        elif cast > 3:
            genres.append('Orgy')
        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.actors = self._extra(scene).actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        images: list[str] = []
        for raw in scene.sel.xpath('//div[contains(@class,"amp-vis-mobile")]//*[@src]/@src').getall():
            raw = (raw or '').strip()
            if not raw:
                continue
            abs_url = absolute_url(raw, scene.site.base_url)
            if abs_url not in images:
                images.append(abs_url)
        metadata.raw_image_urls = images
