from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Teen Mega World'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/search.php?query={query}'
PROVIDER_BASE_URL = 'https://teenmegaworld.net'

PROVIDER = Provider.from_headers(__name__)


SITES: list[SiteInfo] = [
    PROVIDER.site('Teen Mega World'),
    PROVIDER.site('18 First Sex'),
    PROVIDER.site('ATMovs'),
    PROVIDER.site('About Girls Love'),
    PROVIDER.site('Anal-Angels', base_url='https://anal-angels.com'),
    PROVIDER.site('Anal-Beauty', base_url='https://anal-beauty.com'),
    PROVIDER.site('Beauty 4K', base_url='https://beauty4k.com'),
    PROVIDER.site('BeautyAngels', base_url='https://beauty-angels.com'),
    PROVIDER.site('Coeds Reality'),
    PROVIDER.site('Creampie Angels', base_url='https://creampie-angels.com'),
    PROVIDER.site('Dirty Coach', base_url='https://dirty-coach.com'),
    PROVIDER.site('Dirty Doctor', base_url='https://dirty-doctor.com'),
    PROVIDER.site('El Porno Latino'),
    PROVIDER.site('ExGfBox'),
    PROVIDER.site('First BGG', base_url='https://firstbgg.com'),
    PROVIDER.site('Fuck Studies', base_url='https://fuckstudies.com'),
    PROVIDER.site('Gag N Gape', base_url='https://gag-n-gape.com'),
    PROVIDER.site('Home Teen Vids'),
    PROVIDER.site('Home Toy Teens'),
    PROVIDER.site('Lolly Hardcore', base_url='https://lollyhardcore.com'),
    PROVIDER.site('No Boring', base_url='https://noboring.com'),
    PROVIDER.site('Nubile Girls HD', base_url='https://nubilegirlshd.com'),
    PROVIDER.site('NylonsX'),
    PROVIDER.site('Old-n-Young', base_url='https://old-n-young.com'),
    PROVIDER.site('Private Teen Video'),
    PROVIDER.site('Solo Teen Girls', base_url='https://soloteengirls.net'),
    PROVIDER.site('Squirting Virgin'),
    PROVIDER.site('Teen Sex Mania', base_url='https://teensexmania.com'),
    PROVIDER.site('Teen Stars Only'),
    PROVIDER.site('Teens 3 Some'),
    PROVIDER.site('TmwVRnet'),
    PROVIDER.site('Tricky Masseur', base_url='https://trickymasseur.com'),
    PROVIDER.site('WOW Orgasms'),
    PROVIDER.site('Watch Me Fucked'),
    PROVIDER.site('X-Angels', base_url='https://x-angels.com'),
    PROVIDER.site('Teen Sex Movs', base_url='https://teensexmovs.com'),
    PROVIDER.site('Raw Couples', base_url='https://rawcouples.com'),
    PROVIDER.site('TMWPOV', base_url='https://tmwpov.com'),
]
