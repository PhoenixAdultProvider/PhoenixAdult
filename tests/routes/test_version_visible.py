from __future__ import annotations

import phoenixadult
from tests.conftest import authed_client


def test_the_config_page_shows_the_running_version() -> None:
    page = authed_client().get('/config')
    assert page.status_code == 200
    assert f'v{phoenixadult.__version__}' in page.text, 'the version people are asked to quote in bug reports must be visible'


def test_the_version_badge_uses_the_shared_component() -> None:
    page = authed_client().get('/config').text
    assert 'class="pa-badge pa-mono ver"' in page, 'the badge should reuse the shared component, not a bespoke chip'


def test_the_version_is_available_to_every_page() -> None:
    from phoenixadult.routes import app_version

    assert app_version() == phoenixadult.__version__
