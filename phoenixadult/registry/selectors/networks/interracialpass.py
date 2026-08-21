from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = 'InterracialPass'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''


def _site(name: str, host: str, search_path: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path=search_path,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='interracialpass',
    )


SITES: list[SiteInfo] = [
    _site('Interracial Pass', 'www.interracialpass.com', '/t1/search.php?query={query}'),
    _site('Backroom Casting Couch', 'backroomcastingcouch.com', '/search.php?query={query}'),
    _site('BBC Surprise', 'bbcsurprise.com', '/search.php?query={query}'),
    _site('Exploited College Girls', 'exploitedcollegegirls.com', '/search.php?query={query}'),
    _site('I Kiss Girls', 'www.ikissgirls.com', '/search.php?query={query}'),
    _site('HushPass', 'hushpass.com', '/t1/search.php?query={query}'),
    _site('Hot MILFs Fuck', 'hotmilfsfuck.com', '/search.php?query={query}'),
]
