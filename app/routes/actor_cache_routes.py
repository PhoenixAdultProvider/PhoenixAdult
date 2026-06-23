from __future__ import annotations

import html
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.routes.env_auth import env_auth_guard
from app.utils.images import face_crop, face_crop_log
from app.utils.people.cache import actor_cache_dir, restore_original, set_gender

router = APIRouter(dependencies=[Depends(env_auth_guard)])

# gender key -> (css suffix, label)
_GENDERS = [('', 'gn', 'None'), ('male', 'gm', 'Male'), ('female', 'gf', 'Female')]


def _gender_of(filename: str) -> str:
    tail = Path(filename).stem.split('_')[-1]
    return tail if tail in ('male', 'female') else ''


def _gender_buttons(filename: str) -> str:
    cur = _gender_of(filename)
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
    upstream = str(entry.get('upstream_url', ''))
    cropped = bool(entry.get('cropped'))
    ts = html.escape(str(entry.get('ts', '')))
    gcss = next(css for key, css, _ in _GENDERS if key == _gender_of(filename))
    local_src = f'/images/local/{quote(filename)}'
    upstream_src = f'/images/proxy?url={quote(upstream, safe="")}'
    badge = '<span class="badge crop">cropped</span>' if cropped else '<span class="badge orig">original</span>'
    btn = (
        f'<button class="restore" onclick="restore({html.escape(filename, quote=True)!r})">Use original</button>'
        if cropped
        else '<button class="restore" disabled>Original kept</button>'
    )
    return f"""<div class="card {gcss}">
      <div class="hd"><b>{name}</b> {badge}<span class="ts">{ts}</span></div>
      <div class="imgs">
        <figure><figcaption>cached (shown in Plex)</figcaption><img src="{html.escape(local_src)}" loading="lazy"></figure>
        <figure><figcaption>upstream original</figcaption><img src="{html.escape(upstream_src)}" loading="lazy"></figure>
      </div>
      {_gender_buttons(filename)}
      {btn}
    </div>"""


@router.get('', response_class=HTMLResponse)
@router.get('/', response_class=HTMLResponse)
async def page(request: Request) -> HTMLResponse:
    entries = face_crop_log.recent(actor_cache_dir())
    token = html.escape(request.query_params.get('token', ''), quote=True)
    warn = '' if face_crop.available() else '<p class="warn">⚠ opencv-python-headless is not installed — face cropping is a no-op until you install it.</p>'
    empty = '<p class="empty">No cached crops yet. Enable <code>ACTOR_CACHE_ENABLE</code> + <code>ACTOR_CACHE_FACE_ENABLE</code>, then refresh a scene.</p>'
    cards = '\n'.join(_card(e) for e in entries) or empty
    body = f"""<!doctype html><html><head><meta charset="utf-8"><title>Actor image cache</title>
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
      .imgs{{display:flex;gap:10px}} figure{{margin:0;flex:1;text-align:center}}
      figcaption{{font-size:11px;color:#94a3b8;margin-bottom:4px}}
      img{{width:100%;height:170px;object-fit:contain;background:#0b0d12;border-radius:6px}}
      .gender{{display:flex;align-items:center;gap:6px;margin-top:10px;font-size:12px;color:#94a3b8}}
      .gender .g{{flex:1;margin:0;padding:5px;font-size:12px}}
      .g.gf.active{{background:#db2777}} .g.gm.active{{background:#2563eb}} .g.gn.active{{background:#64748b}}
      button{{margin-top:10px;width:100%;padding:7px;border:0;border-radius:6px;background:#2563eb;color:#fff;cursor:pointer}}
      button:disabled{{cursor:default;opacity:.7}}
      button.restore{{background:#2563eb}} button.restore:disabled{{background:#334155;color:#94a3b8;opacity:1}}
    </style></head><body>
    <h1>Actor image cache &mdash; recent crops</h1>
    <div class="sub">Newest first. "Use original" re-downloads the upstream image and replaces the crop (Plex may need a refresh).</div>
    {warn}
    <div class="grid">{cards}</div>
    <script>
      const TOKEN = {token!r};
      function hdrs(){{ return {{'Content-Type':'application/json', ...(TOKEN?{{'x-admin-token':TOKEN}}:{{}})}}; }}
      async function post(url, body){{
        const r = await fetch(url, {{method:'POST', headers:hdrs(), body:JSON.stringify(body)}});
        return r.json().catch(()=>({{ok:false}}));
      }}
      async function restore(filename){{
        const j = await post('/actor-cache/restore', {{filename}});
        if(j.ok) location.reload(); else alert('Restore failed');
      }}
      async function setGender(filename, gender){{
        const j = await post('/actor-cache/gender', {{filename, gender}});
        if(j.ok) location.reload(); else alert('Set gender failed');
      }}
    </script></body></html>"""
    return HTMLResponse(body)


@router.post('/restore')
async def restore(request: Request) -> JSONResponse:
    try:
        data = await request.json()
    except (ValueError, TypeError):
        data = {}
    filename = str(data.get('filename', '')) if isinstance(data, dict) else ''
    if not filename:
        return JSONResponse({'ok': False, 'error': 'missing filename'}, status_code=400)
    ok = await restore_original(filename)
    return JSONResponse({'ok': ok})


@router.post('/gender')
async def gender(request: Request) -> JSONResponse:
    try:
        data = await request.json()
    except (ValueError, TypeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    filename = str(data.get('filename', ''))
    new_gender = str(data.get('gender', ''))
    if not filename:
        return JSONResponse({'ok': False, 'error': 'missing filename'}, status_code=400)
    if new_gender not in ('', 'male', 'female'):
        return JSONResponse({'ok': False, 'error': 'invalid gender'}, status_code=400)
    new_filename = set_gender(filename, new_gender)
    return JSONResponse({'ok': new_filename is not None, 'filename': new_filename})
