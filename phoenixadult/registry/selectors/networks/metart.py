from __future__ import annotations

from phoenixadult.registry.selectors._factory import make_site
from phoenixadult.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'MetArt Network'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/api'


def _site(name: str, host: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path=PROVIDER_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='metart',
    )


METART_SITES: list[SiteInfo] = [
    _site('MetArt', 'www.metart.com'),
    _site('MetArtX', 'www.metartx.com'),
    _site('SexArt', 'www.sexart.com'),
    _site('The Life Erotic', 'www.thelifeerotic.com'),
    _site('VivThomas', 'www.vivthomas.com'),
    _site('Straplezz', 'straplezz.com'),
    _site('Hustler', 'hustler.com'),
    _site('Errotica Archives', 'www.errotica-archives.com'),
    _site('ALS Scan', 'www.alsscan.com'),
    _site('Rylsky Art', 'www.rylskyart.com'),
    _site('Eternal Desire', 'www.eternaldesire.com'),
    _site('Stunning18', 'www.stunning18.com'),
    _site('Love Hairy', 'www.lovehairy.com'),
]
