from __future__ import annotations

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text, web_search_urls

_GALLERY_FIXES: dict[str, str] = {'The_Perfect_Threesome': 'The_Perfect_Threesome_or_Pussy_Galore'}

_TITLE_XP = '//div[contains(@class,"row") and contains(@class,"info")]//div//h1'
_CAST_XP = '//div[contains(@class,"info")]//h2//a'


def _parse_interchange(raw: str) -> str:
    if not raw:
        return ''
    seg = raw.replace('[', '').replace(']', '').replace(', (small)', '').replace(', (medium)', '').replace(', (large)', '').split(',')
    return seg[2].strip() if len(seg) > 2 else ''


class ColetteClient(Client):
    def __init__(self) -> None:
        super().__init__({'Cookie': '_warning=True'})

    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        candidates: list[str] = [f'{base}/videos/{ctx.title.replace(" ", "_")}']
        for u in await web_search_urls(ctx.title, ctx.site_info, include=['/videos/']):
            if u not in candidates:
                candidates.append(u)

        for scene_url in candidates:
            loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] candidate {scene_url}')
            if not loaded:
                continue
            title = first_text(loaded['sel'], _TITLE_XP)
            if not title:
                continue
            date = iso_date(first_text(loaded['sel'], '//h2')) or ''
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=ctx.title,
                    display_date=date or None,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
                )
            )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = first_text(scene.sel, _TITLE_XP) or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = first_text(scene.sel, '(//div[contains(@class,"info")]//p)[2]') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Colette'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        if scene.scene_date:
            metadata.release_date = scene.scene_date
            return
        assert scene.sel is not None
        metadata.release_date = iso_date(first_text(scene.sel, '//h2')) or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        count = len(scene.sel.xpath(_CAST_XP))
        if count == 3:
            metadata.genres = ['Threesome']
        elif count == 4:
            metadata.genres = ['Foursome']
        elif count > 4:
            metadata.genres = ['Orgy']

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        links: list[tuple[str, str]] = []
        for el in scene.sel.xpath(_CAST_XP):
            name = first_attr(el, 'normalize-space(.)')
            href = first_attr(el, '@href')
            if name and href:
                links.append((name, href))

        actors: list[ActorResult] = []
        for name, href in links:
            url = href if href.startswith('http') else scene.site.base_url.rstrip('/') + href
            page = await self.fetch_and_load(url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
            interchange = (page['sel'].xpath('(//img[contains(@class,"info-img")]/@data-interchange)[1]').get() or '') if page else ''
            actors.append(ActorResult(name=name, photo_url=_parse_interchange(interchange)))
        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        images: list[str] = []

        def add(u: str) -> None:
            if u and u not in images:
                images.append(u)

        slug = scene.url.split('/videos/')[-1]
        gallery_path = _GALLERY_FIXES.get(slug, slug)
        gallery_url = scene.url.replace('/videos/', '/galleries/').replace(slug, gallery_path)
        gallery = await self.fetch_and_load(gallery_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] gallery')

        pages = [p['sel'] for p in (gallery,) if p] + [scene.sel]
        for page in pages:
            for src in page.xpath('//div[contains(@class,"gallery-item")]//a//img/@src').getall():
                add((src or '').strip())
            for src in page.xpath('//div[contains(@class,"video-tour")]//a//img/@src').getall():
                add((src or '').strip())
            for raw in page.xpath('//div[contains(@class,"widescreen")]//img/@data-interchange').getall():
                add(_parse_interchange(raw or ''))
            for raw in page.xpath('//div[contains(@class,"columns")]/img/@data-interchange').getall():
                add(_parse_interchange(raw or ''))
        metadata.raw_image_urls = images
