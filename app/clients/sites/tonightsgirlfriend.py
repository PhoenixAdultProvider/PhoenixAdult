from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id, strip_query
from app.utils.helpers.html_helpers import first_attr, first_text

STUDIO = 'Naughty America'
TAGLINE = "Tonight's Girlfriend"
MAX_PAGES = 4
FULL_PAGE_THRESHOLD = 9

_FIXED_GENRES: list[str] = ['Girlfriend Experience', 'Hotel', 'Pornstar', 'Pornstar Experience']
_GREY_XP = '//p[contains(@class,"grey-performers")]'


def _https(src: str) -> str:
    return src if src.startswith('http') else f'https:{src}'


class TonightsGirlfriendClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        slug = ctx.title.lower().split('and ')[0].strip().replace(' ', '-')
        if not slug:
            return
        base = ctx.site_info.base_url.rstrip('/')
        path = ctx.site_info.search_path

        async def fetch_rows(page: int) -> list[Any] | None:
            url = f'{base}{path}{slug}/?p={page}'
            loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search page {page} "{ctx.title}"')
            return list(loaded['sel'].xpath('//div[contains(@class,"panel-body")]')) if loaded else None

        def build_row(row: Any) -> SearchResult | None:
            actor_names = [n for n in (a.xpath('normalize-space(.)').get() or '' for a in row.xpath('.//span[contains(@class,"scene-actors")]//a')) if n]
            if not actor_names:
                return None
            href = first_attr(row, '(.//a/@href)[1]')
            if not href:
                return None
            scene_url = (absolute_url(href, base)).split('?')[0]
            raw_date = first_text(row, './/span[contains(@class,"scene-date")]')
            date = iso_date(raw_date) if raw_date else None
            return build_search_result(
                title=', '.join(actor_names),
                scene_url=scene_url,
                query=actor_names[0],
                display_date=date,
                search_date=ctx.search_date,
                cur_id=pack_cur_id([scene_url, date or '']),
            )

        results.extend(await self.paginate_search(fetch_rows=fetch_rows, build_row=build_row, max_pages=MAX_PAGES, full_page=FULL_PAGE_THRESHOLD))

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        names = self._linked_actor_names(scene)
        metadata.title = ', '.join(names) if names else ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        metadata.summary = first_text(sel, '//p[contains(@class,"scene-description")]') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = TAGLINE

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [TAGLINE]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        if not scene.scene_date:
            return
        metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        genres = list(_FIXED_GENRES)
        linked = self._linked_actor_names(scene)
        male = self._male_actor_names(scene, linked)
        if len(linked) + len(male) == 3:
            genres.append('Threesome')
            genres.append('BGG' if len(linked) == 2 else 'BBG')
        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for a in sel.xpath(f'{_GREY_XP}//a'):
            name = first_attr(a, 'normalize-space(.)')
            href = first_attr(a, '@href')
            if not name or name in seen:
                continue
            seen.add(name)
            photo = ''
            actor_url = strip_query(href)
            if actor_url:
                abs_url = absolute_url(actor_url, scene.site.base_url)
                page = await self.fetch_and_load(abs_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
                if page:
                    src = first_attr(page['sel'], '(//div[contains(@class,"performer-details")]//img/@src)[1]')
                    if src:
                        photo = _https(src)
            actors.append(ActorResult(name=name, photo_url=photo))

        for name in self._male_actor_names(scene, [a.name for a in actors]):
            if name not in seen:
                seen.add(name)
                actors.append(ActorResult(name=name))
        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        src = first_attr(sel, '(//img[contains(@class,"playcard")]/@src)[1]')
        if not src:
            return
        poster = _https(src)
        out = [poster]
        head = poster.split('scene/image')[0].split('scene/horizontal')[0]
        vertical = f'{head}scene/vertical/390x590cdynamic.jpg'
        if vertical != poster:
            out.append(vertical)
        metadata.art = out

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _linked_actor_names(self, scene: LoadedScene) -> list[str]:
        sel = scene.require_sel()
        names = self.dedup_strings([first_attr(a, 'normalize-space(.)') for a in sel.xpath(f'{_GREY_XP}//a')])
        return names

    def _male_actor_names(self, scene: LoadedScene, linked: list[str]) -> list[str]:
        sel = scene.require_sel()
        nodes = sel.xpath(_GREY_XP)
        info = first_attr(nodes[0], 'normalize-space(.)') if nodes else ''
        if not info:
            return []
        for name in linked:
            info = info.replace(f'{name},', '').strip()
        out = self.dedup_strings([part.strip() for part in info.split(',')])
        return out
