from __future__ import annotations

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import build_search_result, iso_date, join_url, pack_cur_id, slugify
from app.utils.helpers.html_helpers import first_attr, web_search_urls

_RELEASED_XP = '//span[contains(@class,"released") and contains(@class,"title")]//strong'


def _search_title_strip(raw: str) -> str:
    after = raw.split(':', 1)[1] if ':' in raw else raw
    return after.strip().strip('"').strip()


def _detail_title_strip(raw: str) -> str:
    stripped = _search_title_strip(raw)
    return stripped.split(' - ')[-1].strip().strip('"')


def _lift_scheme(url: str) -> str:
    if not url:
        return ''
    return f'https:{url}' if url.startswith('//') else url


class HeavyOnHottiesClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        words = ctx.title.strip().split()

        variants = [slugify(ctx.title)]
        if len(words) > 1:
            variants.append('-'.join(w.lower() for w in words[1:]))
        if len(words) > 2:
            tail = words[2:]
            if tail and tail[0].lower() == 'and':
                tail = tail[3:]
            joined = ' '.join(tail).replace("'", '')
            if joined:
                variants.append(slugify(joined))

        candidates: list[str] = []
        for slug in variants:
            url = f'{base}/movies/{slug}'
            if url not in candidates:
                candidates.append(url)
        for u in await web_search_urls(ctx.title, ctx.site_info, include=['/movies/'], exclude=['/page-']):
            if u not in candidates:
                candidates.append(u)

        for scene_url in candidates:
            page = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] candidate {scene_url}')
            if not page:
                continue
            raw_h1 = page['sel'].xpath('normalize-space((//h1)[1])').get() or ''
            if not raw_h1:
                continue
            title = _search_title_strip(raw_h1)
            raw_date = (page['sel'].xpath(f'normalize-space(({_RELEASED_XP})[1])').get() or '').strip()
            date = iso_date(raw_date) if raw_date else ctx.search_date
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

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = scene.sel.xpath('normalize-space((//h1)[1])').get() or ''
        if not raw:
            return
        metadata.title = _detail_title_strip(raw) or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = first_attr(scene.sel, 'normalize-space((//div[contains(@class,"video_text")])[1])') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Heavy on Hotties'

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = ['Heavy on Hotties']

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = (scene.sel.xpath(f'normalize-space(({_RELEASED_XP})[1])').get() or '').strip()
        if raw:
            metadata.release_date = iso_date(raw)
            return
        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath('//span[contains(@class,"feature") and contains(@class,"title")]//a[contains(@href,"models")]'):
            name = first_attr(el, 'normalize-space(.)')
            href = first_attr(el, '@href')
            if not name or not href or name in seen:
                continue
            seen.add(name)
            actor_url = join_url(href, base)
            actor_page = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
            photo = ''
            if actor_page:
                raw = first_attr(actor_page['sel'], '(//div[h1]//img/@src)[1]')
                photo = _lift_scheme(raw) if raw else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        coll = self.image_collector(_lift_scheme)
        for raw in scene.sel.xpath('//video[@poster]/@poster').getall():
            coll['push']((raw or '').strip())
        metadata.raw_image_urls = coll['list']
