from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Porndoe Premium'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/search.en.html?q={query}'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Chicas Loca', host='mamacitaz.com'),
    PROVIDER.site('Carne Del Mercado', host='mamacitaz.com'),
    PROVIDER.site('La Cochonne', host='amateureuro.com'),
    PROVIDER.site('Crowd Bondage', host='forbondage.com'),
    PROVIDER.site('Tu Venganza', host='mamacitaz.com'),
    PROVIDER.site('Los Consoladores', host='vipsexvault.com'),
    PROVIDER.site('Trans Bella', host='transbella.com'),
    PROVIDER.site('Her Big Ass', host='mamacitaz.com'),
    PROVIDER.site('Fucked in Traffic', host='vipsexvault.com'),
    PROVIDER.site('Las Folladoras', host='amateureuro.com'),
    PROVIDER.site('Badtime Stories', host='forbondage.com'),
    PROVIDER.site('Exposed Casting', host='vipsexvault.com'),
    PROVIDER.site('Porndoepedia', host='vipsexvault.com'),
    PROVIDER.site('Casting Francais', host='amateureuro.com'),
    PROVIDER.site('Special Feet Force', host='forbondage.com'),
    PROVIDER.site('Trans Taboo', host='transbella.com'),
    PROVIDER.site('Operacion Limpieza', host='mamacitaz.com'),
    PROVIDER.site('La Novice', host='amateureuro.com'),
    PROVIDER.site('Casting Alla Italiana', host='amateureuro.com'),
    PROVIDER.site('PinUp Sex', host='vipsexvault.com'),
    PROVIDER.site('Hausfrau Ficken', host='amateureuro.com'),
    PROVIDER.site('Deutschland Report', host='amateureuro.com'),
    PROVIDER.site('Reife Swinger', host='amateureuro.com'),
    PROVIDER.site('Scambisti Maturi', host='amateureuro.com'),
    PROVIDER.site('Sextape Germany', host='amateureuro.com'),
    PROVIDER.site('XXX Omas', host='amateureuro.com'),
]
