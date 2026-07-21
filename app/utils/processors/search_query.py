from __future__ import annotations

from dataclasses import dataclass

from app.utils.processors.filename_parser import ParsedFilename, is_digit


@dataclass(frozen=True)
class SearchPieces:
    query: str | None
    full_title: str
    scene_id: str | None = None


def build_search_pieces(content_type: str, parsed: ParsedFilename) -> SearchPieces:
    full_title = ' '.join(p for p in (parsed.content, parsed.content2) if p).strip()
    scene_id = parsed.content if (parsed.content and is_digit(parsed.content)) else None

    if content_type == 'sceneId':
        query = full_title.split(' ')[0] or None
    elif content_type in ('sceneName', 'actors'):
        query = parsed.content2 or parsed.content or None
    elif content_type == 'sceneIdName':
        query = full_title or None
    else:
        query = None

    return SearchPieces(query=query, full_title=full_title, scene_id=scene_id)
