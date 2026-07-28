from __future__ import annotations

from pathlib import Path


def safe_join(root: str | Path, *parts: str) -> Path | None:
    base = Path(root).resolve()
    try:
        resolved = base.joinpath(*parts).resolve()
    except (ValueError, OSError):
        return None
    return resolved if resolved.is_relative_to(base) else None


def rel_to(path: str | Path, root: str | Path, default: str | None = None) -> str | None:
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except (ValueError, OSError):
        return default
