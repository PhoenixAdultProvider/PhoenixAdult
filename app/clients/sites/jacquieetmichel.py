from __future__ import annotations

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, load_site_json, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text

_ACTORS: dict[str, list[str]] = load_site_json(__file__, 'jacquieetmichel_actors')

_RELEASE_XP = '(//div[contains(@class,"content-detail__infos__row")]//p[contains(@class,"content-detail__description--link")])[2]'


class JacquieEtMichelClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        seen: set[str] = set()

        search_url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {search_url}')
        if loaded:
            for card in loaded['sel'].xpath('//a[contains(@class,"content-card--video")]'):
                title = first_text(card, './/h2[contains(@class,"content-card__title")]')
                href = first_attr(card, '@href')
                if not title or not href:
                    continue
                scene_url = absolute_url(href, ctx.site_info.base_url)
                if scene_url in seen:
                    continue
                seen.add(scene_url)
                date_raw = first_text(card, './/div[contains(@class,"content-card__date")]').replace('Added on', '').strip()
                date = iso_date(date_raw)
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

        if ctx.scene_id:
            scene_url = f'{base}/en/content/{ctx.scene_id}'
            if scene_url not in seen:
                direct = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] directScene {scene_url}')
                title = first_text(direct['sel'], '//h1[contains(@class,"content-detail__title")]') if direct else ''
                if title:
                    results.append(
                        build_search_result(
                            title=title,
                            scene_url=scene_url,
                            query=ctx.title,
                            search_date=ctx.search_date,
                            score=100,
                            cur_id=pack_cur_id([x for x in (scene_url, ctx.search_date) if x]),
                        )
                    )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = first_text(scene.sel, '//h1[contains(@class,"content-detail__title")]') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = first_text(scene.sel, '//div[contains(@class,"content-detail__description")]') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Jacquie Et Michel TV'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = first_text(scene.sel, _RELEASE_XP)
        metadata.release_date = (iso_date(raw) if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        genres: list[str] = []
        for el in scene.sel.xpath('//div[contains(@class,"content-detail__row")]//li[contains(@class,"content-detail__tag")]'):
            g = (el.xpath('normalize-space(.)').get() or '').replace(',', '').strip()
            if g == 'Sodomy':
                g = 'Anal'
            if g and g not in genres:
                genres.append(g)
        if 'French porn' not in genres:
            genres.append('French porn')
        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        for fragment, names in _ACTORS.items():
            if fragment in scene.url:
                metadata.actors = [ActorResult(name=name) for name in names]
                return

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = first_attr(scene.sel, '(//video/@poster)[1]')
        if not raw:
            return
        metadata.raw_image_urls = [absolute_url(raw, scene.site.base_url)]
