from __future__ import annotations

from phoenixadult.registry.selectors._factory import make_site
from phoenixadult.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'BlurredMedia'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/videos/search?s={query}'


def _site(name: str, host: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path=PROVIDER_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='blurredmedia',
    )


BLURREDMEDIA_SITES: list[SiteInfo] = [
    _site('Sugar Daddy Porn', 'sugardaddyporn.com'),
    _site('Hot Guys Fuck', 'hotguysfuck.com'),
    _site('Bi Guys Fuck', 'biguysfuck.com'),
    _site('Gay Hoopla', 'gayhoopla.com'),
]
