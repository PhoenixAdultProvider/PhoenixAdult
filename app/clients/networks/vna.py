from __future__ import annotations

from urllib.parse import urlparse

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr
from app.utils.searchengines import SearchOptions, web_search, web_search_available

STUDIO = 'VNA Network'
_SCENE_ACTORS: dict[str, list[str]] = {'36260': ['Sarah Arabic']}


class VNAClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        text = ctx.title.strip()

        candidates: list[str] = []
        if ctx.scene_id:
            candidates.append(base + ctx.site_info.search_path + ctx.scene_id)

        if web_search_available():
            host = urlparse(ctx.site_info.base_url).netloc
            for u in await web_search(SearchOptions(query=text or ctx.title, site=host, num=10)):
                if ('videos/' in u or 'galleries/' in u) and '/page/' not in u and u not in candidates:
                    candidates.append(u)

        results: list[SearchResult] = []
        for scene_url in candidates:
            loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] candidate {scene_url}')
            if not loaded:
                continue
            title = (loaded['sel'].xpath('(//h1[contains(@class,"customhcolor")])[1]').xpath('string(.)').get() or '').strip()
            if not title:
                continue
            date = iso_date((loaded['sel'].xpath('(//*[contains(@class,"date")])[1]').xpath('string(.)').get() or '').strip())
            results.append(
                build_search_result(
                    title=title, scene_url=scene_url, query=text or ctx.title, display_date=date, search_date=ctx.search_date, cur_id=pack_cur_id([scene_url])
                )
            )
        return results

    # ── Detail field hooks ────────────────────────────────────────────────────

    @staticmethod
    def _actors_text(scene: LoadedScene) -> str:
        assert scene.sel is not None
        return (scene.sel.xpath('(//h3[contains(@class,"customhcolor")])[1]').xpath('string(.)').get() or '').strip()

    @staticmethod
    def _genres_text(scene: LoadedScene) -> str:
        assert scene.sel is not None
        return (scene.sel.xpath('(//h4[contains(@class,"customhcolor")])[1]').xpath('string(.)').get() or '').strip()

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//h1[contains(@class,"customhcolor")])[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        summary = (scene.sel.xpath('(//*[contains(@class,"customhcolor2")])[1]').xpath('string(.)').get() or '').strip()
        if scene.site.name == 'Kimber Lee Live':
            summary = summary.split("Don't forget to join me")[0].strip()
        if scene.site.name == 'Vicky at Home':
            summary = summary.replace(self._actors_text(scene), '').strip()
        return summary or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return iso_date((scene.sel.xpath('(//*[contains(@class,"date")])[1]').xpath('string(.)').get() or '').strip())

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        genres = [g.strip() for g in self._genres_text(scene).split(',') if g.strip()]
        return genres or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        actors_text = self._actors_text(scene)
        if scene.site.name == 'Vicky at Home':
            actors_text = actors_text.replace(self._genres_text(scene), '')

        actors: list[ActorResult] = []
        for raw in actors_text.replace('\xa0', ' ').split(','):
            name = raw.strip()
            if not name:
                continue
            if name.endswith(' XXX'):
                name = name[:-4]
            actors.append(ActorResult(name=name))
        if scene.site.name == 'Siri':
            actors.append(ActorResult(name='Siri'))

        parts = scene.url.split('/')
        scene_id = parts[-2] if len(parts) >= 2 else ''
        for name in _SCENE_ACTORS.get(scene_id, []):
            actors.append(ActorResult(name=name, gender='female'))
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        poster = first_attr(scene.sel, '(//center//img)[1]/@src')
        if not poster:
            return None
        abs_url = poster if poster.startswith('http') else f'{base}/{poster}'
        out = [abs_url]
        if 'thumb_1' in abs_url:
            out.append(abs_url.replace('thumb_1', 'thumb_2'))
            out.append(abs_url.replace('thumb_1', 'thumb_3'))
        return out
