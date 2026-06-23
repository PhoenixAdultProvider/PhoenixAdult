from __future__ import annotations

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id, slugify
from app.utils.helpers.html_helpers import web_search_urls

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
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
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

        results: list[SearchResult] = []
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
        return results

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = scene.sel.xpath('normalize-space((//h1)[1])').get() or ''
        if not raw:
            return None
        return _detail_title_strip(raw) or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('normalize-space((//div[contains(@class,"video_text")])[1])').get() or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'Heavy on Hotties'

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return ['Heavy on Hotties']

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath(f'normalize-space(({_RELEASED_XP})[1])').get() or '').strip()
        if raw:
            return iso_date(raw)
        return (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath('//span[contains(@class,"feature") and contains(@class,"title")]//a[contains(@href,"models")]'):
            name = (el.xpath('normalize-space(.)').get() or '').strip()
            href = (el.xpath('@href').get() or '').strip()
            if not name or not href or name in seen:
                continue
            seen.add(name)
            actor_url = href if href.startswith('http') else f'{base}{"" if href.startswith("/") else "/"}{href}'
            actor_page = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
            photo = ''
            if actor_page:
                raw = (actor_page['sel'].xpath('(//div[h1]//img/@src)[1]').get() or '').strip()
                photo = _lift_scheme(raw) if raw else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []
        for raw in scene.sel.xpath('//video[@poster]/@poster').getall():
            raw = (raw or '').strip()
            if not raw:
                continue
            abs_url = _lift_scheme(raw)
            if abs_url not in images:
                images.append(abs_url)
        return images
