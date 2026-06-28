from __future__ import annotations

import re

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_text

STUDIO = 'Xev Unleashed'
_XEV_PHOTO = 'https://xevunleashed.com/content//contentthumbs/00/01/1-set-2x.jpg'
_NON_ALNUM_RE = re.compile(r'[^a-z0-9]+')
_AVAILDATE_XP = '(//span[contains(@class,"availdate")]/text())[1]'


def _slugify(s: str) -> str:
    return _NON_ALNUM_RE.sub('-', s.lower().replace("'", '')).strip('-')


class XevUnleashedClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        results: list[SearchResult] = []
        seen: set[str] = set()

        slug = _slugify(ctx.title)
        if slug:
            direct_url = f'{base}/updates/{slug}.html'
            direct = await self.fetch_and_load(direct_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] direct {direct_url}')
            if direct:
                raw_title = first_text(direct['sel'], '//span[contains(@class,"update_title")]')
                if raw_title:
                    date_raw = (direct['sel'].xpath(_AVAILDATE_XP).get() or '').strip()
                    date = (iso_date(date_raw, '%m/%d/%Y') or iso_date(date_raw)) if date_raw else None
                    seen.add(direct_url.lower())
                    results.append(
                        build_search_result(
                            title=raw_title,
                            scene_url=direct_url,
                            query=ctx.title,
                            display_date=date,
                            search_date=ctx.search_date,
                            cur_id=pack_cur_id([direct_url, date or '']),
                        )
                    )

        search_url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if loaded:
            for row in loaded['sel'].xpath('//div[contains(@class,"updateItem")]'):
                raw_title = first_text(row, './/h4')
                href = (row.xpath('(.//a/@href)[1]').get() or '').strip()
                if not raw_title or not href:
                    continue
                scene_url = absolute_url(href, ctx.site_info.base_url)
                if scene_url.lower() in seen:
                    continue
                seen.add(scene_url.lower())
                date_raw = first_text(row, './/p//span')
                date = iso_date(date_raw) if date_raw else None
                results.append(
                    build_search_result(
                        title=raw_title,
                        scene_url=scene_url,
                        query=ctx.title,
                        display_date=date,
                        search_date=ctx.search_date,
                        cur_id=pack_cur_id([scene_url, date or '']),
                    )
                )
        return results

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//span[contains(@class,"update_title")]') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//span[contains(@class,"latest_update_description")]') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [STUDIO]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        date_raw = (scene.sel.xpath(_AVAILDATE_XP).get() or '').strip()
        if date_raw:
            parsed = iso_date(date_raw, '%m/%d/%Y') or iso_date(date_raw)
            if parsed:
                return parsed
        if scene.scene_date:
            return iso_date(scene.scene_date) or scene.scene_date
        return None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//span[contains(@class,"update_tags")]//a')]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        actors = [ActorResult(name='Xev Bellringer', photo_url=_XEV_PHOTO)]
        keywords = (scene.sel.xpath('(//meta[@name="keywords"]/@content)[1]').get() or '').lower()
        if 'princess leia' in keywords:
            actors.append(ActorResult(name='Princess Leia'))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        images: list[str] = []
        for src in scene.sel.xpath('//div[contains(@class,"update_image")]//img/@src0_4x').getall():
            raw = (src or '').strip()
            if not raw:
                continue
            abs_url = absolute_url(raw, base)
            if abs_url not in images:
                images.append(abs_url)
        return images
