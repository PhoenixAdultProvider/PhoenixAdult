from __future__ import annotations

from urllib.parse import urlparse

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr
from app.utils.logging.best_effort import best_effort
from app.utils.searchengines import SearchOptions, web_search, web_search_available

STUDIO = 'New Sensations'


class NewSensationsClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        stem = ctx.site_info.base_url.rstrip('/') + ctx.site_info.search_path

        title_no_actors = ' '.join(ctx.title.split(' ')[2:])
        if title_no_actors.startswith('and '):
            title_no_actors = ' '.join(title_no_actors.split(' ')[3:])
        slug = title_no_actors.replace(' ', '-')

        candidates: list[str] = [f'{stem}updates/{slug}.html', f'{stem}updates/{slug}-.html', f'{stem}updates/{slug}-4k.html', f'{stem}dvds/{slug}.html']
        seen = set(candidates)
        if web_search_available():
            with best_effort(ctx.site_info.name, 'webSearch'):
                found = await web_search(SearchOptions(query=ctx.title, site=urlparse(ctx.site_info.base_url).netloc, num=10))
                for url in found:
                    is_scene = '/updates/' in url or '/dvds/' in url or '/scenes/' in url
                    is_tour = '/tour_ns/' in url or '/tour_famxxx/' in url
                    if is_scene and is_tour and url not in seen:
                        seen.add(url)
                        candidates.append(url)

        for scene_url in candidates:
            loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] {scene_url}')
            if not loaded:
                continue
            title = (
                loaded['sel']
                .xpath('(//div[@class="indScene"]/h1 | //div[@class="indSceneDVD"]/h1 | //div[@class="indScene"]/h2 | //div[@class="indSceneDVD"]/h2)[1]')
                .xpath('string(.)')
                .get()
                or ''
            ).strip()
            if not title:
                continue
            results.append(build_search_result(title=title, scene_url=scene_url, query=ctx.title, search_date=ctx.search_date, cur_id=pack_cur_id([scene_url])))

    # ── Detail field hooks ────────────────────────────────────────────────────

    def _is_dvd(self, scene: LoadedScene) -> bool:
        return '/dvds/' in scene.url

    def _dvd_tagline(self, scene: LoadedScene) -> str | None:
        if not self._is_dvd(scene):
            return None
        sel = scene.require_sel()
        return (sel.xpath('(//div[@class="indSceneDVD"]/h1)[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        xp = '(//div[@class="indSceneDVD"]/h1)[1]' if self._is_dvd(scene) else '(//div[@class="indScene"]/h1 | //div[@class="indScene"]/h2)[1]'
        metadata.title = (sel.xpath(xp).xpath('string(.)').get() or '').strip()

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        metadata.summary = (sel.xpath('(//div[@class="description"]/h2)[1]').xpath('string(.)').get() or '').replace('Description:', '').strip()

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._dvd_tagline(scene)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        if self._is_dvd(scene):
            dvd = self._dvd_tagline(scene)
            metadata.collections = [dvd] if dvd else None
            return
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        if self._is_dvd(scene):
            raw = (sel.xpath('(//div[@class="datePhotos"])[1]').xpath('string(.)').get() or '').replace('RELEASED:', '').strip()
        else:
            raw = (sel.xpath('(//div[@class="sceneDateP"]/span)[1]').xpath('string(.)').get() or '').strip()
        metadata.release_date = (iso_date(raw) if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        genres: list[str] = []
        if self._is_dvd(scene):
            for a in sel.xpath('//div[@class="textLink"]//a'):
                g = first_attr(a, 'normalize-space(.)')
                if g and g not in genres:
                    genres.append(g)
        else:
            cast = len(sel.xpath('//div[@class="sceneTextLink"]//span[@class="tour_update_models"]/a'))
            if (group := self.group_genre_for(cast)) and group not in genres:
                genres.append(group)
        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        base = scene.site.base_url
        xp = '//span[@class="tour_update_models"]/a' if self._is_dvd(scene) else '//div[@class="sceneTextLink"]//span[@class="tour_update_models"]/a'
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in sel.xpath(xp):
            name = first_attr(el, 'normalize-space(.)')
            if not name or name in seen:
                continue
            seen.add(name)
            photo = ''
            href = first_attr(el, '@href')
            if href:
                page = await self.fetch_and_load(absolute_url(href, base), None, f'GET {href} (actor)')
                raw = first_attr(page['sel'], '(//div[@class="modelBioPic"]/img)[1]/@src0_3x') if page else ''
                if raw:
                    photo = absolute_url(raw, base)
            actors.append(ActorResult(name=name, photo_url=photo))
        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        coll = self.image_collector(lambda raw: absolute_url(raw, scene.site.base_url))
        coll['push'](sel.xpath('(//span[@id="trailer_thumb"]//img)[1]/@src').get())
        if self._is_dvd(scene):
            for src in sel.xpath('//div[@class="videoBlock"]//img/@src0_3x').getall():
                coll['push'](src)
        images: list[str] = coll['list']
        metadata.art = images
