from __future__ import annotations

import re
from typing import Any

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result

_VIDEO_TYPES = ['masturbation', 'photoshoot', 'interview', 'girl-girl action', 'pov lapdance']
_SCENEID_RE = re.compile(r'([^0-9]+)([0-9-]+)')
_THUMB_RE = re.compile(r'graphics/videos/(.+)\.jpg')


def _row_date(row: Any) -> str:
    return re.sub(r'Date:\s*', '', (row.xpath('(.//span[contains(@class,"videodate")])[1]').xpath('string(.)').get() or ''), flags=re.IGNORECASE).strip()


class AlsAngelsClient(Client):
    def __init__(self) -> None:
        super().__init__({'Cookie': 'age_verified=true'})

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        search_results = await self.fetch_and_load(
            f'{base}/dailyvideos.html', FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] dailyvideos'
        )
        if not search_results:
            return

        if search_data.search_date:

            def match_row(row: Any) -> bool:
                return iso_date(_row_date(row)) == search_data.search_date
        else:
            m = re.match(rf'^(.+?)\s+({"|".join(_VIDEO_TYPES)})\b', search_data.title.lower(), re.IGNORECASE)
            if not m:
                return

            model, vtype = m.group(1).strip(), m.group(2).strip()

            def match_row(row: Any) -> bool:
                name = (row.xpath('(.//h2[contains(@class,"videomodel")])[1]').xpath('string(.)').get() or '').lower()
                t = (row.xpath('(.//span[contains(@class,"videotype")])[1]').xpath('string(.)').get() or '').lower()
                return model in name and vtype in t

        for search_result in search_results['sel'].xpath('//tr'):
            if not match_row(search_result):
                continue

            thumb = first_attr(search_result, '(.//td[contains(@class,"videothumbnail")]//a//img)[1]/@src')
            mid = _THUMB_RE.search(thumb)
            if not mid:
                continue

            scene_id = mid.group(1)
            release_date = iso_date(_row_date(search_result)) or ''
            model = re.sub(
                r'Models?:\s*', '', (search_result.xpath('(.//h2[contains(@class,"videomodel")])[1]').xpath('string(.)').get() or ''), flags=re.IGNORECASE
            ).strip()
            vtype = re.sub(
                r'Video Type:\s*', '', (search_result.xpath('(.//span[contains(@class,"videotype")])[1]').xpath('string(.)').get() or ''), flags=re.IGNORECASE
            ).strip()

            results.append(
                build_search_result(
                    title=f'{model} {vtype} {release_date}'.strip(),
                    scene_url=f'{base}/profiles/{scene_id}',
                    query=search_data.title,
                    site=search_data.site_info,
                    cur_id=pack_cur_id([scene_id, release_date]),
                    search_date=search_data.search_date,
                    display_date=release_date or None,
                    score=100,
                )
            )

    # ── Context Loader ────────────────────────────────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        base = site.base_url.rstrip('/')
        pipe = payload.find('|')
        scene_id = payload[:pipe] if pipe >= 0 else payload
        scene_date = payload[pipe + 1 :].strip() if pipe >= 0 else ''

        id_match = _SCENEID_RE.search(scene_id)
        if not id_match:
            return None

        model_id, scene_num = id_match.group(1), id_match.group(2)

        model_page_elements = await self.fetch_and_load(
            f'{base}/profiles/{model_id}.html', FetchCtx(capture=ctx.capture if ctx else None, use_bypass=site.use_bypass), f'[{site.name}] profile {model_id}'
        )
        if not model_page_elements:
            return None

        row = None
        for table_row in model_page_elements['sel'].xpath('//tr'):
            if scene_date and iso_date(_row_date(table_row)) == scene_date:
                row = table_row
                break

        if row is None:
            return None

        model_name = re.sub(
            r'ALSAngels\.com\s*-\s*', '', (model_page_elements['sel'].xpath('(//title)[1]').xpath('string(.)').get() or ''), flags=re.IGNORECASE
        ).strip()
        return LoadedScene(
            url=f'{base}/profiles/{model_id}.html',
            site=site,
            scene_date=scene_date or None,
            capture=ctx.capture if ctx else None,
            sel=model_page_elements['sel'],
            html=model_page_elements['html'],
            extra={'model_id': model_id, 'scene_num': scene_num, 'scene_date': scene_date, 'row': row, 'model_name': model_name},
        )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _ex(self, scene: LoadedScene) -> dict[str, Any]:
        return scene.extra or {}

    def _subject(self, scene: LoadedScene) -> str:
        row = self._ex(scene)['row']
        return re.sub(
            r'Video Type:\s*', '', (row.xpath('(.//span[contains(@class,"videotype")])[1]').xpath('string(.)').get() or ''), flags=re.IGNORECASE
        ).strip()

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        ex = self._ex(scene)
        num = re.match(r'\d+', ex['scene_num'])
        n = int(num.group()) if num else 0

        metadata.title = f'{ex["model_name"]} #{n}: {self._subject(scene)}'

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        row = self._ex(scene)['row']

        metadata.summary = (row.xpath('(.//span[contains(@class,"videodescription")])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = self._ex(scene).get('scene_date') or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        subject = self._subject(scene)

        metadata.genres = [subject] if subject else []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        ex = self._ex(scene)
        base = scene.site.base_url.rstrip('/')
        photo = first_attr(details_page_elements, '(//*[@id="modelbioheadshot"]//img)[1]/@src')
        if photo.startswith('..'):
            photo = photo.replace('..', base)

        metadata.actors = [ActorResult(name=ex['model_name'], photo_url=photo, gender='female')] if ex.get('model_name') else []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        row = self._ex(scene)['row']
        base = scene.site.base_url.rstrip('/')
        images = self.image_collector(lambda image: image.replace('..', base) if image.startswith('..') else image)
        for src in row.xpath('.//td[contains(@class,"videothumbnail")]//img/@src').getall():
            images.push(src)

        for href in row.xpath('.//td[contains(@class,"videothumbnail")]//a/@href').getall():
            images.push(href)

        metadata.art = images.items
