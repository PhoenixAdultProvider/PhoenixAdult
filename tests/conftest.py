from __future__ import annotations

import pytest_httpx2  # noqa: F401  — registers the "httpcore2" respx mocker
import respx.mocks

respx.mocks.DEFAULT_MOCKER = 'httpcore2'
