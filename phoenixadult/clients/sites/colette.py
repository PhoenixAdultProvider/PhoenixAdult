from __future__ import annotations

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text, web_search_urls
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result

_GALLERY_FIXES: dict[str, str] = {'The_Perfect_Threesome': 'The_Perfect_Threesome_or_Pussy_Galore'}

_TITLE_XP = '//div[contains(@class,"row") and contains(@class,"info")]//div//h1'
_CAST_XP = '//div[contains(@class,"info")]//h2//a'


def _parse_interchange(raw: str) -> str:
    if not raw:
        return ''

    seg = raw.replace('[', '').replace(']', '').replace(', (small)', '').replace(', (medium)', '').replace(', (large)', '').split(',')
    return seg[2].strip() if len(seg) > 2 else ''


class ColetteClient(Client):
    summary_xpath = '(//div[contains(@class,"info")]//p)[2]'

    def __init__(self) -> None:
        super().__init__({'Cookie': '_warning=True'})

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        candidates: list[str] = [f'{base}/videos/{search_data.title.replace(" ", "_")}']
        for u in await web_search_urls(search_data.title, search_data.site_info, include=['/videos/']):
            if u not in candidates:
                candidates.append(u)

        for scene_url, details_page_elements in await self.fetch_candidate_pages(
            candidates, FetchCtx(capture=search_data.capture), lambda scene_url: f'[{search_data.site_info.name}] candidate {scene_url}'
        ):
            if not details_page_elements:
                continue

            title = first_text(details_page_elements['sel'], _TITLE_XP)
            if not title:
                continue

            date = iso_date(first_text(details_page_elements['sel'], '//h2')) or ''

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=date or None,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
                )
            )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, _TITLE_XP) or ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        if scene.scene_date:
            metadata.release_date = scene.scene_date
            return

        details_page_elements = scene.require_sel()

        metadata.release_date = iso_date(first_text(details_page_elements, '//h2')) or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        count = len(details_page_elements.xpath(_CAST_XP))
        if group := self.group_genre_for(count):
            metadata.genres = [group]

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')

        def extract_photo(sel: Selector) -> str:
            raw = sel.xpath('(//img[contains(@class,"info-img")]/@data-interchange)[1]').get() or ''
            return _parse_interchange(raw)

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath(_CAST_XP):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name and href:
                refs.append((actor_name, href if href.startswith('http') else base + href))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector()

        slug = scene.url.split('/videos/')[-1]
        gallery_path = _GALLERY_FIXES.get(slug, slug)
        gallery_url = scene.url.replace('/videos/', '/galleries/').replace(slug, gallery_path)
        gallery_page_elements = await self.fetch_and_load(gallery_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] gallery')

        pages = [p['sel'] for p in (gallery_page_elements,) if p] + [details_page_elements]
        for page in pages:
            for src in page.xpath('//div[contains(@class,"gallery-item")]//a//img/@src').getall():
                images.push((src or '').strip())

            for src in page.xpath('//div[contains(@class,"video-tour")]//a//img/@src').getall():
                images.push((src or '').strip())

            for image_url in page.xpath('//div[contains(@class,"widescreen")]//img/@data-interchange').getall():
                images.push(_parse_interchange(image_url or ''))

            for image_url in page.xpath('//div[contains(@class,"columns")]/img/@data-interchange').getall():
                images.push(_parse_interchange(image_url or ''))

        metadata.art = images.items
