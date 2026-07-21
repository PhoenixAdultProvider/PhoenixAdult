from __future__ import annotations

import pytest

from app.utils.processors.actor_strip import actor_strip_candidates, best_title_score, enabled_for, split_actor_prefix, strip_actor_prefix


def test_strip_actor_prefix_legacy_shapes() -> None:
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
    assert enabled_for('Nubile Films') is False
    monkeypatch.setenv('SEARCH_STRIP_ACTORS', 'nubile-films, New Sensations')
    assert enabled_for('Nubile Films') is True
    assert enabled_for('New Sensations') is True
    assert enabled_for('Bratty MILF') is False


def test_best_title_score_strips_only_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    query = 'jane doe a very cool scene'
    title = 'A Very Cool Scene'
    monkeypatch.delenv('SEARCH_STRIP_ACTORS', raising=False)
    plain = best_title_score(query, title, 'Nubile Films')
    monkeypatch.setenv('SEARCH_STRIP_ACTORS', 'Nubile Films')
    stripped = best_title_score(query, title, 'Nubile Films')
    assert stripped == 100
    assert stripped > plain


def test_best_title_score_never_below_plain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('SEARCH_STRIP_ACTORS', 'Nubile Films')
    query = 'a very cool scene'
    title = 'A Very Cool Scene'
    assert best_title_score(query, title, 'Nubile Films') == 100
