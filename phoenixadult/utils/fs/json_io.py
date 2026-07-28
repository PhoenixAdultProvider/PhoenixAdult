from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: Path, default: Any = None, tag: str | None = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as err:
        if tag is not None:
            _warn(tag, f'could not read {path}: {err}')
        return default


def _warn(tag: str, message: str) -> None:
    try:
        from phoenixadult.utils.logging.logger import logger
    except ImportError:
        print(f'[{tag}] {message}')
        return
    logger.warn(tag, message)
