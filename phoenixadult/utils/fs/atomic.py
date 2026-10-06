from __future__ import annotations

import os
import secrets
import time
from pathlib import Path

PARTIAL_SUFFIX = '.part'
STALE_AFTER_SECONDS = 3600.0


def write_bytes_atomic(path: Path, data: bytes) -> None:
    partial = path.with_name(f'.{path.name}.{secrets.token_hex(4)}{PARTIAL_SUFFIX}')
    try:
        partial.write_bytes(data)
        os.replace(partial, path)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise


def sweep_partials(*roots: str | Path, older_than: float = STALE_AFTER_SECONDS) -> int:
    cutoff = time.time() - older_than
    removed = 0
    for root in roots:
        for directory, _subdirs, files in os.walk(root):
            for name in files:
                if not (name.startswith('.') and name.endswith(PARTIAL_SUFFIX)):
                    continue
                path = Path(directory, name)
                try:
                    if path.stat().st_mtime < cutoff:
                        path.unlink()
                        removed += 1
                except OSError:
                    continue
    return removed
