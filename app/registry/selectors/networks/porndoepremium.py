from __future__ import annotations

from app.registry.selectors._factory import make_site
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Porndoe Premium'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/search.en.html?q={query}'


def _site(name: str, base_url: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=base_url,
        search_path=PROVIDER_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='porndoepremium',
    )


PORNDOEPREMIUM_SITES: list[SiteInfo] = [
    _site('Chicas Loca', 'https://mamacitaz.com'),
    _site('Carne Del Mercado', 'https://mamacitaz.com'),
    _site('La Cochonne', 'https://amateureuro.com'),
    _site('Crowd Bondage', 'https://forbondage.com'),
    _site('Tu Venganza', 'https://mamacitaz.com'),
    _site('Los Consoladores', 'https://vipsexvault.com'),
    _site('Trans Bella', 'https://transbella.com'),
    _site('Her Big Ass', 'https://mamacitaz.com'),
    _site('Fucked In Traffic', 'https://vipsexvault.com'),
    _site('Las Folladoras', 'https://amateureuro.com'),
    _site('Badtime Stories', 'https://forbondage.com'),
    _site('Exposed Casting', 'https://vipsexvault.com'),
    _site('Porndoepedia', 'https://vipsexvault.com'),
    _site('Casting Francais', 'https://amateureuro.com'),
    _site('Special Feet Force', 'https://forbondage.com'),
    _site('Trans Taboo', 'https://transbella.com'),
    _site('Operacion Limpieza', 'https://mamacitaz.com'),
    _site('La Novice', 'https://amateureuro.com'),
    _site('Casting Alla Italiana', 'https://amateureuro.com'),
    _site('PinUp Sex', 'https://vipsexvault.com'),
    _site('Hausfrau Ficken', 'https://amateureuro.com'),
    _site('Deutschland Report', 'https://amateureuro.com'),
    _site('Reife Swinger', 'https://amateureuro.com'),
    _site('Scambisti Maturi', 'https://amateureuro.com'),
    _site('Sextape Germany', 'https://amateureuro.com'),
    _site('XXX Omas', 'https://amateureuro.com'),
]
