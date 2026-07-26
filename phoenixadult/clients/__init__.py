from __future__ import annotations

from phoenixadult.clients.aggregators.archive import ArchiveClient
from phoenixadult.clients.aggregators.data18empire import Data18EmpireClient
from phoenixadult.clients.aggregators.data18movies import Data18MoviesClient
from phoenixadult.clients.aggregators.data18scenes import Data18ScenesClient
from phoenixadult.clients.aggregators.javbus import JavBusClient
from phoenixadult.clients.aggregators.javdatabase import JAVDatabaseClient
from phoenixadult.clients.aggregators.javlibrary import JavLibraryClient
from phoenixadult.clients.aggregators.metadataapi import MetadataAPIClient
from phoenixadult.clients.aggregators.pornbox import PornboxClient
from phoenixadult.clients.aggregators.project1service import Project1ServiceClient
from phoenixadult.clients.base import Client
from phoenixadult.clients.networks.abbywinters import AbbyWintersClient
from phoenixadult.clients.networks.adultempirecash import AdultEmpireCashClient
from phoenixadult.clients.networks.adultprime import AdultPrimeClient
from phoenixadult.clients.networks.badoinkvr import BadoinkVrClient
from phoenixadult.clients.networks.bang import BangClient
from phoenixadult.clients.networks.bellapass import BellaPassClient
from phoenixadult.clients.networks.bellesa import BellesaClient
from phoenixadult.clients.networks.blurredmedia import BlurredMediaClient
from phoenixadult.clients.networks.caramelcash import CaramelCashClient
from phoenixadult.clients.networks.cherrypimps import CherryPimpsClient
from phoenixadult.clients.networks.couplescinema import CouplesCinemaClient
from phoenixadult.clients.networks.czechav import CzechAVClient
from phoenixadult.clients.networks.czechvr import CzechVRClient
from phoenixadult.clients.networks.derangeddollars import DerangedDollarsClient
from phoenixadult.clients.networks.dirtyflix import DirtyFlixClient
from phoenixadult.clients.networks.dirtyharddrive import DirtyHardDriveClient
from phoenixadult.clients.networks.evolvedfights import EvolvedFightsClient
from phoenixadult.clients.networks.fakings import FAKingsClient
from phoenixadult.clients.networks.femdomempire import FemdomEmpireClient
from phoenixadult.clients.networks.ftv import FTVClient
from phoenixadult.clients.networks.fuckyoucash import FuckYouCashClient
from phoenixadult.clients.networks.fuelvirtual import FuelVirtualClient
from phoenixadult.clients.networks.fullpornnetwork import FullPornNetworkClient
from phoenixadult.clients.networks.gammaent import GammaEntClient
from phoenixadult.clients.networks.gammaentother import GammaEntOtherClient
from phoenixadult.clients.networks.gasm import GasmClient
from phoenixadult.clients.networks.grooby import GroobyClient
from phoenixadult.clients.networks.hightechvr import HighTechVRClient
from phoenixadult.clients.networks.interracialpass import InterracialPassClient
from phoenixadult.clients.networks.intersec import IntersecClient
from phoenixadult.clients.networks.julesjordan import JulesJordanClient
from phoenixadult.clients.networks.karups import KarupsClient
from phoenixadult.clients.networks.kellymadison import KellyMadisonClient
from phoenixadult.clients.networks.killergram import KillergramClient
from phoenixadult.clients.networks.kink import KinkClient
from phoenixadult.clients.networks.littlecaprice import LittleCapriceClient
from phoenixadult.clients.networks.loveherfilms import LoveHerFilmsClient
from phoenixadult.clients.networks.metart import MetArtClient
from phoenixadult.clients.networks.missax import MissaXClient
from phoenixadult.clients.networks.modelcentro import ModelCentroClient
from phoenixadult.clients.networks.naughtyamerica import NaughtyAmericaClient
from phoenixadult.clients.networks.network5kporn import Network5KPClient
from phoenixadult.clients.networks.newsensations import NewSensationsClient
from phoenixadult.clients.networks.newsensationsother import NewSensationsOtherClient
from phoenixadult.clients.networks.nubiles import NubilesClient
from phoenixadult.clients.networks.nvg import NVGClient
from phoenixadult.clients.networks.perfectgonzo import PerfectGonzoClient
from phoenixadult.clients.networks.pervcity import PervCityClient
from phoenixadult.clients.networks.pkjmedia import PKJMediaClient
from phoenixadult.clients.networks.porncz import PornCZClient
from phoenixadult.clients.networks.porndoepremium import PorndoePremiumClient
from phoenixadult.clients.networks.pornworld import PornWorldClient
from phoenixadult.clients.networks.private import PrivateClient
from phoenixadult.clients.networks.puffy import PuffyClient
from phoenixadult.clients.networks.purecfnm import PureCFNMClient
from phoenixadult.clients.networks.queensnake import QueenSnakeClient
from phoenixadult.clients.networks.radicalcash import RadicalCashClient
from phoenixadult.clients.networks.radicalcashother import RadicalCashOtherClient
from phoenixadult.clients.networks.reptyle import ReptyleClient
from phoenixadult.clients.networks.romero import RomeroClient
from phoenixadult.clients.networks.scoregroup import ScoreGroupClient
from phoenixadult.clients.networks.sinx import SinXClient
from phoenixadult.clients.networks.spizoo import SpizooClient
from phoenixadult.clients.networks.steppedup import SteppedUpClient
from phoenixadult.clients.networks.strike3 import Strike3Client
from phoenixadult.clients.networks.teencoreclub import TeenCoreClubClient
from phoenixadult.clients.networks.teenmegaworld import TeenMegaWorldClient
from phoenixadult.clients.networks.thickcash import ThickCashClient
from phoenixadult.clients.networks.thickcashother import ThickCashOtherClient
from phoenixadult.clients.networks.unzipvr import UnzipVRClient
from phoenixadult.clients.networks.vip4k import VIP4KClient
from phoenixadult.clients.networks.vna import VNAClient
from phoenixadult.clients.networks.wankz import WankzClient
from phoenixadult.clients.networks.wankzvr import WankzVRClient
from phoenixadult.clients.networks.wownetwork import WowNetworkClient
from phoenixadult.clients.sites.adultempire import AdultEmpireClient
from phoenixadult.clients.sites.alluremedia import AllureMediaClient
from phoenixadult.clients.sites.alsangels import AlsAngelsClient
from phoenixadult.clients.sites.amourangels import AmourAngelsClient
from phoenixadult.clients.sites.analvids import AnalVidsClient
from phoenixadult.clients.sites.bamvisions import BAMVisionsClient
from phoenixadult.clients.sites.belami import BelAmiClient
from phoenixadult.clients.sites.blackpayback import BlackPayBackClient
from phoenixadult.clients.sites.boundhoneys import BoundHoneysClient
from phoenixadult.clients.sites.brandnewamateurs import BrandNewAmateursClient
from phoenixadult.clients.sites.caribbeancom import CaribbeancomClient
from phoenixadult.clients.sites.clips4sale import Clips4SaleClient
from phoenixadult.clients.sites.clubfilly import ClubFillyClient
from phoenixadult.clients.sites.colette import ColetteClient
from phoenixadult.clients.sites.cumbizz import CumbizzClient
from phoenixadult.clients.sites.cumlouder import CumLouderClient
from phoenixadult.clients.sites.darkroomvr import DarkRoomVRClient
from phoenixadult.clients.sites.desperateamateurs import DesperateAmateursClient
from phoenixadult.clients.sites.dickdrainers import DickDrainersClient
from phoenixadult.clients.sites.dorcelclub import DorcelClubClient
from phoenixadult.clients.sites.dorcelvision import DorcelVisionClient
from phoenixadult.clients.sites.expliciteart import ExpliciteArtClient
from phoenixadult.clients.sites.familytherapy import FamilyTherapyClient
from phoenixadult.clients.sites.femjoy import FemjoyClient
from phoenixadult.clients.sites.finishesthejob import FinishesTheJobClient
from phoenixadult.clients.sites.firstanalquest import FirstAnalQuestClient
from phoenixadult.clients.sites.fittingroom import FittingRoomClient
from phoenixadult.clients.sites.fuckingawesome import FuckingAwesomeClient
from phoenixadult.clients.sites.girlsoutwest import GirlsOutWestClient
from phoenixadult.clients.sites.girlsrimming import GirlsRimmingClient
from phoenixadult.clients.sites.heavyonhotties import HeavyOnHottiesClient
from phoenixadult.clients.sites.hegre import HegreClient
from phoenixadult.clients.sites.hollyrandall import HollyRandallClient
from phoenixadult.clients.sites.hologirlsvr import HoloGirlsVRClient
from phoenixadult.clients.sites.hotwifexxx import HotwifeXXXClient
from phoenixadult.clients.sites.hucows import HucowsClient
from phoenixadult.clients.sites.inthecrack import InTheCrackClient
from phoenixadult.clients.sites.jacquieetmichel import JacquieEtMichelClient
from phoenixadult.clients.sites.jesseloadsmonsterfacials import JesseLoadsMonsterFacialsClient
from phoenixadult.clients.sites.jvrporn import JVRPornClient
from phoenixadult.clients.sites.kin8tengoku import Kin8tengokuClient
from phoenixadult.clients.sites.lustomic import LustomicClient
from phoenixadult.clients.sites.lustreality import LustRealityClient
from phoenixadult.clients.sites.manualnfo import ManualNfoClient
from phoenixadult.clients.sites.manyvids import ManyvidsClient
from phoenixadult.clients.sites.meanawolf import MeanaWolfClient
from phoenixadult.clients.sites.melenamariarya import MelenaMariaRyaClient
from phoenixadult.clients.sites.melonechallenge import MeloneChallengeClient
from phoenixadult.clients.sites.momcomesfirst import MomComesFirstClient
from phoenixadult.clients.sites.mompov import MomPOVClient
from phoenixadult.clients.sites.mydirtyhobby import MyDirtyHobbyClient
from phoenixadult.clients.sites.penthousegold import PenthouseGoldClient
from phoenixadult.clients.sites.pjgirls import PJGirlsClient
from phoenixadult.clients.sites.playboyplus import PlayboyPlusClient
from phoenixadult.clients.sites.plumperpass import PlumperPassClient
from phoenixadult.clients.sites.pornstarplatinum import PornstarPlatinumClient
from phoenixadult.clients.sites.povr import POVRClient
from phoenixadult.clients.sites.puba import PubaClient
from phoenixadult.clients.sites.putalocura import PutalocuraClient
from phoenixadult.clients.sites.realitylovers import RealityLoversClient
from phoenixadult.clients.sites.reidmylips import ReidMyLipsClient
from phoenixadult.clients.sites.screwbox import ScrewboxClient
from phoenixadult.clients.sites.screwmetoo import ScrewMeTooClient
from phoenixadult.clients.sites.sexlikereal import SexLikeRealClient
from phoenixadult.clients.sites.sexmex import SexMexClient
from phoenixadult.clients.sites.sicflics import SicflicsClient
from phoenixadult.clients.sites.sinslife import SinsLifeClient
from phoenixadult.clients.sites.stasyq import StasyQClient
from phoenixadult.clients.sites.stepsecrets import StepSecretsClient
from phoenixadult.clients.sites.straponcum import StraponCumClient
from phoenixadult.clients.sites.swallowbay import SwallowBayClient
from phoenixadult.clients.sites.teenytaboo import TeenyTabooClient
from phoenixadult.clients.sites.tonightsgirlfriend import TonightsGirlfriendClient
from phoenixadult.clients.sites.twotgirls import TwoTGirlsClient
from phoenixadult.clients.sites.ultrafilms import UltrafilmsClient
from phoenixadult.clients.sites.vipissy import VIPissyClient
from phoenixadult.clients.sites.virtualreal import VirtualRealClient
from phoenixadult.clients.sites.virtualtaboo import VirtualTabooClient
from phoenixadult.clients.sites.vivid import VividClient
from phoenixadult.clients.sites.vogov import VogoVClient
from phoenixadult.clients.sites.vrallure import VRAllureClient
from phoenixadult.clients.sites.vrlatina import VRLatinaClient
from phoenixadult.clients.sites.vrpfilms import VRPFilmsClient
from phoenixadult.clients.sites.wakeupnfuck import WakeUpNFuckClient
from phoenixadult.clients.sites.watch4beauty import Watch4BeautyClient
from phoenixadult.clients.sites.wearehairy import WeAreHairyClient
from phoenixadult.clients.sites.woodmancastingx import WoodmanCastingXClient
from phoenixadult.clients.sites.xart import XartClient
from phoenixadult.clients.sites.xconfessions import XConfessionsClient
from phoenixadult.clients.sites.xevunleashed import XevUnleashedClient
from phoenixadult.clients.sites.xillimite import XillimiteClient
from phoenixadult.clients.sites.xsinsvr import XSinsVRClient
from phoenixadult.clients.sites.xvirtual import XVirtualClient

CLIENT_REGISTRY: dict[str, Client] = {
    'abbywinters': AbbyWintersClient(),
    'archive': ArchiveClient(),
    'adultempire': AdultEmpireClient(),
    'adultempirecash': AdultEmpireCashClient(),
    'adultprime': AdultPrimeClient(),
    'badoinkvr': BadoinkVrClient(),
    'bang': BangClient(),
    'bellapass': BellaPassClient(),
    'bellesa': BellesaClient(),
    'blurredmedia': BlurredMediaClient(),
    'caramelcash': CaramelCashClient(),
    'cherrypimps': CherryPimpsClient(),
    'couplescinema': CouplesCinemaClient(),
    'czechav': CzechAVClient(),
    'czechvr': CzechVRClient(),
    'derangeddollars': DerangedDollarsClient(),
    'dirtyflix': DirtyFlixClient(),
    'dirtyharddrive': DirtyHardDriveClient(),
    'evolvedfights': EvolvedFightsClient(),
    'fakings': FAKingsClient(),
    'femdomempire': FemdomEmpireClient(),
    'ftv': FTVClient(),
    'fuelvirtual': FuelVirtualClient(),
    'fullpornnetwork': FullPornNetworkClient(),
    'gammaent': GammaEntClient(),
    'gammaentother': GammaEntOtherClient(),
    'gasm': GasmClient(),
    'grooby': GroobyClient(),
    'hightechvr': HighTechVRClient(),
    'interracialpass': InterracialPassClient(),
    'intersec': IntersecClient(),
    'julesjordan': JulesJordanClient(),
    'karups': KarupsClient(),
    'kellymadison': KellyMadisonClient(),
    'killergram': KillergramClient(),
    'kink': KinkClient(),
    'littlecaprice': LittleCapriceClient(),
    'loveherfilms': LoveHerFilmsClient(),
    'metart': MetArtClient(),
    'missax': MissaXClient(),
    'modelcentro': ModelCentroClient(),
    'nvg': NVGClient(),
    'naughtyamerica': NaughtyAmericaClient(),
    '5kporn': Network5KPClient(),
    'newsensations': NewSensationsClient(),
    'newsensationsother': NewSensationsOtherClient(),
    'nubiles': NubilesClient(),
    'pkjmedia': PKJMediaClient(),
    'perfectgonzo': PerfectGonzoClient(),
    'pervcity': PervCityClient(),
    'porncz': PornCZClient(),
    'pornworld': PornWorldClient(),
    'porndoepremium': PorndoePremiumClient(),
    'fuckyoucash': FuckYouCashClient(),
    'private': PrivateClient(),
    'project1service': Project1ServiceClient(),
    'puffy': PuffyClient(),
    'purecfnm': PureCFNMClient(),
    'queensnake': QueenSnakeClient(),
    'radicalcash': RadicalCashClient(),
    'radicalcashother': RadicalCashOtherClient(),
    'reptyle': ReptyleClient(),
    'romero': RomeroClient(),
    'scoregroup': ScoreGroupClient(),
    'sinx': SinXClient(),
    'spizoo': SpizooClient(),
    'steppedup': SteppedUpClient(),
    'strike3': Strike3Client(),
    'teencoreclub': TeenCoreClubClient(),
    'teenmegaworld': TeenMegaWorldClient(),
    'thickcash': ThickCashClient(),
    'thickcashother': ThickCashOtherClient(),
    'unzipvr': UnzipVRClient(),
    'vip4k': VIP4KClient(),
    'vna': VNAClient(),
    'wankz': WankzClient(),
    'wankzvr': WankzVRClient(),
    'wownetwork': WowNetworkClient(),
    'data18empire': Data18EmpireClient(),
    'data18movies': Data18MoviesClient(),
    'data18scenes': Data18ScenesClient(),
    'javbus': JavBusClient(),
    'javdatabase': JAVDatabaseClient(),
    'javlibrary': JavLibraryClient(),
    'metadataapi': MetadataAPIClient(),
    'pornbox': PornboxClient(),
    'alluremedia': AllureMediaClient(),
    'alsangels': AlsAngelsClient(),
    'amourangels': AmourAngelsClient(),
    'analvids': AnalVidsClient(),
    'bamvisions': BAMVisionsClient(),
    'belami': BelAmiClient(),
    'blackpayback': BlackPayBackClient(),
    'boundhoneys': BoundHoneysClient(),
    'brandnewamateurs': BrandNewAmateursClient(),
    'caribbeancom': CaribbeancomClient(),
    'clips4sale': Clips4SaleClient(),
    'clubfilly': ClubFillyClient(),
    'colette': ColetteClient(),
    'darkroomvr': DarkRoomVRClient(),
    'desperateamateurs': DesperateAmateursClient(),
    'dickdrainers': DickDrainersClient(),
    'dorcelclub': DorcelClubClient(),
    'dorcelvision': DorcelVisionClient(),
    'familytherapy': FamilyTherapyClient(),
    'femjoy': FemjoyClient(),
    'finishesthejob': FinishesTheJobClient(),
    'firstanalquest': FirstAnalQuestClient(),
    'fittingroom': FittingRoomClient(),
    'fuckingawesome': FuckingAwesomeClient(),
    'girlsoutwest': GirlsOutWestClient(),
    'girlsrimming': GirlsRimmingClient(),
    'heavyonhotties': HeavyOnHottiesClient(),
    'hegre': HegreClient(),
    'hollyrandall': HollyRandallClient(),
    'hologirlsvr': HoloGirlsVRClient(),
    'hotwifexxx': HotwifeXXXClient(),
    'hucows': HucowsClient(),
    'inthecrack': InTheCrackClient(),
    'jacquieetmichel': JacquieEtMichelClient(),
    'jesseloadsmonsterfacials': JesseLoadsMonsterFacialsClient(),
    'jvrporn': JVRPornClient(),
    'kin8tengoku': Kin8tengokuClient(),
    'lustreality': LustRealityClient(),
    'manualnfo': ManualNfoClient(),
    'manyvids': ManyvidsClient(),
    'meanawolf': MeanaWolfClient(),
    'momcomesfirst': MomComesFirstClient(),
    'mydirtyhobby': MyDirtyHobbyClient(),
    'penthousegold': PenthouseGoldClient(),
    'playboyplus': PlayboyPlusClient(),
    'plumperpass': PlumperPassClient(),
    'pornstarplatinum': PornstarPlatinumClient(),
    'puba': PubaClient(),
    'putalocura': PutalocuraClient(),
    'realitylovers': RealityLoversClient(),
    'reidmylips': ReidMyLipsClient(),
    'screwbox': ScrewboxClient(),
    'screwmetoo': ScrewMeTooClient(),
    'sexlikereal': SexLikeRealClient(),
    'sexmex': SexMexClient(),
    'pjgirls': PJGirlsClient(),
    'povr': POVRClient(),
    'cumbizz': CumbizzClient(),
    'cumlouder': CumLouderClient(),
    'expliciteart': ExpliciteArtClient(),
    'lustomic': LustomicClient(),
    'melenamariarya': MelenaMariaRyaClient(),
    'melonechallenge': MeloneChallengeClient(),
    'mompov': MomPOVClient(),
    'sicflics': SicflicsClient(),
    'sinslife': SinsLifeClient(),
    'stasyq': StasyQClient(),
    'stepsecrets': StepSecretsClient(),
    'straponcum': StraponCumClient(),
    'swallowbay': SwallowBayClient(),
    'teenytaboo': TeenyTabooClient(),
    'tonightsgirlfriend': TonightsGirlfriendClient(),
    'twotgirls': TwoTGirlsClient(),
    'ultrafilms': UltrafilmsClient(),
    'vipissy': VIPissyClient(),
    'vrallure': VRAllureClient(),
    'vrlatina': VRLatinaClient(),
    'vrpfilms': VRPFilmsClient(),
    'virtualreal': VirtualRealClient(),
    'virtualtaboo': VirtualTabooClient(),
    'vivid': VividClient(),
    'vogov': VogoVClient(),
    'wakeupnfuck': WakeUpNFuckClient(),
    'watch4beauty': Watch4BeautyClient(),
    'wearehairy': WeAreHairyClient(),
    'woodmancastingx': WoodmanCastingXClient(),
    'xart': XartClient(),
    'xconfessions': XConfessionsClient(),
    'xevunleashed': XevUnleashedClient(),
    'xillimite': XillimiteClient(),
    'xsinsvr': XSinsVRClient(),
    'xvirtual': XVirtualClient(),
}


def get_client(scraper_type: str) -> Client | None:
    return CLIENT_REGISTRY.get(scraper_type)


def _assert_registry_consistent() -> None:
    """Fail at import time on a typo'd selector scraper_type, which otherwise fails only at runtime for that site."""
    from phoenixadult.registry import SITE_DEFINITIONS

    missing = sorted({s.scraper_config.type for s in SITE_DEFINITIONS} - CLIENT_REGISTRY.keys())
    if missing:
        raise RuntimeError(f'selector scraper_type(s) with no registered client: {", ".join(missing)}')


_assert_registry_consistent()
