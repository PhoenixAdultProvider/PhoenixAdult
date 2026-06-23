from __future__ import annotations

import json
from pathlib import Path

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_text

STUDIO = 'Naughty America'
TAGLINE = "Tonight's Girlfriend"
MAX_PAGES = 4
FULL_PAGE_THRESHOLD = 9

_DATA = Path(__file__).parent / '_data' / 'json'
_FIXED_GENRES: list[str] = json.loads((_DATA / 'tonightsgirlfriend_fixed_genres.json').read_text(encoding='utf-8'))
_GREY_XP = '//p[contains(@class,"grey-performers")]'


def _https(src: str) -> str:
    return src if src.startswith('http') else f'https:{src}'


class TonightsGirlfriendClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        slug = ctx.title.lower().split('and ')[0].strip().replace(' ', '-')
        if not slug:
            return []
        base = ctx.site_info.base_url.rstrip('/')
        path = ctx.site_info.search_path
        results: list[SearchResult] = []
        seen: set[str] = set()

        for page in range(1, MAX_PAGES + 1):
            search_url = f'{base}{path}{slug}/?p={page}'
            loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search page {page} "{ctx.title}"')
            if not loaded:
                break
            rows = list(loaded['sel'].xpath('//div[contains(@class,"panel-body")]'))
            for row in rows:
                actor_names = [n for n in (a.xpath('normalize-space(.)').get() or '' for a in row.xpath('.//span[contains(@class,"scene-actors")]//a')) if n]
                if not actor_names:
                    continue
                href = (row.xpath('(.//a/@href)[1]').get() or '').strip()
                if not href:
                    continue
                scene_url = (href if href.startswith('http') else absolute_url(href, base)).split('?')[0]
                if scene_url in seen:
                    continue
                seen.add(scene_url)
                raw_date = first_text(row, './/span[contains(@class,"scene-date")]')
                date = iso_date(raw_date) if raw_date else None
                results.append(
                    build_search_result(
                        title=', '.join(actor_names),
                        scene_url=scene_url,
                        query=actor_names[0],
                        display_date=date,
                        search_date=ctx.search_date,
                        cur_id=pack_cur_id([scene_url, date or '']),
                    )
                )
            if len(rows) < FULL_PAGE_THRESHOLD:
                break
        return results

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        names = self._linked_actor_names(scene)
        return ', '.join(names) if names else None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//p[contains(@class,"scene-description")]') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return TAGLINE

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [TAGLINE]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        if not scene.scene_date:
            return None
        return iso_date(scene.scene_date) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        genres = list(_FIXED_GENRES)
        linked = self._linked_actor_names(scene)
        male = self._male_actor_names(scene, linked)
        if len(linked) + len(male) == 3:
            genres.append('Threesome')
            genres.append('BGG' if len(linked) == 2 else 'BBG')
        return genres

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for a in scene.sel.xpath(f'{_GREY_XP}//a'):
            name = (a.xpath('normalize-space(.)').get() or '').strip()
            href = (a.xpath('@href').get() or '').strip()
            if not name or name in seen:
                continue
            seen.add(name)
            photo = ''
            actor_url = href.split('?')[0]
            if actor_url:
                abs_url = actor_url if actor_url.startswith('http') else absolute_url(actor_url, scene.site.base_url)
                page = await self.fetch_and_load(abs_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
                if page:
                    src = (page['sel'].xpath('(//div[contains(@class,"performer-details")]//img/@src)[1]').get() or '').strip()
                    if src:
                        photo = _https(src)
            actors.append(ActorResult(name=name, photo_url=photo))

        for name in self._male_actor_names(scene, [a.name for a in actors]):
            if name not in seen:
                seen.add(name)
                actors.append(ActorResult(name=name))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        src = (scene.sel.xpath('(//img[contains(@class,"playcard")]/@src)[1]').get() or '').strip()
        if not src:
            return []
        poster = _https(src)
        out = [poster]
        head = poster.split('scene/image')[0].split('scene/horizontal')[0]
        vertical = f'{head}scene/vertical/390x590cdynamic.jpg'
        if vertical != poster:
            out.append(vertical)
        return out

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _linked_actor_names(self, scene: LoadedScene) -> list[str]:
        assert scene.sel is not None
        names: list[str] = []
        for a in scene.sel.xpath(f'{_GREY_XP}//a'):
            n = (a.xpath('normalize-space(.)').get() or '').strip()
            if n and n not in names:
                names.append(n)
        return names

    def _male_actor_names(self, scene: LoadedScene, linked: list[str]) -> list[str]:
        assert scene.sel is not None
        nodes = scene.sel.xpath(_GREY_XP)
        info = (nodes[0].xpath('normalize-space(.)').get() or '').strip() if nodes else ''
        if not info:
            return []
        for name in linked:
            info = info.replace(f'{name},', '').strip()
        out: list[str] = []
        for part in info.split(','):
            t = part.strip()
            if t and t not in out:
                out.append(t)
        return out
