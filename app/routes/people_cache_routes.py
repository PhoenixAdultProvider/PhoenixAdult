from __future__ import annotations

import html
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import people_image_base
from app.config.env import env
from app.routes import read_json_body
from app.utils.auth.env_auth import env_auth_guard
from app.utils.images import face_crop, face_crop_log
from app.utils.images.ext import IMAGE_EXTS
from app.utils.people.cache import _ORIGINALS_DIR, people_cache_dir, purge, restore_original, set_gender
from app.utils.people.types import parse_person_filename

router = APIRouter(dependencies=[Depends(env_auth_guard)])

_ROLES = ('actor', 'director', 'producer')
# gender key -> (css suffix, label)
_GENDERS = [('', 'gn', 'None'), ('male', 'gm', 'Male'), ('female', 'gf', 'Female')]
_ROLE_CSS = {'actor': 'r-actor', 'director': 'r-director', 'producer': 'r-producer'}
# (subfolder-derived type, tab label) — one view per storage bucket.
_TABS = [
    ('directors', 'Directors'),
    ('producers', 'Producers'),
    ('actors-female', 'Female Actors'),
    ('actors-male', 'Male Actors'),
    ('actors-trans', 'Trans Actors'),
    ('actors-unknown', 'Unknown Actors'),
]


def _parse_filename(filename: str) -> tuple[str, str, str] | None:
    """(role, display_name, gender) from `role.slug[_gender].ext`; None if not a person file."""
    role, slug, gender = parse_person_filename(filename)
    if role not in _ROLES or not slug:
        return None
    return role, slug.replace('-', ' ').title(), gender


def _list_people(directory: str) -> list[dict[str, Any]]:
    """Every cached headshot across the role/gender subfolders, newest first, enriched with
    each subfolder's crop-log metadata. The originals/ backing store is skipped. Each entry
    carries its relpath (for the served URL) and a `type` (the tab it belongs to)."""
    root = Path(directory)
    if not root.exists():
        return []
    subdirs = sorted({f.parent for f in root.rglob('*') if f.is_file() and not f.name.startswith('.') and f.suffix.lower() in IMAGE_EXTS})
    out: list[dict[str, Any]] = []
    for sd in subdirs:
        subpath = sd.relative_to(root).as_posix()
        if subpath == _ORIGINALS_DIR or subpath.startswith(f'{_ORIGINALS_DIR}/'):
            continue
        by_file = {e.get('filename'): e for e in face_crop_log.recent(str(sd))}
        for f in sorted(sd.iterdir()):
            if not f.is_file() or f.name.startswith('.') or f.suffix.lower() not in IMAGE_EXTS:
                continue
            parsed = _parse_filename(f.name)
            if not parsed:
                continue
            role, name, gender = parsed
            log = by_file.get(f.name, {})
            try:
                mtime = f.stat().st_mtime
            except OSError:
                mtime = 0.0
            out.append(
                {
                    'name': log.get('name') or name,
                    'filename': f.name,
                    'relpath': f'{subpath}/{f.name}',
                    'type': subpath.replace('/', '-'),
                    'role': role,
                    'gender': gender,
                    'upstream_url': log.get('upstream_url', ''),
                    'cropped': bool(log.get('cropped')),
                    'ts': log.get('ts') or datetime.fromtimestamp(mtime, UTC).strftime('%Y-%m-%d %H:%M:%S'),
                    'mtime': mtime,
                }
            )
    out.sort(key=lambda e: e['mtime'], reverse=True)
    return out


def _gender_of(gender: str) -> str:
    return gender if gender in ('male', 'female') else ''


def _gender_buttons(filename: str, gender: str) -> str:
    cur = _gender_of(gender)
    fn = html.escape(filename, quote=True)
    out = []
    for key, css, label in _GENDERS:
        active = ' active' if key == cur else ''
        dis = ' disabled' if key == cur else ''
        out.append(f'<button class="g {css}{active}" onclick="setGender({fn!r}, \'{key}\')"{dis}>{label}</button>')
    return f'<div class="gender"><span>Gender:</span>{"".join(out)}</div>'


def _card(entry: dict[str, Any]) -> str:
    name = html.escape(str(entry.get('name', '')))
    filename = str(entry.get('filename', ''))
    role = str(entry.get('role', ''))
    upstream = str(entry.get('upstream_url', ''))
    cropped = bool(entry.get('cropped'))
    ts = html.escape(str(entry.get('ts', '')))
    gcss = next(css for key, css, _ in _GENDERS if key == _gender_of(str(entry.get('gender', ''))))
    relpath = str(entry.get('relpath', filename))
    ctype = html.escape(str(entry.get('type', '')), quote=True)
    local_src = f'/images/local/{quote(relpath, safe="/")}?v={int(entry.get("mtime", 0))}'  # bust the browser cache when the file changes
    role_badge = f'<span class="role {_ROLE_CSS.get(role, "")}">{html.escape(role)}</span>'
    crop_badge = '<span class="badge crop">cropped</span>' if cropped else '<span class="badge orig">original</span>'
    fn = html.escape(filename, quote=True)
    if upstream:
        upstream_fig = f'<figure><figcaption>upstream original</figcaption><img src="/images/proxy?url={quote(upstream, safe="")}" loading="lazy"></figure>'
        restore_btn = (
            f'<button class="restore" onclick="restore({fn!r})">Use original</button>' if cropped else '<button class="restore" disabled>Original kept</button>'
        )
    else:
        upstream_fig = ''
        restore_btn = '<button class="restore" disabled>No upstream recorded</button>'
    purge_btn = f'<button class="purge" onclick="purge({fn!r})">Purge</button>'
    return f"""<div class="card {gcss}" data-type="{ctype}">
      <div class="hd">{role_badge}<b>{name}</b> {crop_badge}<span class="ts">{ts}</span></div>
      <div class="imgs">
        <figure><figcaption>cached (shown in Plex)</figcaption><img src="{html.escape(local_src)}" loading="lazy"></figure>
        {upstream_fig}
      </div>
      {_gender_buttons(filename, str(entry.get('gender', '')))}
      <div class="actions">{restore_btn}{purge_btn}</div>
    </div>"""


@router.get('', response_class=HTMLResponse)
@router.get('/', response_class=HTMLResponse)
async def page(request: Request) -> HTMLResponse:
    entries = _list_people(people_cache_dir())
    type_counts = {t: sum(1 for e in entries if e['type'] == t) for t, _ in _TABS}
    default_tab = next((t for t, _ in _TABS if type_counts[t]), _TABS[0][0])
    token = html.escape(request.query_params.get('token', ''), quote=True)
    warn = '' if face_crop.available() else '<p class="warn">⚠ opencv-python-headless is not installed — face cropping is a no-op until you install it.</p>'
    empty = '<p class="empty">No cached people yet. Enable <code>PEOPLE_CACHE_ENABLE</code>, then refresh a scene.</p>' if not entries else ''
    summary = ' · '.join(f'{type_counts[t]} {label.lower()}' for t, label in _TABS if type_counts[t]) or 'none yet'
    img_base = html.escape(people_image_base())
    img_opt = html.escape(env.people_image_url_raw)
    tabs = ''.join(
        f'<button class="tab" data-t="{t}" onclick="showTab({t!r})">{label} <span class="cnt">{type_counts[t]}</span></button>' for t, label in _TABS
    )
    cards = '\n'.join(_card(e) for e in entries)
    body = f"""<!doctype html><html><head><meta charset="utf-8"><title>People image cache</title>
    <style>
      body{{font-family:system-ui,sans-serif;background:#0f1117;color:#e2e8f0;margin:0;padding:24px}}
      h1{{font-size:20px}} .sub{{color:#94a3b8;font-size:13px;margin-bottom:20px}}
      .warn{{background:#3b1d1d;border:1px solid #b91c1c;padding:8px 12px;border-radius:6px}}
      .empty{{color:#94a3b8}}
      .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:16px}}
      .card{{background:#1e2433;border:1px solid #334155;border-left:5px solid #475569;border-radius:8px;padding:12px}}
      .card.gf{{border-left-color:#db2777;background:#241a20}}
      .card.gm{{border-left-color:#2563eb;background:#1a1f2e}}
      .card.gn{{border-left-color:#64748b}}
      .hd{{display:flex;align-items:center;gap:8px;margin-bottom:8px}} .ts{{margin-left:auto;color:#64748b;font-size:12px}}
      .badge{{font-size:11px;padding:1px 7px;border-radius:10px}} .badge.crop{{background:#1e3a8a}} .badge.orig{{background:#334155}}
      .role{{font-size:11px;padding:1px 7px;border-radius:10px;text-transform:capitalize;background:#475569}}
      .role.r-actor{{background:#0e7490}} .role.r-director{{background:#7c3aed}} .role.r-producer{{background:#b45309}}
      .imgs{{display:flex;gap:10px}} figure{{margin:0;flex:1;text-align:center}}
      figcaption{{font-size:11px;color:#94a3b8;margin-bottom:4px}}
      img{{width:100%;height:170px;object-fit:contain;background:#0b0d12;border-radius:6px}}
      .gender{{display:flex;align-items:center;gap:6px;margin-top:10px;font-size:12px;color:#94a3b8}}
      .gender .g{{flex:1;margin:0;padding:5px;font-size:12px}}
      .g.gf.active{{background:#db2777}} .g.gm.active{{background:#2563eb}} .g.gn.active{{background:#64748b}}
      button{{margin-top:10px;width:100%;padding:7px;border:0;border-radius:6px;background:#2563eb;color:#fff;cursor:pointer}}
      button:disabled{{cursor:default;opacity:.7}}
      .actions{{display:flex;gap:8px}}
      button.restore{{background:#2563eb;flex:1}} button.restore:disabled{{background:#334155;color:#94a3b8;opacity:1}}
      button.purge{{background:#b91c1c;flex:0 0 90px}}
      .tabs{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}}
      .tab{{width:auto;margin:0;padding:6px 12px;background:#1e2433;border:1px solid #334155;color:#94a3b8}}
      .tab.active{{background:#2563eb;color:#fff;border-color:#2563eb}}
      .tab .cnt{{opacity:.65;font-size:11px}}
    </style></head><body>
    <h1>People image cache</h1>
    <div class="sub">Cached cast &amp; crew headshots ({summary}). Newest first.
      "Use original" restores the preserved pre-crop original (Plex may need a refresh).
      <br>Serving people images via <code>PEOPLE_IMAGE_URL={img_opt}</code> → <code>{img_base}</code></div>
    {warn}
    <div class="tabs">{tabs}</div>
    <div class="grid">{cards}</div>
    <p class="empty viewempty" style="display:none">No images in this category.</p>
    {empty}
    <script>
      const TOKEN = {token!r};
      function hdrs(){{ return {{'Content-Type':'application/json', ...(TOKEN?{{'x-admin-token':TOKEN}}:{{}})}}; }}
      async function post(url, body){{
        const r = await fetch(url, {{method:'POST', headers:hdrs(), body:JSON.stringify(body)}});
        return r.json().catch(()=>({{ok:false}}));
      }}
      async function restore(filename){{
        const j = await post('/people-cache/restore', {{filename}});
        if(j.ok) location.reload(); else alert('Restore failed');
      }}
      async function setGender(filename, gender){{
        const j = await post('/people-cache/gender', {{filename, gender}});
        if(j.ok) location.reload(); else alert('Set gender failed');
      }}
      async function purge(filename){{
        if(!confirm('Delete '+filename+' from the local cache?')) return;
        const j = await post('/people-cache/purge', {{filename}});
        if(j.ok) location.reload(); else alert('Purge failed');
      }}
      function showTab(t){{
        document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('active', b.dataset.t===t));
        let n=0;
        document.querySelectorAll('.card').forEach(c=>{{ const m=c.dataset.type===t; c.style.display=m?'':'none'; if(m)n++; }});
        const ve=document.querySelector('.viewempty'); if(ve) ve.style.display=n?'none':'';
      }}
      showTab({default_tab!r});
    </script></body></html>"""
    return HTMLResponse(body)


@router.post('/restore')
async def restore(request: Request) -> JSONResponse:
    data = await read_json_body(request)
    filename = str(data.get('filename', ''))
    if not filename:
        return JSONResponse({'ok': False, 'error': 'missing filename'}, status_code=400)
    ok = await restore_original(filename)
    return JSONResponse({'ok': ok})


@router.post('/purge')
async def purge_file(request: Request) -> JSONResponse:
    data = await read_json_body(request)
    filename = str(data.get('filename', ''))
    if not filename:
        return JSONResponse({'ok': False, 'error': 'missing filename'}, status_code=400)
    return JSONResponse({'ok': purge(filename)})


@router.post('/gender')
async def gender(request: Request) -> JSONResponse:
    data = await read_json_body(request)
    filename = str(data.get('filename', ''))
    new_gender = str(data.get('gender', ''))
    if not filename:
        return JSONResponse({'ok': False, 'error': 'missing filename'}, status_code=400)
    if new_gender not in ('', 'male', 'female'):
        return JSONResponse({'ok': False, 'error': 'invalid gender'}, status_code=400)
    new_filename = set_gender(filename, new_gender)
    return JSONResponse({'ok': new_filename is not None, 'filename': new_filename})
