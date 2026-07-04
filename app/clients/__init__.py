from __future__ import annotations

from app.clients.aggregators.data18empire import Data18EmpireClient
from app.clients.aggregators.data18movies import Data18MoviesClient
from app.clients.aggregators.data18scenes import Data18ScenesClient
from app.clients.aggregators.javbus import JavBusClient
from app.clients.aggregators.javdatabase import JAVDatabaseClient
from app.clients.aggregators.javlibrary import JavLibraryClient
from app.clients.aggregators.metadataapi import MetadataAPIClient
from app.clients.aggregators.pornbox import PornboxClient
from app.clients.base import Client
from app.clients.networks.abbywinters import AbbyWintersClient
from app.clients.networks.adultempirecash import AdultEmpireCashClient
from app.clients.networks.adultprime import AdultPrimeClient
from app.clients.networks.badoinkvr import BadoinkVrClient
from app.clients.networks.bang import BangClient
from app.clients.networks.bellapass import BellaPassClient
from app.clients.networks.bellesa import BellesaClient
from app.clients.networks.blurredmedia import BlurredMediaClient
from app.clients.networks.caramelcash import CaramelCashClient
from app.clients.networks.cherrypimps import CherryPimpsClient
from app.clients.networks.couplescinema import CouplesCinemaClient
from app.clients.networks.czechav import CzechAVClient
from app.clients.networks.czechvr import CzechVRClient
from app.clients.networks.derangeddollars import DerangedDollarsClient
from app.clients.networks.dirtyflix import DirtyFlixClient
from app.clients.networks.dirtyharddrive import DirtyHardDriveClient
from app.clients.networks.evolvedfights import EvolvedFightsClient
from app.clients.networks.fakings import FAKingsClient
from app.clients.networks.femdomempire import FemdomEmpireClient
from app.clients.networks.ftv import FTVClient
from app.clients.networks.fuelvirtual import FuelVirtualClient
from app.clients.networks.fullpornnetwork import FullPornNetworkClient
from app.clients.networks.gammaent import GammaEntClient
from app.clients.networks.gammaentother import GammaEntOtherClient
from app.clients.networks.gasm import GasmClient
from app.clients.networks.grooby import GroobyClient
from app.clients.networks.hightechvr import HighTechVRClient
from app.clients.networks.interracialpass import InterracialPassClient
from app.clients.networks.intersec import IntersecClient
from app.clients.networks.julesjordan import JulesJordanClient
from app.clients.networks.karups import KarupsClient
from app.clients.networks.kellymadison import KellyMadisonClient
from app.clients.networks.killergram import KillergramClient
from app.clients.networks.kink import KinkClient
from app.clients.networks.littlecaprice import LittleCapriceClient
from app.clients.networks.loveherfilms import LoveHerFilmsClient
from app.clients.networks.metart import MetArtClient
from app.clients.networks.missax import MissaXClient
from app.clients.networks.modelcentro import ModelCentroClient
from app.clients.networks.naughtyamerica import NaughtyAmericaClient
from app.clients.networks.network5kporn import Network5KPClient
from app.clients.networks.network18 import Network18Client
from app.clients.networks.newsensations import NewSensationsClient
from app.clients.networks.newsensationsother import NewSensationsOtherClient
from app.clients.networks.nubiles import NubilesClient
from app.clients.networks.nvg import NVGClient
from app.clients.networks.perfectgonzo import PerfectGonzoClient
from app.clients.networks.pervcity import PervCityClient
from app.clients.networks.pkjmedia import PKJMediaClient
from app.clients.networks.porncz import PornCZClient
from app.clients.networks.porndoepremium import PorndoePremiumClient
from app.clients.networks.pornpros import PornProsClient
from app.clients.networks.pornworld import PornWorldClient
from app.clients.networks.private import PrivateClient
from app.clients.networks.project1service import Project1ServiceClient
from app.clients.networks.puffy import PuffyClient
from app.clients.networks.purecfnm import PureCFNMClient
from app.clients.networks.queensnake import QueenSnakeClient
from app.clients.networks.radicalcash import RadicalCashClient
from app.clients.networks.radicalcashother import RadicalCashOtherClient
from app.clients.networks.reptyle import ReptyleClient
from app.clients.networks.romero import RomeroClient
from app.clients.networks.scoregroup import ScoreGroupClient
from app.clients.networks.sinx import SinXClient
from app.clients.networks.spizoo import SpizooClient
from app.clients.networks.steppedup import SteppedUpClient
from app.clients.networks.strike3 import Strike3Client
from app.clients.networks.teencoreclub import TeenCoreClubClient
from app.clients.networks.teenmegaworld import TeenMegaWorldClient
from app.clients.networks.thickcash import ThickCashClient
from app.clients.networks.thickcashother import ThickCashOtherClient
from app.clients.networks.unzipvr import UnzipVRClient
from app.clients.networks.vip4k import VIP4KClient
from app.clients.networks.vna import VNAClient
from app.clients.networks.wankz import WankzClient
from app.clients.networks.wankzvr import WankzVRClient
from app.clients.networks.wownetwork import WowNetworkClient
from app.clients.sites.adultempire import AdultEmpireClient
from app.clients.sites.alluremedia import AllureMediaClient
from app.clients.sites.alsangels import AlsAngelsClient
from app.clients.sites.amourangels import AmourAngelsClient
from app.clients.sites.analvids import AnalVidsClient
from app.clients.sites.bamvisions import BAMVisionsClient
from app.clients.sites.belami import BelAmiClient
from app.clients.sites.blackpayback import BlackPayBackClient
from app.clients.sites.boundhoneys import BoundHoneysClient
from app.clients.sites.brandnewamateurs import BrandNewAmateursClient
from app.clients.sites.caribbeancom import CaribbeancomClient
from app.clients.sites.clips4sale import Clips4SaleClient
from app.clients.sites.clubfilly import ClubFillyClient
from app.clients.sites.colette import ColetteClient
from app.clients.sites.cumbizz import CumbizzClient
from app.clients.sites.cumlouder import CumLouderClient
from app.clients.sites.darkroomvr import DarkRoomVRClient
from app.clients.sites.desperateamateurs import DesperateAmateursClient
from app.clients.sites.dickdrainers import DickDrainersClient
from app.clients.sites.dorcelclub import DorcelClubClient
from app.clients.sites.dorcelvision import DorcelVisionClient
from app.clients.sites.expliciteart import ExpliciteArtClient
from app.clients.sites.familytherapy import FamilyTherapyClient
from app.clients.sites.femjoy import FemjoyClient
from app.clients.sites.finishesthejob import FinishesTheJobClient
from app.clients.sites.firstanalquest import FirstAnalQuestClient
from app.clients.sites.fittingroom import FittingRoomClient
from app.clients.sites.fuckingawesome import FuckingAwesomeClient
from app.clients.sites.girlsoutwest import GirlsOutWestClient
from app.clients.sites.girlsrimming import GirlsRimmingClient
from app.clients.sites.heavyonhotties import HeavyOnHottiesClient
from app.clients.sites.hegre import HegreClient
from app.clients.sites.hollyrandall import HollyRandallClient
from app.clients.sites.hologirlsvr import HoloGirlsVRClient
from app.clients.sites.hotwifexxx import HotwifeXXXClient
from app.clients.sites.hucows import HucowsClient
from app.clients.sites.inthecrack import InTheCrackClient
from app.clients.sites.jacquieetmichel import JacquieEtMichelClient
from app.clients.sites.jesseloadsmonsterfacials import JesseLoadsMonsterFacialsClient
from app.clients.sites.jvrporn import JVRPornClient
from app.clients.sites.kin8tengoku import Kin8tengokuClient
from app.clients.sites.lustomic import LustomicClient
from app.clients.sites.lustreality import LustRealityClient
from app.clients.sites.manualnfo import ManualNfoClient
from app.clients.sites.manyvids import ManyvidsClient
from app.clients.sites.meanawolf import MeanaWolfClient
from app.clients.sites.melenamariarya import MelenaMariaRyaClient
from app.clients.sites.melonechallenge import MeloneChallengeClient
from app.clients.sites.momcomesfirst import MomComesFirstClient
from app.clients.sites.mompov import MomPOVClient
from app.clients.sites.mydirtyhobby import MyDirtyHobbyClient
from app.clients.sites.penthousegold import PenthouseGoldClient
from app.clients.sites.pjgirls import PJGirlsClient
from app.clients.sites.playboyplus import PlayboyPlusClient
from app.clients.sites.plumperpass import PlumperPassClient
from app.clients.sites.pornstarplatinum import PornstarPlatinumClient
from app.clients.sites.povr import POVRClient
from app.clients.sites.puba import PubaClient
from app.clients.sites.putalocura import PutalocuraClient
from app.clients.sites.realitylovers import RealityLoversClient
from app.clients.sites.reidmylips import ReidMyLipsClient
from app.clients.sites.screwbox import ScrewboxClient
from app.clients.sites.screwmetoo import ScrewMeTooClient
from app.clients.sites.sexlikereal import SexLikeRealClient
from app.clients.sites.sexmex import SexMexClient
from app.clients.sites.sicflics import SicflicsClient
from app.clients.sites.sinslife import SinsLifeClient
from app.clients.sites.stasyq import StasyQClient
from app.clients.sites.stepsecrets import StepSecretsClient
from app.clients.sites.straponcum import StraponCumClient
from app.clients.sites.swallowbay import SwallowBayClient
from app.clients.sites.teenytaboo import TeenyTabooClient
from app.clients.sites.tonightsgirlfriend import TonightsGirlfriendClient
from app.clients.sites.twotgirls import TwoTGirlsClient
from app.clients.sites.ultrafilms import UltrafilmsClient
from app.clients.sites.vipissy import VIPissyClient
from app.clients.sites.virtualreal import VirtualRealClient
from app.clients.sites.virtualtaboo import VirtualTabooClient
from app.clients.sites.vivid import VividClient
from app.clients.sites.vogov import VogoVClient
from app.clients.sites.vrallure import VRAllureClient
from app.clients.sites.vrlatina import VRLatinaClient
from app.clients.sites.vrpfilms import VRPFilmsClient
from app.clients.sites.wakeupnfuck import WakeUpNFuckClient
from app.clients.sites.watch4beauty import Watch4BeautyClient
from app.clients.sites.wearehairy import WeAreHairyClient
from app.clients.sites.woodmancastingx import WoodmanCastingXClient
from app.clients.sites.xart import XartClient
from app.clients.sites.xconfessions import XConfessionsClient
from app.clients.sites.xevunleashed import XevUnleashedClient
from app.clients.sites.xillimite import XillimiteClient
from app.clients.sites.xsinsvr import XSinsVRClient
from app.clients.sites.xvirtual import XVirtualClient

CLIENT_REGISTRY: dict[str, Client] = {
    'abbywinters': AbbyWintersClient(),
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
    'network18': Network18Client(),
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
    'pornpros': PornProsClient(),
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
    # A typo'd selector scraper_type otherwise fails only at runtime for that site.
    from app.registry import SITE_DEFINITIONS

    missing = sorted({s.scraper_config.type for s in SITE_DEFINITIONS} - CLIENT_REGISTRY.keys())
    if missing:
        raise RuntimeError(f'selector scraper_type(s) with no registered client: {", ".join(missing)}')


_assert_registry_consistent()
