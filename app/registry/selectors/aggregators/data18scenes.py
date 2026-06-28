from __future__ import annotations

from app.registry.selectors._factory import make_site
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Data18 Porn Database'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''


def _data18_scenes(name: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url='https://data18.com',
        search_path='/sys/live.php?index=&key=',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='data18scenes',
        cache_layout='aggregator',  # database spanning many studios+sub-sites → data18scenes/<studio>/<sub-site>
    )


DATA18SCENES_SITES: list[SiteInfo] = [_data18_scenes('Data18 Scenes'), _data18_scenes('Data18 Movie Scene')]
