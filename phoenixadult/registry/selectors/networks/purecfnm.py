from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'PureCFNM'
PROVIDER_CONTENT_TYPE: ContentType = 'actors'
PROVIDER_SEARCH_METHOD: SearchMethod = 'exact'
PROVIDER_SEARCH_NOTES = 'ActressID with Title Search'
PROVIDER_SEARCH_PATH = '/models/{query}.html'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Amateur CFNM', host='amateurcfnm.com'),
    PROVIDER.site('PureCFNM', host='purecfnm.com'),
    PROVIDER.site('CFNMGames', host='cfnmgames.com'),
    PROVIDER.site('Girls Abuse Guys', host='girlsabuseguys.com'),
    PROVIDER.site('Hey Little Dick', host='heylittledick.com'),
    PROVIDER.site('Lady Voyeurs', host='ladyvoyeurs.com'),
]
