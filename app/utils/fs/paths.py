from __future__ import annotations

from pathlib import Path


def safe_join(root: str | Path, *parts: str) -> Path | None:
    """Resolve ``root``/``parts`` and return it only if it stays inside ``root``
    (path-traversal guard); ``None`` if it escapes or can't be resolved."""
    base = Path(root).resolve()
    try:
        resolved = base.joinpath(*parts).resolve()
    except (ValueError, OSError):
        return None
    return resolved if resolved.is_relative_to(base) else None


def is_within(root: str | Path, path: str | Path) -> bool:
    """True if ``path`` resolves to ``root`` or a descendant of it."""
    base = Path(root).resolve()
    try:
        target = Path(path).resolve()
    except (ValueError, OSError):
        return False
    return target.is_relative_to(base)
