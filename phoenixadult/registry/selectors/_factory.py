from __future__ import annotations

from phoenixadult.models.scraper_config import ScraperConfig
from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo


def make_site(
    name: str,
    *,
    scraper_type: str,
    base_url: str,
    fallback_url: str = '',
    search_path: str = '/',
    content_type: ContentType = 'sceneName',
    data18_enrichment: bool = False,
    provider_id: str | None = None,
    provider_name: str | None = None,
    direct_url_template: str | None = None,
    aliases: list[str] | None = None,
    sub_group: str | None = None,
    image_referers: list[str] | None = None,
    image_cookies: list[str] | None = None,
    search_method: SearchMethod | None = None,
    search_notes: str | None = None,
    use_bypass: bool = False,
    token_prefixes: tuple[str, ...] = (),
) -> SiteInfo:
    return SiteInfo(
        name=name,
        base_url=base_url,
        fallback_url=fallback_url,
        search_path=search_path,
        content_type=content_type,
        scraper_config=ScraperConfig(type=scraper_type, data18_enrichment=data18_enrichment),
        provider_id=provider_id,
        provider_name=provider_name,
        direct_url_template=direct_url_template,
        aliases=aliases if aliases is not None else [],
        sub_group=sub_group,
        image_referers=image_referers if image_referers is not None else [],
        image_cookies=image_cookies if image_cookies is not None else [],
        search_method=search_method,
        search_notes=search_notes,
        use_bypass=use_bypass,
        token_prefixes=token_prefixes,
    )
