from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from phoenixadult.registry import get_all_providers
from phoenixadult.utils.plex.media_type import provider_mount_path
from tests.conftest import seed_connection

MOUNT = provider_mount_path(get_all_providers()[0])


@pytest.fixture
def remote() -> TestClient:
    from phoenixadult.services import plex_connections

    connection = seed_connection()
    plex_connections.set_allowed_clients(connection.id, ['some-registered-client'])
    return TestClient(create_app(), client=('203.0.113.9', 51234))


def test_a_registered_allowlist_no_longer_blocks_anyone(remote: TestClient) -> None:
    assert remote.get(MOUNT).status_code == 200, 'Plex sends no client identifier when adding a provider'
    assert remote.get(MOUNT, headers={'X-Plex-Client-Identifier': 'unknown-client'}).status_code == 200
    assert remote.post(f'{MOUNT}/library/metadata/matches', json={'type': 1, 'filename': 'a.mp4'}).status_code == 200


def test_provider_requests_are_traced_with_their_headers(remote: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(5, logger='phoenixadult'):
        remote.get(MOUNT, headers={'X-Plex-Client-Identifier': 'abc-123', 'X-Plex-Product': 'Plex Media Server'})
    text = caplog.text
    assert f'GET {MOUNT} from 203.0.113.9' in text, 'the trace must name the path and the caller'
    assert 'abc-123' in text and 'Plex Media Server' in text, 'the trace must dump the headers Plex sent'


def test_the_trace_masks_credential_headers(remote: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(5, logger='phoenixadult'):
        remote.get(MOUNT, headers={'X-Plex-Token': 'super-secret', 'Authorization': 'Bearer pa_secret', 'X-Plex-Product': 'PMS'})
    assert 'PMS' in caplog.text, 'the trace should still run'
    assert 'super-secret' not in caplog.text
    assert 'pa_secret' not in caplog.text


def test_tracing_costs_nothing_when_the_level_is_off(remote: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.utils.logging import request_trace

    calls: list[str] = []
    monkeypatch.setattr(request_trace, 'verbose_enabled', lambda: False)
    monkeypatch.setattr(request_trace.logger, 'verbose', lambda *a, **k: calls.append('emitted'))
    assert remote.get(MOUNT).status_code == 200
    assert calls == [], 'no dump should be built when verbose logging is off'
