from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class RawCaptureEntry:
    label: str
    content_type: Literal['json', 'html']
    body: Any
