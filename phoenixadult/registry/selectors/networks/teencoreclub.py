from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'TeenCoreClub'
PROVIDER_BASE_URL = 'https://api.fundorado.com'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = ''

_NAMES = [
    'Analyzed Girls',
    'Ass Teen Mouth',
    'Bang Teen Pussy',
    'Brutal Invasion',
    'Cumoholic Teens',
    'Defiled 18',
    'Double Teamed Teens',
    'Dream Teens HD',
    'Girls Got Cream',
    'Hardcore Youth',
    'Little Hellcat',
    'Make Teen Gape',
    'Nylon Sweeties',
    'Seductive 18',
    'Teen Anal Casting',
    'Teen Drillers',
    'Teens Natural Way',
    'Teens Try Blacks',
    'Spermatino',
    'Teach My Ass',
    'Drilled Chicks',
    'Anal Checkups',
    'Fab Sluts',
    'Jerk-Off Pass',
    'Nylon Spunk Junkies',
    'She Got Six',
    'Spear Teen Pussy',
    'Teen Core Club',
    'Teen Core Zine',
    'Teens Go Porn',
    'We Need New Talents',
    'X Core Club',
    'White Teens Black Cocks',
    'Try Teens',
    'Young Throats',
]

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [PROVIDER.site(n) for n in _NAMES]
