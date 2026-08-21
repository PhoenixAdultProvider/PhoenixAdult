from __future__ import annotations

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import build_search_result, iso_date, load_data, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_attr

STUDIO = 'Intersec Interactive'
_TAGLINE_FALLBACK = 'Intersex'

_TAGLINES: dict[str, str] = load_data(__file__, 'intersec_taglines')


def _resolve_tagline(link_text: str) -> str:
    hay = link_text.lower()
    for key, label in _TAGLINES.items():
        if key in hay:
            return label

    return _TAGLINE_FALLBACK


class IntersecClient(Client):
    title_xpath = '(//div[contains(@class,"has-text-weight-bold")])[1]'
    summary_xpath = '(//div[contains(@class,"has-text-white-ter")])[3]'

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        scene_url = search_data.search_url()
        search_results = await self.fetch_and_load(scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {scene_url}')
        if not search_results:
            return

        for search_result in search_results['sel'].xpath('//div[contains(@class,"is-multiline")]/div[contains(@class,"column")]'):
            href = first_attr(search_result, '(.//a)[1]/@href')
            title = (search_result.xpath('(.//div[contains(@class,"has-text-weight-bold")])[1]').xpath('string(.)').get() or '').strip()
            if not href or not title:
                continue

            if href.startswith('http'):
                detail_url = href
            else:
                cleaned = href.lstrip('/')
                cleaned = cleaned[4:] if cleaned.startswith('iod/') else cleaned
                detail_url = f'{base}/iod/{cleaned}'

            raw_date = (search_result.xpath('(.//span[contains(@class,"tag")])[1]').xpath('string(.)').get() or '').strip()
            date = iso_date(raw_date) if raw_date else search_data.search_date
            cover = first_attr(search_result, '(.//img)[1]/@src')
            cover_packed = self.encode(cover) if cover else ''

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=detail_url,
                    query=search_data.title,
                    display_date=date,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([detail_url, f'{date or ""}|{cover_packed}']),
                )
            )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _tagline(self, scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        links = details_page_elements.xpath('(//div[contains(@class,"has-text-white-ter")])[1]//a[contains(@class,"is-dark")]')
        if not links:
            return _TAGLINE_FALLBACK

        last = links[-1]
        link_text = f'{last.xpath("string(.)").get() or ""} {last.xpath("@href").get() or ""}'
        return _resolve_tagline(link_text)

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline(scene)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        tag = self._tagline(scene)

        metadata.collections = [tag] if tag else None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (
            details_page_elements.xpath('(//div[contains(@class,"has-text-white-ter")])[1]//span[contains(@class,"is-dark")][1]').xpath('string(.)').get() or ''
        ).strip()
        if date:
            metadata.release_date = iso_date(date)
        else:
            metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres = ['BDSM']
        dark = details_page_elements.xpath('(//div[contains(@class,"has-text-white-ter")])[1]//a[contains(@class,"is-dark")]')
        actor_count = max(0, len(dark) - 1)
        if (group := self.group_genre_for(actor_count)) and group not in genres:
            genres.append(group)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        dark = details_page_elements.xpath('(//div[contains(@class,"has-text-white-ter")])[1]//a[contains(@class,"is-dark")]')
        entries = [ActorResult(name=first_attr(row)) for row in dark[:-1]]

        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector()

        if scene.scene_date and '|' in scene.scene_date:
            cover_b64 = scene.scene_date.split('|', 1)[1]
            if cover_b64:
                try:
                    cover = self.decode(cover_b64)
                except Exception:  # noqa: BLE001 - decode failures are non-fatal
                    cover = ''

                if cover:
                    images.push(cover)

        xpaths = ('//video-js/@poster', '//figure//img/@src')
        for xpath in xpaths:
            for image_url in details_page_elements.xpath(xpath).getall():
                images.push(image_url)

        metadata.art = images.items
