from __future__ import annotations

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id, slugify
from app.utils.helpers.html_helpers import append_year_param, first_attr, first_text, meta_content

_DIRECTOR = ActorResult(
    name='Petter Hegre',
    photo_url='https://img.discogs.com/TafxhnwJE2nhLodoB6UktY6m0xM=/fit-in/180x264/filters:strip_icc():format(jpeg):mode_rgb():quality(90)/discogs-images/A-2236724-1305622884.jpeg.jpg',
)


class HegreClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')

        # Stage 1 — direct /films/<slug>.
        direct = base + ctx.site_info.search_path.replace('{query}', slugify(ctx.title))
        direct_page = await self.fetch_and_load(direct, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] directScene {direct}')
        if direct_page:
            title = first_text(direct_page['sel'], '//h1')
            if title:
                raw_date = first_text(direct_page['sel'], '//span[contains(@class,"date")]')
                date = iso_date(raw_date) if raw_date else None
                return [
                    build_search_result(
                        title=title,
                        scene_url=direct,
                        query=ctx.title,
                        display_date=date,
                        search_date=ctx.search_date,
                        score=100,
                        cur_id=pack_cur_id([direct]),
                    )
                ]

        # Stage 2 — in-site search with optional year filter.
        search_url = append_year_param(f'{base}/search?q={ctx.encoded}', 'year', year=ctx.year, search_date=ctx.search_date)
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {search_url}')
        if not loaded:
            return []

        results: list[SearchResult] = []
        for card in loaded['sel'].xpath('//div[contains(@class,"item")]'):
            href = first_attr(card, '(.//a/@href)[1]')
            if not href or not ('/films/' in href or '/massage/' in href):
                continue
            scene_url = href if href.startswith('http') else f'{base}{"" if href.startswith("/") else "/"}{href}'
            title = first_attr(card, '(.//img/@alt)[1]')
            if not title:
                continue
            raw_date = first_text(card, '(.//div[contains(@class,"details")]/span)[last()]')
            date = iso_date(raw_date) if raw_date else None
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
        return meta_content(scene.sel, 'og:title') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//div[contains(@class,"record-description-content") and contains(@class,"record-box-content")]')
        if not raw:
            return None
        idx = raw.find('Runtime')
        return raw[:idx].strip() if idx >= 0 else raw

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'Hegre'

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//span[contains(@class,"date")]')
        return iso_date(raw) if raw else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres: list[str] = []
        for a in scene.sel.xpath('//a[contains(@class,"tag")]'):
            g = first_attr(a, 'normalize-space(.)').lower()
            if g and g not in genres:
                genres.append(g)
        count = len(scene.sel.xpath('//a[contains(@class,"record-model")]'))
        if count == 3 and 'Threesome' not in genres:
            genres.append('Threesome')
        elif count == 4 and 'Foursome' not in genres:
            genres.append('Foursome')
        elif count > 4 and 'Orgy' not in genres:
            genres.append('Orgy')
        return genres

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        entries: list[ActorResult] = []
        for a in scene.sel.xpath('//a[contains(@class,"record-model")]'):
            name = first_attr(a, '@title')
            raw = first_attr(a, '(.//img/@src)[1]')
            entries.append(ActorResult(name=name, photo_url=raw.replace('240x', '480x') if raw else ''))
        return self.dedup_people(entries)

    async def fetch_directors(self, scene: LoadedScene) -> list[ActorResult] | None:
        return [_DIRECTOR]

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        raw = meta_content(scene.sel, 'twitter:image')
        if not raw:
            return []
        images: list[str] = []
        small = raw.replace('board-image', 'poster-image').replace('1600x', '640x')
        if small != raw:
            images.append(small)
        large = raw.replace('1600x', '1920x')
        if large not in images:
            images.append(large)
        return images
