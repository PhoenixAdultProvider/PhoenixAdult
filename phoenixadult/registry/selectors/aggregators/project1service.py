from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider
from phoenixadult.utils.helpers.data_files import load_data

PROVIDER_NAME = 'Project1Service'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneIdName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = ''
PROVIDER_DATA18_ENRICHMENT = True

_ALIASES: dict[str, list[str]] = load_data(__file__, 'project1service_aliases')

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Brazzers', base_url='http://www.brazzers.com', aliases=_ALIASES.get('Brazzers', [])),
    PROVIDER.site('BangBros', base_url='https://bangbros.com', aliases=_ALIASES.get('BangBros', [])),
    PROVIDER.site('Reality Kings', base_url='https://www.realitykings.com', aliases=_ALIASES.get('Reality Kings', [])),
    PROVIDER.site('Lets Doe It', base_url='https://letsdoeit.com', aliases=_ALIASES.get('Lets Doe It', [])),
    PROVIDER.site('Mofos', base_url='https://www.mofos.com', aliases=_ALIASES.get('Mofos', [])),
    PROVIDER.site('Babes', base_url='https://www.babes.com', aliases=_ALIASES.get('Babes', [])),
    PROVIDER.site('Twistys', base_url='https://www.twistys.com', aliases=_ALIASES.get('Twistys', [])),
    PROVIDER.site('Digital Playground', base_url='https://www.digitalplayground.com', aliases=_ALIASES.get('Digital Playground', [])),
    PROVIDER.site('SexyHub', base_url='https://www.sexyhub.com', aliases=_ALIASES.get('SexyHub', [])),
    PROVIDER.site('Lesbea', base_url='https://www.lesbea.com', aliases=_ALIASES.get('Lesbea', [])),
    PROVIDER.site('FakeHub', base_url='https://www.fakehub.com', aliases=_ALIASES.get('FakeHub', [])),
    PROVIDER.site('Mile High Media', base_url='https://milehighmedia.com', aliases=_ALIASES.get('Mile High Media', [])),
    PROVIDER.site('Property Sex', base_url='https://www.propertysex.com', aliases=_ALIASES.get('Property Sex', [])),
    PROVIDER.site('TransAngels', base_url='https://www.transangels.com', aliases=_ALIASES.get('TransAngels', [])),
    PROVIDER.site('Family Hookups', base_url='https://www.familyhookups.com', aliases=_ALIASES.get('Family Hookups', [])),
    PROVIDER.site('Family Sinners', base_url='https://www.familysinners.com', aliases=_ALIASES.get('Family Sinners', [])),
    PROVIDER.site('Transsensual', base_url='https://www.transsensual.com', aliases=_ALIASES.get('Transsensual', [])),
    PROVIDER.site('Erito', base_url='https://www.erito.com', aliases=_ALIASES.get('Erito', [])),
    PROVIDER.site('True Amateurs', base_url='https://www.trueamateurs.com', aliases=_ALIASES.get('True Amateurs', [])),
    PROVIDER.site('Look at Her Now', base_url='https://www.lookathernow.com', aliases=_ALIASES.get('Look at Her Now', [])),
    PROVIDER.site('Bi Empire', base_url='http://www.biempire.com', aliases=_ALIASES.get('Bi Empire', [])),
    PROVIDER.site('Deviant Hardcore', base_url='https://www.devianthardcore.com', aliases=_ALIASES.get('Deviant Hardcore', [])),
    PROVIDER.site('She Will Cheat', base_url='https://www.shewillcheat.com', aliases=_ALIASES.get('She Will Cheat', [])),
    PROVIDER.site('Kinky Spa', base_url='https://www.kinkyspa.com', aliases=_ALIASES.get('Kinky Spa', [])),
    PROVIDER.site('Doe Girls', base_url='https://doegirls.com', aliases=_ALIASES.get('Doe Girls', [])),
    PROVIDER.site('Why Not Bi', base_url='https://whynotbi.com', aliases=_ALIASES.get('Why Not Bi', [])),
    PROVIDER.site('HentaiPros', base_url='https://hentaipros.com', aliases=_ALIASES.get('HentaiPros', [])),
    PROVIDER.site('XXXPawn', base_url='http://xxxpawn.com', aliases=_ALIASES.get('XXXPawn', [])),
    PROVIDER.site('Mia Khalifa', base_url='http://miakhalifa.com', aliases=_ALIASES.get('Mia Khalifa', [])),
    PROVIDER.site('Blacks on Moms', base_url='http://blacksonmoms.com', aliases=_ALIASES.get('Blacks on Moms', [])),
    PROVIDER.site('Filthy Family', base_url='http://filthyfamily.com', aliases=_ALIASES.get('Filthy Family', [])),
    PROVIDER.site('Deviante', base_url='https://www.deviante.com', aliases=_ALIASES.get('Deviante', [])),
    PROVIDER.site('Forgive Me Father', base_url='https://www.forgivemefather.com', aliases=_ALIASES.get('Forgive Me Father', [])),
    PROVIDER.site('Sex Working', base_url='https://www.sexworking.com', aliases=_ALIASES.get('Sex Working', [])),
    PROVIDER.site('Pretty Dirty Teens', base_url='https://www.prettydirtyteens.com', aliases=_ALIASES.get('Pretty Dirty Teens', [])),
    PROVIDER.site('Love Her Ass', base_url='https://www.loveherass.com', aliases=_ALIASES.get('Love Her Ass', [])),
    PROVIDER.site('Erotic Spice', base_url='https://www.eroticspice.com', aliases=_ALIASES.get('Erotic Spice', [])),
    PROVIDER.site('Milfed', base_url='https://milfed.com', aliases=_ALIASES.get('Milfed', [])),
    PROVIDER.site('Girl Grind', base_url='https://www.girlgrind.com', aliases=_ALIASES.get('Girl Grind', [])),
    PROVIDER.site('Virtual Porn', base_url='https://virtualporn.com', aliases=_ALIASES.get('Virtual Porn', [])),
    PROVIDER.site('Squirted', base_url='https://squirted.com', aliases=_ALIASES.get('Squirted', [])),
    PROVIDER.site('Gilfed', base_url='https://gilfed.com', aliases=_ALIASES.get('Gilfed', [])),
    PROVIDER.site('Dilfed', base_url='https://dilfed.com', aliases=_ALIASES.get('Dilfed', [])),
    PROVIDER.site('Sex Selector', base_url='https://www.sexselector.com', aliases=_ALIASES.get('Sex Selector', [])),
    PROVIDER.site('My GF', base_url='https://www.mygf.com', aliases=_ALIASES.get('My GF', [])),
]
