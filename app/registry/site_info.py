from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.models.scraper_config import ScraperConfig

ContentType = Literal['sceneName', 'actors', 'sceneId', 'sceneIdName']
SearchMethod = Literal['enhanced', 'limited', 'exact']
CacheLayout = Literal['auto', 'studio', 'network', 'aggregator']


@dataclass(frozen=True)
class SiteInfo:
    name: str
    base_url: str
    search_path: str
    content_type: ContentType
    scraper_config: ScraperConfig
    provider_id: str | None = None
    provider_name: str | None = None
    direct_url_template: str | None = None
    aliases: list[str] = field(default_factory=list)
    sub_group: str | None = None
    image_referers: list[str] = field(default_factory=list)
    image_cookies: list[str] = field(default_factory=list)
    search_method: SearchMethod | None = None
    search_notes: str | None = None
    use_bypass: bool = False
    cache_layout: CacheLayout = 'auto'


@dataclass(frozen=True)
class ResolvedSiteInfo(SiteInfo):
    provider_id: str = ''
