from __future__ import annotations

from app.models.scraper_config import ScraperConfig
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Teen Mega World'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
_SEARCH_PATH = '/search.php?query={query}'
_SHARED_HOST = 'teenmegaworld.net'


def _site(name: str, host: str = _SHARED_HOST) -> SiteInfo:
    return SiteInfo(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path=_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_config=ScraperConfig(type='teenmegaworld'),
    )


TEENMEGAWORLD_SITES: list[SiteInfo] = [
    _site('Teen Mega World'),
    _site('18 First Sex'),
    _site('ATMovs'),
    _site('About Girls Love'),
    _site('Anal-Angels', 'anal-angels.com'),
    _site('Anal-Beauty', 'anal-beauty.com'),
    _site('Beauty 4K', 'beauty4k.com'),
    _site('BeautyAngels', 'beauty-angels.com'),
    _site('Coeds Reality'),
    _site('Creampie Angels', 'creampie-angels.com'),
    _site('Dirty Coach', 'dirty-coach.com'),
    _site('Dirty Doctor', 'dirty-doctor.com'),
    _site('el Porno Latino'),
    _site('ExGfBox'),
    _site('First BGG', 'firstbgg.com'),
    _site('Fuck Studies', 'fuckstudies.com'),
    _site('Gag N Gape', 'gag-n-gape.com'),
    _site('Home Teen Vids'),
    _site('Home Toy Teens'),
    _site('Lolly Hardcore', 'lollyhardcore.com'),
    _site('No Boring', 'noboring.com'),
    _site('Nubile Girls HD', 'nubilegirlshd.com'),
    _site('NylonsX'),
    _site('Old-n-Young', 'old-n-young.com'),
    _site('Private Teen Video'),
    _site('Solo Teen Girls', 'soloteengirls.net'),
    _site('Squirting Virgin'),
    _site('Teen Sex Mania', 'teensexmania.com'),
    _site('Teen Stars Only'),
    _site('Teens 3 Some'),
    _site('TmwVRnet'),
    _site('Tricky Masseur', 'trickymasseur.com'),
    _site('WOW Orgasms'),
    _site('Watch Me Fucked'),
    _site('X-Angels', 'x-angels.com'),
    _site('Teen Sex Movs', 'teensexmovs.com'),
    _site('Raw Couples', 'rawcouples.com'),
    _site('TMWPOV', 'tmwpov.com'),
]
