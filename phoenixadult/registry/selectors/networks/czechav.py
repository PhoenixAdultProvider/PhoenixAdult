from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Czech Authentic Videos'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = 'Title only and Date Add'
PROVIDER_SEARCH_PATH = '/tour/search/?q={query}'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Czech Amateurs', host='czechamateurs.com'),
    PROVIDER.site('Czech Bangbus', host='czechbangbus.com'),
    PROVIDER.site('Czech Bitch', host='czechbitch.com'),
    PROVIDER.site('Czech Cabins', host='czechcabins.com'),
    PROVIDER.site('Czech Couples', host='czechcouples.com'),
    PROVIDER.site('Czech Dungeon', host='czechdungeon.com'),
    PROVIDER.site('Czech Estrogenolit', host='czechestrogenolit.com'),
    PROVIDER.site('Czech Experiment', host='czechexperiment.com'),
    PROVIDER.site('Czech Fantasy', host='czechfantasy.com'),
    PROVIDER.site('Czech First Video', host='czechfirstvideo.com'),
    PROVIDER.site('Czech Game', host='czechgame.com'),
    PROVIDER.site('Czech Gangbang', host='czechgangbang.com'),
    PROVIDER.site('Czech Garden Party', host='czechgardenparty.com'),
    PROVIDER.site('Czech Harem', host='czechharem.com'),
    PROVIDER.site('Czech Home Orgy', host='czechhomeorgy.com'),
    PROVIDER.site('Czech Lesbians', host='czechlesbians.com'),
    PROVIDER.site('Czech Massage', host='czechmassage.com'),
    PROVIDER.site('Czech Mega Swingers', host='czechmegaswingers.com'),
    PROVIDER.site('Czech Orgasm', host='czechorgasm.com'),
    PROVIDER.site('Czech Parties', host='czechparties.com'),
    PROVIDER.site('Czech Pawn Shop', host='czechpawnshop.com'),
    PROVIDER.site('Czech Pool', host='czechpool.com'),
    PROVIDER.site('Czech Sauna', host='czechsauna.com'),
    PROVIDER.site('Czech Sharking', host='czechsharking.com'),
    PROVIDER.site('Czech Snooper', host='czechsnooper.com'),
    PROVIDER.site('Czech Solarium', host='czechsolarium.com'),
    PROVIDER.site('Czech Spy', host='czechspy.com'),
    PROVIDER.site('Czech Streets', host='czechstreets.com'),
    PROVIDER.site('Czech Super Models', host='czechsupermodels.com'),
    PROVIDER.site('Czech Taxi', host='czechtaxi.com'),
    PROVIDER.site('Czech Toilets', host='czechtoilets.com'),
    PROVIDER.site('Czech Twins', host='czechtwins.com'),
    PROVIDER.site('Czech Wife Swap', host='czechwifeswap.com'),
    PROVIDER.site('Czech Casting', host='czechcasting.com'),
]
