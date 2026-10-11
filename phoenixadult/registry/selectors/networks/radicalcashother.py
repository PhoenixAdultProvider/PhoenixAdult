from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Radical Cash Other'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('PurgatoryX', host='purgatoryx.com', search_path='https://tour.purgatoryx.com/search/{query}', sub_group='PurgatoryX'),
    PROVIDER.site('Hitzefrei', host='hitzefrei.com', search_path='https://tour.hitzefrei.com/search/{query}', sub_group='Hitzefrei'),
    PROVIDER.site('Unleashed', host='unleashed.hitzefrei.com', search_path='/search/{query}', sub_group='Hitzefrei'),
    PROVIDER.site('CityCheck', host='citycheck.hitzefrei.com', search_path='/search/{query}', sub_group='Hitzefrei'),
    PROVIDER.site('MILF Hunters', host='milfhunters.hitzefrei.com', search_path='/search/{query}', sub_group='Hitzefrei'),
    PROVIDER.site('Cuff Em All', host='cuffemall.hitzefrei.com', search_path='/search/{query}', sub_group='Hitzefrei'),
    PROVIDER.site('fANALarm', host='fanalarm.hitzefrei.com', search_path='/search/{query}', sub_group='Hitzefrei'),
    PROVIDER.site('Fuck on Arrival', host='fuckonarrival.hitzefrei.com', search_path='/search/{query}', sub_group='Hitzefrei'),
    PROVIDER.site('Family Affairs', host='familyaffairs.hitzefrei.com', search_path='/search/{query}', sub_group='Hitzefrei'),
    PROVIDER.site("Patti's Anal", host='pattisanals.hitzefrei.com', search_path='/search/{query}', sub_group='Hitzefrei'),
    PROVIDER.site('Gonzo Living', host='gonzoliving.com', search_path='https://tour.gonzoliving.com/search/{query}', sub_group='Gonzo Living'),
    PROVIDER.site('Teen Gonzo', host='teengonzo.com', search_path='https://tour.teengonzo.com/search/{query}', sub_group='Gonzo Living'),
    PROVIDER.site('MILF Gonzo', host='milfgonzo.com', search_path='https://tour.milfgonzo.com/search/{query}', sub_group='Gonzo Living'),
    PROVIDER.site(
        'ToughLoveX',
        host='toughlovex.com',
        search_path='https://tour.toughlovex.com/search/{query}',
        sub_group='ToughLoveX',
        search_notes='Actor Name Only or Title Only',
    ),
]
