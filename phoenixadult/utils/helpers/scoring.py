from __future__ import annotations

import re

from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.processors.similarity import compare_string
from phoenixadult.utils.processors.title_case import convert_sequence_numbers, title_case


def sceneid_distance_score(query: str, title: str) -> int:
    score = 100 - compare_string(query, title).levenshtein
    logger.debug('Scene ID Distance Score', f'Query: {query}, Title: {title}, Score: {score}')
    return score


_TITLE_CLEAN_RE = re.compile(r'[^a-z0-9]+', re.IGNORECASE)


def title_distance_score(query: str, title: str) -> int:
    def _score(q: str, t: str) -> int:
        return 100 - compare_string(_TITLE_CLEAN_RE.sub('', q).lower(), _TITLE_CLEAN_RE.sub('', t).lower()).levenshtein

    query, title = title_case(query), title_case(title)
    score = _score(query, title)
    nq, nt = convert_sequence_numbers(query), convert_sequence_numbers(title)
    if nq or nt:
        score = max(score, _score(nq or query, nt or title))
    logger.debug('Title Distance Score', f'Query: {query}, Title: {title}, Score: {score}')
    return score


def date_distance_score(search_date: str, release_date: str) -> int:
    score = 100 - compare_string(search_date, release_date).levenshtein
    logger.debug('Date Distance Score', f'Search Date: {search_date}, Release Date: {release_date}, Score: {score}')
    return score
