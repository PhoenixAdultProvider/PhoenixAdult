from __future__ import annotations

from parsel import Selector

from app.utils.logging.logger import logger
from app.utils.people.sources._http import encode_name, make_source_http
from app.utils.people.types import PersonLookupContext, PhotoHit


class _FreeonesSource:
    name = 'Freeones'

    async def find(self, actor_name: str, ctx: PersonLookupContext) -> PhotoHit | None:
        search_url = f'https://www.freeones.com/babes?q={encode_name(actor_name)}'
        logger.debug('freeonesSource', f'GET {search_url}')
        async with make_source_http() as client:
            search_html = (await client.get(search_url)).text
            href = Selector(text=search_html).xpath('(//div[contains(@class,"grid-item")]//a/@href)[1]').get()
            if not href:
                logger.debug('freeonesSource', f'no grid-item match for "{actor_name}"')
                return None

            bio_url = f'https://www.freeones.com{href.replace("/feed", "/bio")}'
            sel = Selector(text=(await client.get(bio_url)).text)

        db_name = (sel.xpath('normalize-space((//h1)[1])').get() or '').lower().replace(' bio', '').strip()
        aliases = {db_name}
        alias_text = sel.xpath('normalize-space((//p[contains(.,"Aliases")]/following-sibling::div[1]//p)[1])').get() or ''
        for alias in alias_text.split(','):
            a = alias.strip().lower()
            if a:
                aliases.add(a)

        prof_text = sel.xpath('normalize-space((//p[contains(.,"Profession")]/following-sibling::div[1]//p)[1])').get() or ''
        professions = [p.strip() for p in prof_text.split(',')]
        is_porn_star = any(p in ('Porn Stars', 'Adult Models') for p in professions)
        img = sel.xpath('(//div[contains(@class,"image-container")]//a//img/@src)[1]').get()

        if img and actor_name.lower() in aliases and is_porn_star:
            logger.debug('freeonesSource', f'matched "{actor_name}" → {img}')
            return PhotoHit(url=img, gender='female')
        logger.debug('freeonesSource', f'rejected "{actor_name}" (img={bool(img)} aliasHit={actor_name.lower() in aliases} pornStar={is_porn_star})')
        return None


freeones_source = _FreeonesSource()
