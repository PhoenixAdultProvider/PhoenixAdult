from __future__ import annotations

from app.models.scraper_config import ScraperConfig
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Adult Prime'
PROVIDER_BASE_URL = 'https://adultprime.com'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneIdName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/studios/search?type='


def _site(name: str) -> SiteInfo:
    return SiteInfo(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=PROVIDER_BASE_URL,
        search_path=PROVIDER_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_config=ScraperConfig(type='adultprime'),
    )


ADULTPRIME_SITES: list[SiteInfo] = [
    _site('4K CFNM'),
    _site('Adult Prime Originals'),
    _site('Adult Prime'),
    _site('BBvideo'),
    _site('Beauty and the Senior'),
    _site('Bondagettes'),
    _site('Bound Men Wanked'),
    _site('BrasilBimbos'),
    _site('Breed Bus'),
    _site('Club Bang Boys'),
    _site('Club Castings'),
    _site('Club Sweethearts'),
    _site('Cockin'),
    _site('Color Climax'),
    _site('CuckOldest'),
    _site('DaringSex HD'),
    _site('Digital Desire'),
    _site('Dirty Gunther'),
    _site('Dirty Hospital'),
    _site('Distorded'),
    _site('Elegant Raw'),
    _site('Evil Playgrounds'),
    _site('Family Screw'),
    _site('Fan Fuckers'),
    _site('Fixxxion'),
    _site('Fresh POV'),
    _site('Fucking Skinny'),
    _site('Gonzo 2000'),
    _site('Granddadz'),
    _site('GrandMams'),
    _site('GrandParentsX'),
    _site('Group Banged'),
    _site('Group Mams'),
    _site('Group Sex Games'),
    _site('Hollandsche Passie'),
    _site('Interraced'),
    _site('Jim Slip'),
    _site('Laras Playground'),
    _site('Lets Go Bi'),
    _site('Mams Casting'),
    _site('Manalized'),
    _site('Manko 88'),
    _site('Massage Sins'),
    _site('Mature Van'),
    _site('My MILFz'),
    _site('My Sexy Kittens'),
    _site('OldieX'),
    _site('Peep Leek'),
    _site('Perfect 18'),
    _site('Plumperd'),
    _site('Pornstar Classics'),
    _site('Pornstars Live'),
    _site('Prime Lesbian'),
    _site('Raw Euro'),
    _site('Red Light Sex Trips'),
    _site('Retro Raw'),
    _site('Rodox'),
    _site('Salsa XXX'),
    _site('Sensual Heat'),
    _site('Shadow Slaves'),
    _site('Sinful Raw'),
    _site('Sinful Soft'),
    _site('Sinful XXX'),
    _site('Southern Sins'),
    _site('Submissed'),
    _site('Summer Sinners'),
    _site('Swhores'),
    _site('Teenrs'),
    _site('The Pain Files'),
    _site('Tranny Bizarre'),
    _site('UK Flashers'),
    _site('Vintage Classic Porn'),
    _site('VR Teens'),
    _site('Young Busty'),
]
