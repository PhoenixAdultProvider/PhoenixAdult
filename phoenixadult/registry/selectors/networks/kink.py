from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Kink'
PROVIDER_BASE_URL = 'https://www.kink.com'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/search?q={query}'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Kink'),
    PROVIDER.site('Brutal Sessions', search_path='/search?channelIds=brutalsessions&q={query}'),
    PROVIDER.site('Device Bondage', search_path='/search?channelIds=devicebondage&q={query}'),
    PROVIDER.site('Families Tied', search_path='/search?channelIds=familiestied&q={query}'),
    PROVIDER.site('Hardcore Gangbang', search_path='/search?channelIds=hardcoregangbang&q={query}'),
    PROVIDER.site('Hogtied', search_path='/search?channelIds=hogtied&q={query}'),
    PROVIDER.site('Kink Features', search_path='/search?channelIds=kinkfeatures&q={query}'),
    PROVIDER.site('Kink University', search_path='/search?channelIds=kinkuniversity&q={query}'),
    PROVIDER.site('Public Disgrace', search_path='/search?channelIds=publicdisgrace&q={query}'),
    PROVIDER.site('Sadistic Rope', search_path='/search?channelIds=sadisticrope&q={query}'),
    PROVIDER.site('Sex and Submission', search_path='/search?channelIds=sexandsubmission&q={query}'),
    PROVIDER.site('The Training of O', search_path='/search?channelIds=thetrainingofo&q={query}'),
    PROVIDER.site('The Upper Floor', search_path='/search?channelIds=theupperfloor&q={query}'),
    PROVIDER.site('Water Bondage', search_path='/search?channelIds=waterbondage&q={query}'),
    PROVIDER.site('Everything Butt', search_path='/search?channelIds=everythingbutt&q={query}'),
    PROVIDER.site('Foot Worship', search_path='/search?channelIds=footworship&q={query}'),
    PROVIDER.site('Fucking Machines', search_path='/search?channelIds=fuckingmachines&q={query}'),
    PROVIDER.site('TS Pussy Hunters', search_path='/search?channelIds=tspussyhunters&q={query}'),
    PROVIDER.site('TS Seduction', search_path='/search?channelIds=tsseduction&q={query}'),
    PROVIDER.site('Ultimate Surrender', search_path='/search?channelIds=ultimatesurrender&q={query}'),
    PROVIDER.site('30 Minutes of Torment', search_path='/search?channelIds=30minutesoftorment&q={query}'),
    PROVIDER.site('Bound Gods', search_path='/search?channelIds=boundgods&q={query}'),
    PROVIDER.site('Bound in Public', search_path='/search?channelIds=boundinpublic&q={query}'),
    PROVIDER.site('Butt Machine Boys', search_path='/search?channelIds=buttmachineboys&q={query}'),
    PROVIDER.site('Men on Edge', search_path='/search?channelIds=menonedge&q={query}'),
    PROVIDER.site('Naked Kombat', search_path='/search?channelIds=nakedkombat&q={query}'),
    PROVIDER.site('Divine Bitches', search_path='/search?channelIds=divinebitches&q={query}'),
    PROVIDER.site('Electrosluts', search_path='/search?channelIds=electrosluts&q={query}'),
    PROVIDER.site('Men in Pain', search_path='/search?channelIds=meninpain&q={query}'),
    PROVIDER.site('Whipped Ass', search_path='/search?channelIds=whippedass&q={query}'),
    PROVIDER.site('Wired Pussy', search_path='/search?channelIds=wiredpussy&q={query}'),
    PROVIDER.site('Bound Gang Bangs', search_path='/search?channelIds=boundgangbangs&q={query}'),
    PROVIDER.site('Chantas Bitches', search_path='/search?channelIds=chantasbitches&q={query}'),
    PROVIDER.site('Fucked and Bound', search_path='/search?channelIds=fuckedandbound&q={query}'),
    PROVIDER.site('Captive Male', search_path='/search?channelIds=captivemale&q={query}'),
    PROVIDER.site('SubmissiveX', search_path='/search?channelIds=submissivex&q={query}'),
    PROVIDER.site('Filthy Femdom', search_path='/search?channelIds=filthyfemdom&q={query}'),
    PROVIDER.site('Kink Evolved Fights Lesbian Edition', search_path='/search?channelIds=evolvedfightslesbianedition&q={query}'),
    PROVIDER.site('Kink Evolved Fights', search_path='/search?channelIds=evolvedfights&q={query}'),
    PROVIDER.site('StraponSquad', search_path='/search?channelIds=straponsquad&q={query}'),
    PROVIDER.site('SexualDisgrace', search_path='/search?channelIds=sexualdisgrace&q={query}'),
    PROVIDER.site('FetishNetwork', search_path='/search?channelIds=fetishnetwork&q={query}'),
    PROVIDER.site('FetishNetwork Male', search_path='/search?channelIds=fetishnetworkmale&q={query}'),
]
