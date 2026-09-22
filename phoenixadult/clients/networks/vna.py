from __future__ import annotations

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, web_search_urls
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result

STUDIO = 'VNA Network'
_SCENE_ACTORS: dict[str, list[str]] = {'36260': ['Sarah Arabic']}


class VNAClient(Client):
    title_xpath = '(//h1[contains(@class,"customhcolor")])[1]'

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        text = search_data.title.strip()

        candidates: list[str] = []
        if search_data.scene_id:
            candidates.append(base + search_data.site_info.search_path + search_data.scene_id)

        for u in await web_search_urls(text or search_data.title, search_data.site_info):
            if ('videos/' in u or 'galleries/' in u) and '/page/' not in u and u not in candidates:
                candidates.append(u)

        for scene_url, details_page_elements in await self.fetch_candidate_pages(
            candidates, FetchCtx(capture=search_data.capture), lambda scene_url: f'[{search_data.site_info.name}] candidate {scene_url}'
        ):
            if not details_page_elements:
                continue

            title = (details_page_elements['sel'].xpath('(//h1[contains(@class,"customhcolor")])[1]').xpath('string(.)').get() or '').strip()
            if not title:
                continue

            date = iso_date((details_page_elements['sel'].xpath('(//*[contains(@class,"date")])[1]').xpath('string(.)').get() or '').strip())

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=text or search_data.title,
                    display_date=date,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([scene_url]),
                )
            )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    @staticmethod
    def _actors_text(scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        return (details_page_elements.xpath('(//h3[contains(@class,"customhcolor")])[1]').xpath('string(.)').get() or '').strip()

    @staticmethod
    def _genres_text(scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        return (details_page_elements.xpath('(//h4[contains(@class,"customhcolor")])[1]').xpath('string(.)').get() or '').strip()

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        summary = (details_page_elements.xpath('(//*[contains(@class,"customhcolor2")])[1]').xpath('string(.)').get() or '').strip()
        if scene.site.name == 'Kimber Lee Live':
            summary = summary.split("Don't forget to join me")[0].strip()

        if scene.site.name == 'Vicky at Home':
            summary = summary.replace(self._actors_text(scene), '').strip()

        metadata.summary = summary or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.release_date = iso_date((details_page_elements.xpath('(//*[contains(@class,"date")])[1]').xpath('string(.)').get() or '').strip())

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        genres = [genre_name.strip() for genre_name in self._genres_text(scene).split(',') if genre_name.strip()]

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        actors_text = self._actors_text(scene)
        if scene.site.name == 'Vicky at Home':
            actors_text = actors_text.replace(self._genres_text(scene), '')

        actors: list[ActorResult] = []
        for raw in actors_text.replace('\xa0', ' ').split(','):
            actor_name = raw.strip()
            if not actor_name:
                continue

            if actor_name.endswith(' XXX'):
                actor_name = actor_name[:-4]

            actors.append(ActorResult(name=actor_name))

        if scene.site.name == 'Siri':
            actors.append(ActorResult(name='Siri'))

        parts = scene.url.split('/')
        scene_id = parts[-2] if len(parts) >= 2 else ''
        for actor_name in _SCENE_ACTORS.get(scene_id, []):
            actors.append(ActorResult(name=actor_name, gender='female'))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')
        poster = first_attr(details_page_elements, '(//center//img)[1]/@src')
        if not poster:
            return

        abs_url = poster if poster.startswith('http') else f'{base}/{poster}'
        out = [abs_url]
        if 'thumb_1' in abs_url:
            out.append(abs_url.replace('thumb_1', 'thumb_2'))
            out.append(abs_url.replace('thumb_1', 'thumb_3'))

        metadata.art = out
