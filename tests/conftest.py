from __future__ import annotations

import os
import tempfile

# Keep test runs out of the real local/logs/agent.log: point file logging at a temp
# dir BEFORE any app module (and its logger, which opens the file at import) loads.
os.environ['LOG_DIR'] = os.path.join(tempfile.gettempdir(), 'phoenixadult-pytest-logs')

import pytest_httpx2  # noqa: E402, F401  — registers the "httpcore2" respx mocker
import respx.mocks  # noqa: E402

respx.mocks.DEFAULT_MOCKER = 'httpcore2'
