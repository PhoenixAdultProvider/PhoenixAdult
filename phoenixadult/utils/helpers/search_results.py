from __future__ import annotations

import re

from phoenixadult.models.scrape import SearchResult
from phoenixadult.models.site_info import ResolvedSiteInfo
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.scoring import date_distance_score
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.processors.actor_strip import best_title_score


def build_search_result(
    *,
    title: str,
    scene_url: str,
    query: str,
    search_date: str | None = None,
    display_date: str | None = None,
    score: float | None = None,
    cur_id: str | None = None,
    thumb_url: str | None = None,
    search_url: str | None = None,
    subsite: str | None = None,
    site: ResolvedSiteInfo,
) -> SearchResult:
    title = re.sub(r'\s+', ' ', title).strip()

    if score is not None:
        computed = score
    elif search_date and display_date:
        computed = date_distance_score(search_date, display_date)
    else:
        computed = best_title_score(query, title, site)

    logger.debug('Result Builder', f'Final score: {computed}')
    release_date = display_date or search_date or None
    if cur_id is None:
        cur_id = pack_cur_id([p for p in (scene_url, release_date) if p])

    return SearchResult(
        title=title,
        scene_url=scene_url,
        release_date=release_date,
        display_date=display_date or None,
        cur_id=cur_id,
        score=computed,
        thumb_url=thumb_url or None,
        search_url=search_url or None,
        subsite=subsite or None,
    )
