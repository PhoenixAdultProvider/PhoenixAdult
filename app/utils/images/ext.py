from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

IMAGE_EXTS = frozenset({'.jpg', '.jpeg', '.png', '.gif', '.webp', '.tbn', '.jfif'})

_CT_EXTS = {'jpeg': '.jpg', 'svg+xml': '.svg'}


def is_image_content_type(content_type: str) -> bool:
    return content_type.lower().startswith('image/')


def ext_from(content_type: str, url: str, *, allow_svg: bool = False, default: str = '.jpg') -> str:
    """Best extension for a downloaded image: content-type subtype first, then the URL
    path suffix; `default` when neither yields a known image extension."""
    allowed = IMAGE_EXTS | {'.svg'} if allow_svg else IMAGE_EXTS
    subtype = content_type.split(';')[0].strip().lower().partition('/')[2]
    ext = _CT_EXTS.get(subtype) or (f'.{subtype}' if subtype else '')
    if ext not in allowed:
        ext = Path(urlsplit(url).path).suffix.lower()
    return ext if ext in allowed else default
