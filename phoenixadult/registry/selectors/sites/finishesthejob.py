from __future__ import annotations

from phoenixadult.registry.selectors._factory import make_site
from phoenixadult.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Finishes The Job'
PROVIDER_BASE_URL = 'https://www.finishesthejob.com'
PROVIDER_SEARCH_PATH = '/search?search={query}'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = 'Date Add'


def _finishes_the_job(name: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=PROVIDER_BASE_URL,
        search_path=PROVIDER_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='finishesthejob',
    )


FINISHESTHEJOB_SITES: list[SiteInfo] = [
    _finishes_the_job('Mano Job'),
    _finishes_the_job('The Dick Suckers'),
    _finishes_the_job('Mister POV'),
]
