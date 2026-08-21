from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from phoenixadult.routes.dev_routes import _searched_url


@dataclass
class _Capture:
    label: str


@dataclass
class _Result:
    search_url: str | None


def test_a_result_that_reports_its_own_url_wins() -> None:
    results: list[Any] = [_Result(None), _Result('https://site.test/search?q=x')]
    assert _searched_url(results, [_Capture('GET https://other.test/ 200')]) == 'https://site.test/search?q=x'


def test_it_falls_back_to_the_first_get_that_was_captured() -> None:
    captures = [_Capture('POST https://site.test/login'), _Capture('GET https://site.test/search?q=x 200')]
    assert _searched_url([_Result(None)], captures) == 'https://site.test/search?q=x'


def test_no_results_and_no_captures_yields_nothing() -> None:
    assert _searched_url(None, []) == ''
    assert _searched_url([], []) == ''


def test_a_capture_with_no_get_yields_nothing() -> None:
    assert _searched_url([_Result(None)], [_Capture('POST https://site.test/x')]) == ''
