from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = 'Czech Authentic Videos'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = 'Title only and Date Add'
PROVIDER_SEARCH_PATH = '/tour/search/?q={query}'


def _site(name: str, host: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path=PROVIDER_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='czechav',
    )


SITES: list[SiteInfo] = [
    _site('Czech Amateurs', 'czechamateurs.com'),
    _site('Czech Bangbus', 'czechbangbus.com'),
    _site('Czech Bitch', 'czechbitch.com'),
    _site('Czech Cabins', 'czechcabins.com'),
    _site('Czech Couples', 'czechcouples.com'),
    _site('Czech Dungeon', 'czechdungeon.com'),
    _site('Czech Estrogenolit', 'czechestrogenolit.com'),
    _site('Czech Experiment', 'czechexperiment.com'),
    _site('Czech Fantasy', 'czechfantasy.com'),
    _site('Czech First Video', 'czechfirstvideo.com'),
    _site('Czech Game', 'czechgame.com'),
    _site('Czech Gangbang', 'czechgangbang.com'),
    _site('Czech Garden Party', 'czechgardenparty.com'),
    _site('Czech Harem', 'czechharem.com'),
    _site('Czech Home Orgy', 'czechhomeorgy.com'),
    _site('Czech Lesbians', 'czechlesbians.com'),
    _site('Czech Massage', 'czechmassage.com'),
    _site('Czech Mega Swingers', 'czechmegaswingers.com'),
    _site('Czech Orgasm', 'czechorgasm.com'),
    _site('Czech Parties', 'czechparties.com'),
    _site('Czech Pawn Shop', 'czechpawnshop.com'),
    _site('Czech Pool', 'czechpool.com'),
    _site('Czech Sauna', 'czechsauna.com'),
    _site('Czech Sharking', 'czechsharking.com'),
    _site('Czech Snooper', 'czechsnooper.com'),
    _site('Czech Solarium', 'czechsolarium.com'),
    _site('Czech Spy', 'czechspy.com'),
    _site('Czech Streets', 'czechstreets.com'),
    _site('Czech Super Models', 'czechsupermodels.com'),
    _site('Czech Taxi', 'czechtaxi.com'),
    _site('Czech Toilets', 'czechtoilets.com'),
    _site('Czech Twins', 'czechtwins.com'),
    _site('Czech Wife Swap', 'czechwifeswap.com'),
    _site('Czech Casting', 'czechcasting.com'),
]
