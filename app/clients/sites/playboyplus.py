from __future__ import annotations

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text


class PlayboyPlusClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        scene_url = f'{base}{ctx.site_info.search_path}/{ctx.encoded}'
        loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {scene_url}')
        if not loaded:
            return
        page_poster = (loaded['sel'].xpath('(//img[contains(@class,"image")]/@data-src)[1]').get() or '').split('?')[0]

        for card in loaded['sel'].xpath('//div[@id="search-results-gallery"]//li[contains(@class,"item")]'):
            title = first_text(card, './/h3[contains(@class,"title")]')
            href = first_attr(card, '(.//a[contains(@class,"cardLink")]/@href)[1]')
            if not title or not href:
                continue
            url = href if href.startswith('http') else base + href
            date = iso_date(first_text(card, './/p[contains(@class,"date")]'))
            results.append(
                build_search_result(
                    title=title, scene_url=url, query=ctx.title, display_date=date, search_date=ctx.search_date, cur_id=pack_cur_id([url, page_poster])
                )
            )

    # ── Context loader (curID packs the search-card poster) ───────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        pipe = payload.find('|')
        url = payload[:pipe] if pipe >= 0 else payload
        poster = payload[pipe + 1 :].strip() if pipe >= 0 else ''
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture if ctx else None), f'[{site.name}] detail {url}')
        if not loaded:
            return None
        return LoadedScene(url=url, site=site, capture=ctx.capture if ctx else None, sel=loaded['sel'], html=loaded['html'], extra={'poster': poster})

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = first_text(scene.sel, '//h1[contains(@class,"title")]')

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = first_text(scene.sel, '//p[contains(@class,"description-truncated")]').replace('...', '')

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Playboy Plus'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//p[contains(@class,"date")]')
        metadata.release_date = (iso_date(raw, '%B %d, %Y') if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.genres = ['Glamour']

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        entries = [ActorResult(name=a.xpath('normalize-space(.)').get() or '') for a in scene.sel.xpath('//p[contains(@class,"contributorName")]//a')]
        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        coll = self.image_collector(lambda raw: absolute_url(raw.split('?')[0].strip(), scene.site.base_url))
        coll['push'](scene.extra.get('poster', '') if isinstance(scene.extra, dict) else '')
        coll['push'](scene.sel.xpath('(//img[contains(@class,"image")]/@data-src)[1]').get() or '')
        for raw in scene.sel.xpath('//section[contains(@class,"gallery")]//img[contains(@class,"image")]/@data-src').getall():
            coll['push'](raw)
        metadata.art = coll['list']
