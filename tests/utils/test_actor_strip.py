from __future__ import annotations

import pytest

from phoenixadult.registry import find_site
from phoenixadult.utils.processors.actor_strip import actor_strip_candidates, best_title_score, enabled_for, split_actor_prefix, strip_actor_prefix

NUBILE_FILMS = find_site('Nubile Films')
MY_FAMILY_PIES = find_site('My Family Pies')
BRATTY_SIS = find_site('Bratty Sis')
NEW_SENSATIONS = find_site('New Sensations')
assert NUBILE_FILMS and MY_FAMILY_PIES and BRATTY_SIS and NEW_SENSATIONS


def test_strip_actor_prefix_shapes() -> None:
    assert strip_actor_prefix('jane doe a cool scene') == 'a cool scene'
    assert strip_actor_prefix('jane doe and jane smith a cool scene') == 'a cool scene'


def test_split_actor_prefix_returns_both_sides() -> None:
    assert split_actor_prefix('jane doe a cool scene') == ('jane doe', 'a cool scene')
    assert split_actor_prefix('jane doe and jane smith a cool scene') == ('jane doe and jane smith', 'a cool scene')


def test_candidates_cover_one_to_three_actors_and_long_names() -> None:
    assert 'a cool scene' in actor_strip_candidates('jane doe a cool scene')
    assert 'a cool scene' in actor_strip_candidates('jane doe and jane smith a cool scene')
    assert 'a cool scene' in actor_strip_candidates('jane doe jane frost and jane smith a cool scene')
    assert 'a cool scene' in actor_strip_candidates('abby lee brazil a cool scene')
    assert actor_strip_candidates('short one')[0] == 'short one'


def test_candidates_cover_one_word_stage_names() -> None:
    assert 'a cool scene' in actor_strip_candidates('sybil a cool scene')
    assert 'a cool scene' in actor_strip_candidates('sybil and luna a cool scene')
    assert 'a cool scene' in actor_strip_candidates('jane doe and sybil a cool scene')
    assert 'a cool scene' in actor_strip_candidates('sybil and abby lee brazil a cool scene')
    assert 'a cool scene' in actor_strip_candidates('abby lee brazil and jane smith a cool scene')


def test_enabled_for_normalizes_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('SEARCH_STRIP_ACTORS', raising=False)
    assert enabled_for(NUBILE_FILMS) is False
    monkeypatch.setenv('SEARCH_STRIP_ACTORS', 'nubile-films, New Sensations')
    assert enabled_for(NUBILE_FILMS) is True
    assert enabled_for(NEW_SENSATIONS) is True
    assert enabled_for(MY_FAMILY_PIES) is False


def test_enabled_for_matches_studio_and_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('SEARCH_STRIP_ACTORS', 'Nubiles Porn')
    assert enabled_for(MY_FAMILY_PIES) is True
    assert enabled_for(BRATTY_SIS) is False

    monkeypatch.setenv('SEARCH_STRIP_ACTORS', 'Nubiles')
    assert enabled_for(MY_FAMILY_PIES) is True
    assert enabled_for(BRATTY_SIS) is True
    assert enabled_for(NEW_SENSATIONS) is False


def test_best_title_score_strips_only_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    query = 'jane doe a very cool scene'
    title = 'A Very Cool Scene'
    monkeypatch.delenv('SEARCH_STRIP_ACTORS', raising=False)
    plain = best_title_score(query, title, NUBILE_FILMS)
    monkeypatch.setenv('SEARCH_STRIP_ACTORS', 'Nubile Films')
    stripped = best_title_score(query, title, NUBILE_FILMS)
    assert stripped == 100
    assert stripped > plain


def test_best_title_score_never_below_plain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('SEARCH_STRIP_ACTORS', 'Nubile Films')
    query = 'a very cool scene'
    title = 'A Very Cool Scene'
    assert best_title_score(query, title, NUBILE_FILMS) == 100


def test_best_title_score_network_entry_covers_member_site(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('SEARCH_STRIP_ACTORS', 'Nubiles')
    assert best_title_score('nata ocean stepsis is a flirt', 'Stepsis Is a Flirt', MY_FAMILY_PIES) == 100
