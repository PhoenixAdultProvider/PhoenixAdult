from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from app.config.env_overrides import load_overrides

load_dotenv()
load_overrides()


@dataclass(frozen=True)
class _Config:
    port: int
    base_url: str
    log_level: str


config = _Config(
    port=int(os.environ.get('PORT') or '3000'),
    base_url=os.environ.get('PHOENIX_BASE_URL') or 'http://localhost:3000',
    log_level=os.environ.get('LOG_LEVEL') or 'info',
)
