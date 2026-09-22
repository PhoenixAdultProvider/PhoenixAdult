from __future__ import annotations

from datetime import datetime

from phoenixadult.clients import get_client
from phoenixadult.clients.aggregators.data18 import Data18Client
from phoenixadult.config.env import env
from phoenixadult.models.metadata import PlexData18, PlexMetadataResponse
from phoenixadult.models.site_info import ResolvedSiteInfo
from phoenixadult.registry import find_site
from phoenixadult.utils.helpers.data18 import data18_ref_with_extras, mapping_slug
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.processors.studio_name import normalize_studio


async def backfill_data18(response: PlexMetadataResponse, site_name: str) -> bool:
    if not env.data18_enabled:
        return False
    site = find_site(site_name)
    if not site or not site.scraper_config.data18_enrichment:
        return False
    pending = [md for md in response.MediaContainer.Metadata if md.data18 is None and md.title]
    if not pending:
        return False

    client = Data18Client()
    changed = False
    for md in pending:
        try:
            date_obj = datetime.fromisoformat(md.originallyAvailableAt) if md.originallyAvailableAt else None
        except ValueError:
            date_obj = None
        providers = [p for p in (md.studio, md.tagline) if p]
        try:
            url = await client.find_scene_url(mapping_slug(md.title, md.tagline or md.studio), md.title, providers, date_obj)
        except Exception as err:  # noqa: BLE001 — backfill must never break the serve
            logger.warn('meta-cache', f'data18 backfill resolve failed for "{md.title}": {err}')
            continue
        if ref := data18_ref_with_extras(url):
            md.data18 = PlexData18.model_validate(ref)
            changed = True
    return changed


def backfill_studio(response: PlexMetadataResponse, site: ResolvedSiteInfo) -> bool:
    client = get_client(site.scraper_config.type)
    derived = client.studio_for(site) if client else None
    if not derived:
        return False
    try:
        md = response.MediaContainer.Metadata[0]
    except (AttributeError, IndexError):
        return False
    if normalize_studio(derived) == md.studio:
        return False
    logger.info('meta-cache', f'restudioed "{md.title}": {md.studio!r} -> {normalize_studio(derived)!r}')
    md.studio = normalize_studio(derived)
    if md.tagline and md.tagline == md.studio:
        md.tagline = None
    return True
