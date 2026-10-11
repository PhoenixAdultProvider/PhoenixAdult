from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'PervCity'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = 'Title or Actor'
PROVIDER_SEARCH_PATH = '/search.php?query={query}'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Anal Overdose', host='analoverdose.com'),
    PROVIDER.site('Banging Beauties', host='www.bangingbeauties.com'),
    PROVIDER.site('Chocolate BJs', host='www.chocolatebjs.com'),
    PROVIDER.site('Oral Overdose', host='www.oraloverdose.com'),
    PROVIDER.site('Up Her Asshole', host='www.upherasshole.com'),
    PROVIDER.site('Perv City', host='www.pervcity.com'),
    PROVIDER.site('DP Diva', host='www.dpdiva.com', search_path=''),
]
