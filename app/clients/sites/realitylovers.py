from __future__ import annotations

import httpx2

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text
from app.utils.logging.logger import logger


def _srcset_entry(srcset: str, index: int, drop_chars: int) -> str:
    parts = srcset.split(',')
    if index >= len(parts) or index < -len(parts):
        return ''
    entry = parts[index]
    return entry[:-drop_chars].strip().replace('https', 'http') if entry else ''


class RealityLoversClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        search_url = base + ctx.site_info.search_path
        try:
            r = await self.http.post(
                search_url,
                json={'sortBy': 'MOST_RELEVANT', 'searchQuery': ctx.title, 'videoView': 'MEDIUM'},
                headers={'Content-Type': 'application/json'},
            )
            contents = (r.json() or {}).get('contents', [])
        except (httpx2.HTTPError, ValueError) as err:
            logger.warn(ctx.site_info.name, f'search POST threw: {err}')
            return []

        results: list[SearchResult] = []
        for c in contents:
            title = (c.get('title') or '').strip()
            uri = (c.get('videoUri') or '').strip()
            if not title or not uri:
                continue
            scene_url = uri if uri.startswith('http') else f'{base}/{uri.lstrip("/")}'
            date = iso_date(c['released']) if c.get('released') else None
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
        return first_text(scene.sel, '//h1[contains(@class,"video-detail-name")]') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//p[@itemprop="description"]').replace('…', '').replace('Read more', '')
        return ' '.join(raw.split()) or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//span[contains(@class,"videoClip__Details-infoValue")]')
        return (iso_date(raw) if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [first_attr(a, 'normalize-space(.)').lower() for a in scene.sel.xpath('//span[@itemprop="keywords"]//a')]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        for el in scene.sel.xpath('//span[@itemprop="actors"]//a'):
            name = first_attr(el, 'normalize-space(.)')
            if not name:
                continue
            photo = ''
            href = first_attr(el, '@href')
            if href:
                loaded = await self.fetch_and_load(href, FetchCtx(capture=scene.capture), f'GET {href} (actor)')
                srcset = (loaded['sel'].xpath('(//img[contains(@class,"girlDetails-posterImage")]/@srcset)[1]').get() or '') if loaded else ''
                if srcset:
                    photo = _srcset_entry(srcset, 1, 3)
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []
        for data_big in scene.sel.xpath('//img[contains(@class,"videoClip__Details--galleryItem")]/@data-big').getall():
            data_big = (data_big or '').strip()
            if not data_big:
                continue
            url = _srcset_entry(data_big, len(data_big.split(',')) - 1, 6)
            if url and url not in images:
                images.append(url)
        return images
