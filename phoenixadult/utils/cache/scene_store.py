from __future__ import annotations

import sqlite3
import time
from typing import Any

from phoenixadult.utils import db

_TAG_FIELDS = (
    ('Genre', 'scene_genres', 'genres', 'genre_id'),
    ('Collection', 'scene_collections', 'collections', 'collection_id'),
    ('Country', 'scene_countries', 'countries', 'country_id'),
)
_ROLE_FIELDS = (('Role', 'actor'), ('Director', 'director'), ('Producer', 'producer'), ('Writer', 'writer'))
_JUNCTIONS = ('scene_genres', 'scene_collections', 'scene_countries', 'scene_people', 'scene_images')

_SCENE_COLUMNS = (
    'hash',
    'site',
    'cur_id',
    'rel_path',
    'identifier',
    'rating_key',
    'guid',
    'title',
    'title_sort',
    'original_title',
    'summary',
    'release_date',
    'year',
    'duration',
    'rating',
    'audience_rating',
    'content_rating',
    'is_adult',
    'data18_type',
    'data18_id',
    'thumb',
    'art',
    'studio_id',
    'tagline_id',
    'updated_at',
)
_UPSERT = (
    f'INSERT INTO scenes({", ".join(_SCENE_COLUMNS)}) VALUES({", ".join("?" * len(_SCENE_COLUMNS))}) '
    f'ON CONFLICT(hash) DO UPDATE SET {", ".join(f"{c} = excluded.{c}" for c in _SCENE_COLUMNS[1:])}'
)


def _person_id(conn: sqlite3.Connection, name: str, studio_id: int | None, gender: str) -> int:
    """Scoped-identity resolution: the (name, scene's studio) row wins when it exists;
    otherwise the global row is used, created on first sight."""
    row = None
    if studio_id is not None:
        row = conn.execute('SELECT id, gender FROM people WHERE name = ? AND scope_studio_id = ?', (name, studio_id)).fetchone()
    if row is None:
        row = conn.execute('SELECT id, gender FROM people WHERE name = ? AND scope_studio_id IS NULL', (name,)).fetchone()
    if row is None:
        cur = conn.execute('INSERT INTO people(name, gender) VALUES(?, ?)', (name, gender))
        return int(cur.lastrowid or 0)
    person_id = int(row['id'])
    if gender and not row['gender']:
        conn.execute('UPDATE people SET gender = ? WHERE id = ?', (gender, person_id))
    return person_id


def upsert(
    site: str,
    cur_id: str,
    scene_hash: str,
    rel_path: str,
    data: dict[str, Any],
    image_meta: dict[str, tuple[int, int, int]] | None = None,
    updated_at: float | None = None,
) -> None:
    """Decompose one frozen PlexMetadataResponse dict into the relational scene tables
    (dimensions via INSERT OR IGNORE + id lookup), one transaction per scene."""
    container = data.get('MediaContainer') or {}
    metadata = container.get('Metadata') or [{}]
    md: dict[str, Any] = metadata[0] if isinstance(metadata[0], dict) else {}
    dims = image_meta or {}
    conn = db.connect()
    with conn:
        studio_id = db.dim_id(conn, 'studios', str(md.get('studio') or ''))
        tagline_id = db.dim_id(conn, 'taglines', str(md.get('tagline') or ''))
        d18 = md.get('data18') or {}
        is_adult = md.get('isAdult')
        conn.execute(
            _UPSERT,
            (
                scene_hash,
                site,
                cur_id,
                rel_path,
                str(container.get('identifier') or ''),
                str(md.get('ratingKey') or ''),
                str(md.get('guid') or ''),
                str(md.get('title') or ''),
                md.get('titleSort'),
                md.get('originalTitle'),
                md.get('summary'),
                md.get('originallyAvailableAt'),
                md.get('year'),
                md.get('duration'),
                md.get('rating'),
                md.get('audienceRating'),
                md.get('contentRating'),
                None if is_adult is None else int(bool(is_adult)),
                d18.get('type'),
                d18.get('id'),
                md.get('thumb'),
                md.get('art'),
                studio_id,
                tagline_id,
                time.time() if updated_at is None else updated_at,
            ),
        )
        scene_id = int(conn.execute('SELECT id FROM scenes WHERE hash = ?', (scene_hash,)).fetchone()['id'])
        for table in _JUNCTIONS:
            conn.execute(f'DELETE FROM {table} WHERE scene_id = ?', (scene_id,))
        for field, table, dim_table, dim_col in _TAG_FIELDS:
            tags = [t for t in ((entry or {}).get('tag') for entry in md.get(field) or []) if t]
            conn.executemany(
                f'INSERT OR IGNORE INTO {table}(scene_id, {dim_col}, pos) VALUES(?, ?, ?)',
                [(scene_id, db.dim_id(conn, dim_table, str(tag)), pos) for pos, tag in enumerate(tags)],
            )
        for field, role in _ROLE_FIELDS:
            for pos, entry in enumerate(md.get(field) or []):
                name = str((entry or {}).get('tag') or '')
                if not name:
                    continue
                person_id = _person_id(conn, name, studio_id, str(entry.get('gender') or ''))
                conn.execute(
                    'INSERT OR IGNORE INTO scene_people(scene_id, person_id, role, part, pos, photo_rel_path) VALUES(?, ?, ?, ?, ?, ?)',
                    (scene_id, person_id, role, entry.get('role'), pos, entry.get('thumb')),
                )
        for pos, img in enumerate(md.get('Image') or []):
            url = str((img or {}).get('url') or '')
            if not url:
                continue
            width, height, size = dims.get(url, (None, None, None))
            conn.execute(
                'INSERT INTO scene_images(scene_id, kind, rel_path, width, height, bytes, pos) VALUES(?, ?, ?, ?, ?, ?, ?)',
                (scene_id, str(img.get('type') or ''), url, width, height, size, pos),
            )


def _tag_list(conn: sqlite3.Connection, scene_id: int, table: str, dim_table: str, dim_col: str) -> list[str]:
    rows = conn.execute(f'SELECT d.name FROM {table} j JOIN {dim_table} d ON d.id = j.{dim_col} WHERE j.scene_id = ? ORDER BY j.pos', (scene_id,)).fetchall()
    return [str(r['name']) for r in rows]


def _people_lists(conn: sqlite3.Connection, scene_id: int) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {role: [] for _field, role in _ROLE_FIELDS}
    rows = conn.execute(
        'SELECT sp.role, sp.part, sp.photo_rel_path, p.name, p.gender FROM scene_people sp '
        'JOIN people p ON p.id = sp.person_id WHERE sp.scene_id = ? ORDER BY sp.pos',
        (scene_id,),
    ).fetchall()
    for row in rows:
        people = out.setdefault(str(row['role']), [])
        person: dict[str, Any] = {'tag': row['name']}
        if row['part']:
            person['role'] = row['part']
        if row['photo_rel_path']:
            person['thumb'] = row['photo_rel_path']
        if row['gender']:
            person['gender'] = row['gender']
        person['order'] = len(people)
        people.append(person)
    return out


def _image_list(conn: sqlite3.Connection, scene_id: int) -> list[dict[str, str]]:
    """Each image kind is emitted highest resolution first (unknown dimensions last),
    kinds keeping their stored relative order."""
    rows = conn.execute('SELECT kind, rel_path, width, height, pos FROM scene_images WHERE scene_id = ? ORDER BY pos', (scene_id,)).fetchall()
    first_pos: dict[str, int] = {}
    for row in rows:
        first_pos.setdefault(str(row['kind']), int(row['pos']))
    ordered = sorted(rows, key=lambda r: (first_pos[str(r['kind'])], -(int(r['width'] or 0) * int(r['height'] or 0)), int(r['pos'])))
    return [{'url': str(r['rel_path']), 'type': str(r['kind'])} for r in ordered]


def load(scene_hash: str) -> dict[str, Any] | None:
    """Reassemble the frozen response dict for one scene, or None when it is not stored."""
    conn = db.connect()
    row = conn.execute(
        'SELECT s.*, st.name AS studio_name, tl.name AS tagline_name FROM scenes s '
        'LEFT JOIN studios st ON st.id = s.studio_id LEFT JOIN taglines tl ON tl.id = s.tagline_id WHERE s.hash = ?',
        (scene_hash,),
    ).fetchone()
    if row is None:
        return None
    scene_id = int(row['id'])
    md: dict[str, Any] = {'type': 'movie', 'ratingKey': row['rating_key'], 'guid': row['guid'], 'title': row['title']}
    for key, col in (('titleSort', 'title_sort'), ('originalTitle', 'original_title'), ('year', 'year'), ('summary', 'summary')):
        if row[col] is not None:
            md[key] = row[col]
    if row['tagline_name']:
        md['tagline'] = row['tagline_name']
    if row['data18_type']:
        md['data18'] = {'type': row['data18_type'], 'id': row['data18_id']}
    if row['content_rating'] is not None:
        md['contentRating'] = row['content_rating']
    if row['is_adult'] is not None:
        md['isAdult'] = bool(row['is_adult'])
    for key, col in (
        ('audienceRating', 'audience_rating'),
        ('rating', 'rating'),
        ('duration', 'duration'),
        ('originallyAvailableAt', 'release_date'),
        ('thumb', 'thumb'),
        ('art', 'art'),
    ):
        if row[col] is not None:
            md[key] = row[col]
    if row['studio_name']:
        md['studio'] = row['studio_name']
    tags = {field: _tag_list(conn, scene_id, table, dim_table, dim_col) for field, table, dim_table, dim_col in _TAG_FIELDS}
    md['Genre'] = [{'tag': t} for t in tags['Genre']]
    people = _people_lists(conn, scene_id)
    md['Role'] = people['actor']
    for field, role in (('Director', 'director'), ('Writer', 'writer'), ('Producer', 'producer')):
        if people[role]:
            md[field] = people[role]
    md['Image'] = _image_list(conn, scene_id)
    md['Collection'] = [{'tag': t} for t in tags['Collection']]
    if tags['Country']:
        md['Country'] = [{'tag': t} for t in tags['Country']]
    return {'MediaContainer': {'identifier': row['identifier'], 'size': 1, 'Metadata': [md]}}


def tags_for(site_name: str, cur_id: str) -> dict[str, list[str]] | None:
    """The reconcile-relevant tag lists for one stored scene, None when it is not stored."""
    from phoenixadult.utils.cache import _hash

    conn = db.connect()
    row = conn.execute('SELECT id FROM scenes WHERE hash = ?', (_hash(site_name, cur_id),)).fetchone()
    if row is None:
        return None
    scene_id = int(row['id'])
    out: dict[str, list[str]] = {
        'Collection': _tag_list(conn, scene_id, 'scene_collections', 'collections', 'collection_id'),
        'Genre': _tag_list(conn, scene_id, 'scene_genres', 'genres', 'genre_id'),
    }
    for field, role in (('Role', 'actor'), ('Director', 'director'), ('Producer', 'producer')):
        rows = conn.execute(
            'SELECT p.name FROM scene_people sp JOIN people p ON p.id = sp.person_id WHERE sp.scene_id = ? AND sp.role = ? ORDER BY sp.pos',
            (scene_id, role),
        ).fetchall()
        out[field] = [str(r['name']) for r in rows]
    return out


def has(scene_hash: str) -> bool:
    return db.connect().execute('SELECT 1 FROM scenes WHERE hash = ?', (scene_hash,)).fetchone() is not None


def delete(rel_path: str) -> bool:
    conn = db.connect()
    with conn:
        cur = conn.execute('DELETE FROM scenes WHERE rel_path = ?', (rel_path,))
    return bool(cur.rowcount)


def flag_people_changed(name: str) -> list[str]:
    """Mark every scene crediting `name` for a forced re-push, returning their titles. A cached
    serve freezes the headshot URL, so a re-cached image only reaches Plex once that URL is rebuilt."""
    conn = db.connect()
    with conn:
        rows = conn.execute(
            'SELECT s.hash, s.title FROM scenes s JOIN scene_people sp ON sp.scene_id = s.id JOIN people p ON p.id = sp.person_id WHERE p.name = ?',
            (name,),
        ).fetchall()
        if rows:
            conn.execute(f'UPDATE scenes SET force_refresh = 1 WHERE hash IN ({",".join("?" * len(rows))})', [r['hash'] for r in rows])
    return [str(r['title']) for r in rows]


def take_force_refresh(scene_hash: str) -> bool:
    conn = db.connect()
    with conn:
        cur = conn.execute('UPDATE scenes SET force_refresh = 0 WHERE hash = ? AND force_refresh = 1', (scene_hash,))
    return bool(cur.rowcount)


def identity_for(rel_path: str) -> tuple[str, str] | None:
    row = db.connect().execute('SELECT site, cur_id FROM scenes WHERE rel_path = ?', (rel_path,)).fetchone()
    return (str(row['site']), str(row['cur_id'])) if row else None


def site_scenes(site: str) -> list[dict[str, str]]:
    rows = db.connect().execute('SELECT cur_id, title, release_date, thumb FROM scenes WHERE site = ? ORDER BY title', (site,)).fetchall()
    return [{'cur_id': str(r['cur_id']), 'title': str(r['title']), 'release_date': str(r['release_date'] or ''), 'thumb': str(r['thumb'] or '')} for r in rows]


def scene_keys() -> list[tuple[str, str, str]]:
    """(hash, rel_path, rating_key) for every stored scene."""
    rows = db.connect().execute('SELECT hash, rel_path, rating_key FROM scenes').fetchall()
    return [(str(r['hash']), str(r['rel_path']), str(r['rating_key'])) for r in rows]


_SUMMARY_SELECT = (
    'SELECT s.id, s.rel_path, s.title, s.release_date, s.thumb, s.updated_at, s.data18_type, s.data18_id, '
    'st.name AS studio, tl.name AS tagline, COUNT(si.id) AS images '
)
_SUMMARY_TABLES = 'FROM scenes s LEFT JOIN studios st ON st.id = s.studio_id LEFT JOIN taglines tl ON tl.id = s.tagline_id'
_SUMMARY_IMAGES_JOIN = ' LEFT JOIN scene_images si ON si.scene_id = s.id'
_SORT_COLUMNS = {
    'title': 's.title',
    'studio': "COALESCE(st.name, '')",
    'tagline': "COALESCE(tl.name, '')",
    'release_date': "COALESCE(s.release_date, '')",
    'data18_id': "COALESCE(s.data18_id, '')",
    'updated_at': 's.updated_at',
}


def _summary_row(r: sqlite3.Row, collections: dict[int, list[str]]) -> dict[str, Any]:
    return {
        'rel_path': str(r['rel_path']),
        'title': str(r['title']),
        'studio': str(r['studio'] or ''),
        'tagline': str(r['tagline'] or ''),
        'collections': collections.get(int(r['id']), []),
        'release_date': str(r['release_date'] or ''),
        'thumb': str(r['thumb'] or ''),
        'images': int(r['images']),
        'updated_at': float(r['updated_at']),
        'data18_id': str(r['data18_id'] or ''),
        'data18_type': str(r['data18_type'] or ''),
    }


def _collections_for(conn: sqlite3.Connection, scene_ids: list[int]) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    if not scene_ids:
        return out
    marks = ','.join('?' * len(scene_ids))
    rows = conn.execute(
        f'SELECT sc.scene_id, c.name FROM scene_collections sc JOIN collections c ON c.id = sc.collection_id WHERE sc.scene_id IN ({marks}) ORDER BY sc.pos',
        scene_ids,
    ).fetchall()
    for row in rows:
        out.setdefault(int(row['scene_id']), []).append(str(row['name']))
    return out


_BLANK = '__blank__'


def _entry_filters(
    studio: str, query: str, year: str, month: str, day: str, tagline: str, collection: str, data18: str, dup_paths: list[str] | None
) -> tuple[str, list[Any]]:
    where: list[str] = []
    params: list[Any] = []
    if studio:
        where.append('st.name = ?')
        params.append(studio)
    if query:
        where.append("(s.title LIKE ? ESCAPE '\\' OR COALESCE(st.name, '') LIKE ? ESCAPE '\\' OR COALESCE(tl.name, '') LIKE ? ESCAPE '\\')")
        params.extend([db.like_contains(query)] * 3)
    if year == _BLANK:
        where.append("COALESCE(s.release_date, '') = ''")
    elif year:
        where.append('substr(s.release_date, 1, 4) = ?')
        params.append(year)
    if month:
        where.append('substr(s.release_date, 6, 2) = ?')
        params.append(month)
    if day:
        where.append('substr(s.release_date, 9, 2) = ?')
        params.append(day)
    if tagline == _BLANK:
        where.append('s.tagline_id IS NULL')
    elif tagline:
        where.append('tl.name = ?')
        params.append(tagline)
    if collection == _BLANK:
        where.append('NOT EXISTS (SELECT 1 FROM scene_collections sc WHERE sc.scene_id = s.id)')
    elif collection:
        where.append('EXISTS (SELECT 1 FROM scene_collections sc JOIN collections c ON c.id = sc.collection_id WHERE sc.scene_id = s.id AND c.name = ?)')
        params.append(collection)
    if data18 == '__set__':
        where.append("COALESCE(s.data18_id, '') != ''")
    elif data18 == _BLANK:
        where.append("COALESCE(s.data18_id, '') = ''")
    if dup_paths is not None:
        if dup_paths:
            where.append(f's.rel_path IN ({",".join("?" * len(dup_paths))})')
            params.extend(dup_paths)
        else:
            where.append('1 = 0')
    return (f' WHERE {" AND ".join(where)}' if where else ''), params


def query_entry_rows(
    *,
    studio: str = '',
    query: str = '',
    year: str = '',
    month: str = '',
    day: str = '',
    tagline: str = '',
    collection: str = '',
    data18: str = '',
    dup_paths: list[str] | None = None,
    sort: str = 'updated_at',
    direction: str = 'desc',
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """One filtered/sorted/paged set of per-scene summary rows for the /metadata UI plus the
    total match count; every filter runs in SQL so pages and totals agree (limit -1 = all)."""
    conn = db.connect()
    where_sql, params = _entry_filters(studio, query, year, month, day, tagline, collection, data18, dup_paths)
    total = int(conn.execute(f'SELECT COUNT(*) AS count {_SUMMARY_TABLES}{where_sql}', params).fetchone()['count'])
    order_col = _SORT_COLUMNS.get(sort, 's.updated_at')
    order_dir = 'ASC' if direction == 'asc' else 'DESC'
    rows = conn.execute(
        f'{_SUMMARY_SELECT}{_SUMMARY_TABLES}{_SUMMARY_IMAGES_JOIN}{where_sql} GROUP BY s.id ORDER BY {order_col} {order_dir}, s.id LIMIT ? OFFSET ?',
        [*params, limit, offset],
    ).fetchall()
    collections = _collections_for(conn, [int(r['id']) for r in rows])
    return [_summary_row(r, collections) for r in rows], total


def facet_values() -> dict[str, Any]:
    """Distinct facet options across ALL stored scenes, for the /metadata dropdowns."""
    conn = db.connect()

    def names(sql: str) -> list[str]:
        return [str(r[0]) for r in conn.execute(sql).fetchall()]

    def exists(sql: str) -> bool:
        return int(conn.execute(f'SELECT EXISTS ({sql})').fetchone()[0]) == 1

    return {
        'taglines': names('SELECT DISTINCT tl.name FROM scenes s JOIN taglines tl ON tl.id = s.tagline_id ORDER BY tl.name'),
        'tagline_blank': exists('SELECT 1 FROM scenes WHERE tagline_id IS NULL'),
        'collections': names('SELECT DISTINCT c.name FROM scene_collections sc JOIN collections c ON c.id = sc.collection_id ORDER BY c.name'),
        'collection_blank': exists('SELECT 1 FROM scenes s WHERE NOT EXISTS (SELECT 1 FROM scene_collections sc WHERE sc.scene_id = s.id)'),
        'years': names("SELECT DISTINCT substr(release_date, 1, 4) FROM scenes WHERE COALESCE(release_date, '') != '' ORDER BY 1 DESC"),
        'year_blank': exists("SELECT 1 FROM scenes WHERE COALESCE(release_date, '') = ''"),
        'months': names("SELECT DISTINCT substr(release_date, 6, 2) FROM scenes WHERE COALESCE(release_date, '') != '' ORDER BY 1"),
        'days': names("SELECT DISTINCT substr(release_date, 9, 2) FROM scenes WHERE COALESCE(release_date, '') != '' ORDER BY 1"),
    }


def studio_names() -> list[str]:
    """Distinct studio names across stored scenes, alphabetical."""
    rows = db.connect().execute(f'SELECT DISTINCT st.name AS name {_SUMMARY_TABLES} WHERE st.name IS NOT NULL ORDER BY st.name').fetchall()
    return [str(r['name']) for r in rows]


def change_token() -> str:
    row = db.connect().execute('SELECT COUNT(*) AS count, COALESCE(MAX(updated_at), 0) AS newest FROM scenes').fetchone()
    return f'{int(row["count"])}:{float(row["newest"])}'
