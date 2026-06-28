from __future__ import annotations

import re
from urllib.parse import quote

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_text

_LEADING_ID_RE = re.compile(r'^(\d+)\s*(.*)$')
_GENRES_LIST_FIRST_A = '//div[contains(@class,"genres-list")]//a'


class AnalVidsClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        m = _LEADING_ID_RE.match(ctx.title.strip())
        source_id = m.group(1) if m else None
        text = (m.group(2).strip() if m else ctx.title.strip()) or ctx.title.strip()

        data = await self.fetch_json(
            f'{base}/api/autocomplete/search?q={quote(text)}',
            FetchCtx(capture=ctx.capture),
            label=f'[{ctx.site_info.name}] AnalVids search "{text}"',
        )

        results: list[SearchResult] = []
        for term in (data or {}).get('terms', []):
            if term.get('type') != 'scene' or not term.get('url') or not term.get('name'):
                continue
            url = term['url']
            scene_url = absolute_url(url, ctx.site_info.base_url)
            direct_hit = source_id is not None and str(term.get('source_id', '')) == source_id
            results.append(
                build_search_result(
                    title=term['name'].strip(),
                    scene_url=scene_url,
                    query=text,
                    search_date=ctx.search_date,
                    score=100 if direct_hit else None,
                    cur_id=pack_cur_id([scene_url]),
                )
            )
        return results

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//h1[contains(@class,"watch__title")]')
        return raw.split('featuring')[0].strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"text-mob-more")]') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'AnalVids'

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, _GENRES_LIST_FIRST_A) or None

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        tagline = first_text(scene.sel, _GENRES_LIST_FIRST_A)
        return [tagline] if tagline else None

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//i[contains(@class,"bi-calendar3")]')
        return iso_date(raw) or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [
            a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//div[contains(@class,"genres-list")]//a[contains(@href,"/genre/")]')
        ]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        links: list[tuple[str, str]] = []
        seen: set[str] = set()
        for el in scene.sel.xpath('//a[contains(@href,"/model/")]'):
            href = (el.xpath('@href').get() or '').strip()
            name = (el.xpath('normalize-space(.)').get() or '').strip()
            if not name or not href or 'forum' in href or name in seen:
                continue
            seen.add(name)
            links.append((name, href))

        actors: list[ActorResult] = []
        for name, href in links:
            url = absolute_url(href, scene.site.base_url)
            loaded = await self.fetch_and_load(url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
            photo = (loaded['sel'].xpath('(//div[contains(@class,"model")]//img/@src)[1]').get() or '').strip() if loaded else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors

    async def fetch_directors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        directors: list[ActorResult] = []
        seen: set[str] = set()

        def add(name: str) -> None:
            n = name.strip()
            if n and n not in seen:
                seen.add(n)
                directors.append(ActorResult(name=n))

        tagline = first_text(scene.sel, _GENRES_LIST_FIRST_A)
        if tagline in ('Giorgio Grandi', "Giorgio's Lab"):
            add('Giorgio Grandi')
        for el in scene.sel.xpath('//p[contains(@class,"director")]//a'):
            add(el.xpath('normalize-space(.)').get() or '')
        return directors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        poster = (scene.sel.xpath('(//div[contains(@class,"watch__video")]//video/@data-poster)[1]').get() or '').strip()
        return [poster] if poster else []
