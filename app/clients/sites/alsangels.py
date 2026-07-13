from __future__ import annotations

import re
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr

_VIDEO_TYPES = ['masturbation', 'photoshoot', 'interview', 'girl-girl action', 'pov lapdance']
# Unanchored (matches the legacy re.search): scene IDs may have a trailing
# non-numeric suffix, e.g. "stormrose006-nn" -> model "stormrose", num "006-".
# The TS port anchored this with ^...$, which dropped those scenes.
_SCENEID_RE = re.compile(r'([^0-9]+)([0-9-]+)')
_THUMB_RE = re.compile(r'graphics/videos/(.+)\.jpg')


def _row_date(row: Any) -> str:
    return re.sub(r'Date:\s*', '', (row.xpath('(.//span[contains(@class,"videodate")])[1]').xpath('string(.)').get() or ''), flags=re.IGNORECASE).strip()


class AlsAngelsClient(Client):
    def __init__(self) -> None:
        super().__init__({'Cookie': 'age_verified=true'})

    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        loaded = await self.fetch_and_load(f'{base}/dailyvideos.html', FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] dailyvideos')
        if not loaded:
            return

        if ctx.search_date:

            def match_row(row: Any) -> bool:
                return iso_date(_row_date(row)) == ctx.search_date
        else:
            m = re.match(rf'^(.+?)\s+({"|".join(_VIDEO_TYPES)})\b', ctx.title.lower(), re.IGNORECASE)
            if not m:
                return
            model, vtype = m.group(1).strip(), m.group(2).strip()

            def match_row(row: Any) -> bool:
                name = (row.xpath('(.//h2[contains(@class,"videomodel")])[1]').xpath('string(.)').get() or '').lower()
                t = (row.xpath('(.//span[contains(@class,"videotype")])[1]').xpath('string(.)').get() or '').lower()
                return model in name and vtype in t

        for row in loaded['sel'].xpath('//tr'):
            if not match_row(row):
                continue
            thumb = first_attr(row, '(.//td[contains(@class,"videothumbnail")]//a//img)[1]/@src')
            mid = _THUMB_RE.search(thumb)
            if not mid:
                continue
            scene_id = mid.group(1)
            release_date = iso_date(_row_date(row)) or ''
            model = re.sub(
                r'Models?:\s*', '', (row.xpath('(.//h2[contains(@class,"videomodel")])[1]').xpath('string(.)').get() or ''), flags=re.IGNORECASE
            ).strip()
            vtype = re.sub(
                r'Video Type:\s*', '', (row.xpath('(.//span[contains(@class,"videotype")])[1]').xpath('string(.)').get() or ''), flags=re.IGNORECASE
            ).strip()
            results.append(
                SearchResult(
                    title=f'{model} {vtype} {release_date}'.strip(),
                    scene_url=f'{base}/profiles/{scene_id}',
                    cur_id=pack_cur_id([scene_id, release_date]),
                    release_date=release_date or ctx.search_date or None,
                    display_date=release_date or None,
                    score=100,
                )
            )

    # ── Context loader ────────────────────────────────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        base = site.base_url.rstrip('/')
        pipe = payload.find('|')
        scene_id = payload[:pipe] if pipe >= 0 else payload
        scene_date = payload[pipe + 1 :].strip() if pipe >= 0 else ''

        id_match = _SCENEID_RE.search(scene_id)
        if not id_match:
            return None
        model_id, scene_num = id_match.group(1), id_match.group(2)

        loaded = await self.fetch_and_load(
            f'{base}/profiles/{model_id}.html', FetchCtx(capture=ctx.capture if ctx else None), f'[{site.name}] profile {model_id}'
        )
        if not loaded:
            return None

        row = None
        for el in loaded['sel'].xpath('//tr'):
            if scene_date and iso_date(_row_date(el)) == scene_date:
                row = el
                break
        if row is None:
            return None

        model_name = re.sub(r'ALSAngels\.com\s*-\s*', '', (loaded['sel'].xpath('(//title)[1]').xpath('string(.)').get() or ''), flags=re.IGNORECASE).strip()
        return LoadedScene(
            url=f'{base}/profiles/{model_id}.html',
            site=site,
            scene_date=scene_date or None,
            capture=ctx.capture if ctx else None,
            sel=loaded['sel'],
            html=loaded['html'],
            extra={'model_id': model_id, 'scene_num': scene_num, 'scene_date': scene_date, 'row': row, 'model_name': model_name},
        )

    def _ex(self, scene: LoadedScene) -> dict[str, Any]:
        return scene.extra or {}

    def _subject(self, scene: LoadedScene) -> str:
        row = self._ex(scene)['row']
        return re.sub(
            r'Video Type:\s*', '', (row.xpath('(.//span[contains(@class,"videotype")])[1]').xpath('string(.)').get() or ''), flags=re.IGNORECASE
        ).strip()

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        ex = self._ex(scene)
        num = re.match(r'\d+', ex['scene_num'])
        n = int(num.group()) if num else 0
        metadata.title = f'{ex["model_name"]} #{n}: {self._subject(scene)}'

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        row = self._ex(scene)['row']
        metadata.summary = (row.xpath('(.//span[contains(@class,"videodescription")])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = self._ex(scene).get('scene_date') or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        subject = self._subject(scene)
        metadata.genres = [subject] if subject else []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        ex = self._ex(scene)
        base = scene.site.base_url.rstrip('/')
        photo = first_attr(scene.sel, '(//*[@id="modelbioheadshot"]//img)[1]/@src')
        if photo.startswith('..'):
            photo = photo.replace('..', base)
        metadata.actors = [ActorResult(name=ex['model_name'], photo_url=photo, gender='female')] if ex.get('model_name') else []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        row = self._ex(scene)['row']
        base = scene.site.base_url.rstrip('/')
        coll = self.image_collector(lambda u: u.replace('..', base) if u.startswith('..') else u)
        for src in row.xpath('.//td[contains(@class,"videothumbnail")]//img/@src').getall():
            coll['push'](src)
        for href in row.xpath('.//td[contains(@class,"videothumbnail")]//a/@href').getall():
            coll['push'](href)
        images: list[str] = coll['list']
        metadata.art = images or []
