from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site
from phoenixadult.utils.helpers.helpers import load_data

PROVIDER_NAME = 'BellaPass'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = 'Title or Slug'
PROVIDER_SEARCH_PATH = '/search.php?query={query}'

_ALIASES: list[str] = load_data(__file__, 'bellapass_aliases')


def _site(name: str, host: str, aliases: list[str] | None = None) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path=PROVIDER_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        aliases=aliases or [],
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='bellapass',
    )


BELLAPASS_SITES: list[SiteInfo] = [
    _site('BellaPass', 'bellapass.com', _ALIASES),
    _site('Hussie Pass', 'hussiepass.com'),
    _site('Babe Archives', 'babearchives.com'),
    _site('See Him Fuck', 'seehimfuck.com'),
]
