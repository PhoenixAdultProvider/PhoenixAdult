from __future__ import annotations

from app.utils.http.ssrf_guard import is_blocked_hostname, is_private_address


def test_ssrf_guard_blocks_private() -> None:
    assert is_private_address('127.0.0.1')
    assert is_private_address('169.254.169.254')
    assert is_private_address('10.0.0.1')
    assert not is_private_address('8.8.8.8')


def test_ssrf_guard_blocks_hostnames() -> None:
    assert is_blocked_hostname('localhost')
    assert not is_blocked_hostname('example.com')
