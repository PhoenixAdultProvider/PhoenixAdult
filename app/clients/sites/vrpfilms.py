from __future__ import annotations

import re

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import append_unique, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text
from app.utils.logging.logger import logger

_HERO_TITLE_XP = '//section[contains(@class,"login-banner") and contains(@class,"parallax")]//h1'
_URL_RE = re.compile(r"""url\(['"]?([^'")]+)['"]?\)""")


def _slugify(title: str) -> str:
    return title.lower().replace(' ', '-').replace('_', ' ')


def _url_from_style(style: str) -> str:
    m = _URL_RE.search(style or '')
    return m.group(1) if m else ''


class VRPFilmsClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        slug = _slugify(ctx.title)
        if not slug:
            return
        base = ctx.site_info.base_url.rstrip('/')
        scene_url = f'{base}{ctx.site_info.search_path}{slug}'
        loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] direct {scene_url}')
        if not loaded:
            return
        raw = first_text(loaded['sel'], _HERO_TITLE_XP)
        if not raw:
            return
        logger.info(ctx.site_info.name, f'VRPFilms direct hit "{raw}" ({scene_url})')
        results.append(
            build_search_result(
                title=raw, scene_url=scene_url, query=ctx.title, search_date=ctx.search_date, cur_id=pack_cur_id([scene_url, ctx.search_date or ''])
            )
        )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        metadata.title = first_text(sel, _HERO_TITLE_XP) or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        metadata.summary = first_text(sel, '//div[contains(@class,"col-md-8") and contains(@class,"text-justify")]') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        if not scene.scene_date:
            return
        metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        raw = first_text(sel, '//div[contains(@class,"single__download") and contains(@class,"tags")]')
        parts: list[str | None] = list(raw.split(','))
        metadata.genres = self.dedup_strings(parts)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        entries: list[ActorResult] = []
        for el in sel.xpath('//a[contains(@class,"starring_contain")]'):
            name = first_text(el, './/div[contains(@class,"col-xs-12") and contains(@class,"video-star-title")]//h3')
            style = first_attr(el, '(.//div[contains(@class,"starring_image")]/@style)[1]')
            entries.append(ActorResult(name=name, photo_url=_url_from_style(style)))
        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        base = scene.site.base_url
        images: list[str] = []

        def push(raw: str) -> None:
            append_unique(images, raw, base)

        bg_style = first_attr(sel, '(//section[contains(@class,"login-banner") and contains(@class,"parallax")]/@style)[1]')
        push(_url_from_style(bg_style))
        for href in sel.xpath('//div[contains(@class,"col-md-12") and contains(@class,"gallery-body")]//div//div//div//a[@href]/@href').getall():
            push(href)
        metadata.art = images
