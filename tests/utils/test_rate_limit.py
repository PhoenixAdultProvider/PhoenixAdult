from __future__ import annotations

import pytest

from phoenixadult.utils.auth import rate_limit


@pytest.fixture(autouse=True)
def _clear() -> None:
    rate_limit._buckets.clear()


def test_free_attempts_are_not_throttled() -> None:
    for _ in range(rate_limit._FREE_ATTEMPTS):
        assert rate_limit.retry_after('login', 'k') == 0.0
        rate_limit.record_failure('login', 'k')
    assert rate_limit.retry_after('login', 'k') == 0.0


def test_backoff_kicks_in_after_free_attempts() -> None:
    for _ in range(rate_limit._FREE_ATTEMPTS + 1):
        rate_limit.record_failure('login', 'k')
    assert rate_limit.retry_after('login', 'k') > 0.0


def test_success_clears_the_bucket() -> None:
    for _ in range(rate_limit._FREE_ATTEMPTS + 2):
        rate_limit.record_failure('login', 'k')
    assert rate_limit.retry_after('login', 'k') > 0.0
    rate_limit.record_success('login', 'k')
    assert rate_limit.retry_after('login', 'k') == 0.0


def test_scopes_and_keys_are_independent() -> None:
    for _ in range(rate_limit._FREE_ATTEMPTS + 2):
        rate_limit.record_failure('login', 'alice')
    assert rate_limit.retry_after('login', 'alice') > 0.0
    assert rate_limit.retry_after('login', 'bob') == 0.0
    assert rate_limit.retry_after('setup', 'alice') == 0.0
