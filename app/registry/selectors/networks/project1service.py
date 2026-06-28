from __future__ import annotations

from app.registry.selectors._factory import make_site
from app.registry.site_info import ContentType, SearchMethod, SiteInfo
from app.utils.helpers.helpers import load_site_json

PROVIDER_NAME = 'Project1Service'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneIdName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''

_ALIASES: dict[str, list[str]] = load_site_json(__file__, 'project1service_aliases')


def _site(name: str, base_url: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=base_url,
        search_path='',
        content_type=PROVIDER_CONTENT_TYPE,
        aliases=_ALIASES.get(name, []),
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='project1service', data18_enrichment=True,
        cache_layout='aggregator',  # aggregator of networks with sub-brands → project1service/<studio>/<sub-site>
    )


PROJECT1SERVICE_SITES: list[SiteInfo] = [
    _site('Brazzers', 'http://www.brazzers.com'),
    _site('BangBros', 'https://bangbros.com'),
    _site('Reality Kings', 'https://www.realitykings.com'),
    _site('Lets Doe It', 'https://letsdoeit.com'),
    _site('Mofos', 'https://www.mofos.com'),
    _site('Babes', 'https://www.babes.com'),
    _site('Twistys', 'https://www.twistys.com'),
    _site('Digital Playground', 'https://www.digitalplayground.com'),
    _site('SexyHub', 'https://www.sexyhub.com'),
    _site('Lesbea', 'https://www.lesbea.com'),
    _site('FakeHub', 'https://www.fakehub.com'),
    _site('Mile High Media', 'https://milehighmedia.com'),
    _site('Property Sex', 'https://www.propertysex.com'),
    _site('TransAngels', 'https://www.transangels.com'),
    _site('Family Hookups', 'https://www.familyhookups.com'),
    _site('Family Sinners', 'https://www.familysinners.com'),
    _site('Transsensual', 'https://www.transsensual.com'),
    _site('Erito', 'https://www.erito.com'),
    _site('True Amateurs', 'https://www.trueamateurs.com'),
    _site('Look At Her Now', 'https://www.lookathernow.com'),
    _site('Bi Empire', 'http://www.biempire.com'),
    _site('Deviant Hardcore', 'https://www.devianthardcore.com'),
    _site('She Will Cheat', 'https://www.shewillcheat.com'),
    _site('Kinky Spa', 'https://www.kinkyspa.com'),
    _site('Doe Girls', 'https://doegirls.com'),
    _site('Why Not Bi', 'https://whynotbi.com'),
    _site('HentaiPros', 'https://hentaipros.com'),
    _site('XXXPawn', 'http://xxxpawn.com'),
    _site('Mia Khalifa', 'http://miakhalifa.com'),
    _site('Blacks On Moms', 'http://blacksonmoms.com'),
    _site('Filthy Family', 'http://filthyfamily.com'),
    _site('Deviante', 'https://www.deviante.com'),
    _site('Forgive Me Father', 'https://www.forgivemefather.com'),
    _site('Sex Working', 'https://www.sexworking.com'),
    _site('Pretty Dirty Teens', 'https://www.prettydirtyteens.com'),
    _site('Love Her Ass', 'https://www.loveherass.com'),
    _site('Erotic Spice', 'https://www.eroticspice.com'),
    _site('Milfed', 'https://milfed.com'),
    _site('Girl Grind', 'https://www.girlgrind.com'),
    _site('Virtual Porn', 'https://virtualporn.com'),
    _site('Squirted', 'https://squirted.com'),
    _site('Gilfed', 'https://gilfed.com'),
    _site('Dilfed', 'https://dilfed.com'),
    _site('Sex Selector', 'https://www.sexselector.com'),
    _site('My GF', 'https://www.mygf.com'),
]
