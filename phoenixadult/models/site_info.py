from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from phoenixadult.models.scraper_config import ScraperConfig

ContentType = Literal['sceneName', 'actors', 'sceneId', 'sceneIdName']
SearchMethod = Literal['enhanced', 'limited', 'exact']
BypassName = Literal['Impersonate', 'FlareSolverr', 'Playwright', 'ReqBin']


@dataclass(frozen=True)
class SiteInfo:
    name: str
    base_url: str
    search_path: str
    content_type: ContentType
    scraper_config: ScraperConfig
    fallback_url: str = ''
    provider_id: str | None = None
    provider_name: str | None = None
    direct_url_template: str | None = None
    aliases: tuple[str, ...] = ()
    sub_group: str | None = None
    image_referers: tuple[str, ...] = ()
    image_cookies: tuple[str, ...] = ()
    search_method: SearchMethod | None = None
    search_notes: str | None = None
    bypass: tuple[BypassName, ...] = ()
    token_prefixes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ('aliases', 'image_referers', 'image_cookies', 'token_prefixes', 'bypass'):
            object.__setattr__(self, name, tuple(getattr(self, name)))

    def search_url(self, query: str) -> str:
        path = self.search_path.replace('{query}', query)
        return path if path.startswith(('http://', 'https://')) else self.base_url.rstrip('/') + path


@dataclass(frozen=True)
class ResolvedSiteInfo(SiteInfo):
    provider_id: str = ''
