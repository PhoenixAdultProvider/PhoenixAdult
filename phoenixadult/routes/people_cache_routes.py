from __future__ import annotations

import asyncio
import html
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from phoenixadult.config import image_base_url
from phoenixadult.config.env import env
from phoenixadult.routes import read_json_body
from phoenixadult.utils.auth.env_auth import csrf_guard, env_auth_guard
from phoenixadult.utils.cache import scene_store
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.helpers.helpers import load_data
from phoenixadult.utils.images import face_crop, face_crop_log
from phoenixadult.utils.images.ext import IMAGE_EXTS
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.people.cache import _ORIGINALS_DIR, _index_conn, cache_photo, people_cache_dir, purge, restore_original, set_gender
from phoenixadult.utils.people.sources import ALL_SOURCES
from phoenixadult.utils.people.sources.localStorage import local_storage_source
from phoenixadult.utils.people.types import Gender, PersonLookupContext, PersonSource, parse_person_filename

router = APIRouter(dependencies=[Depends(env_auth_guard), Depends(csrf_guard)])

_EDIT_TEMPLATE: str = load_data(__file__, 'people_edit', kind='html')
FETCHABLE_SOURCES = [source for source in ALL_SOURCES if source.name != local_storage_source.name]
_BULK_CONCURRENCY = 3
_BULK_MAX = 250


def _json_attr(value: object) -> str:
    return json.dumps(value).replace('<', '\\u003c')


_ROLES = ('actor', 'director', 'producer')
_GENDERS = [('', 'gn', 'None'), ('male', 'gm', 'Male'), ('female', 'gf', 'Female'), ('trans', 'gt', 'Trans')]
_ROLE_CSS = {'actor': 'r-actor', 'director': 'r-director', 'producer': 'r-producer'}
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


def _entry(relpath: str, mtime: float, log: dict[str, Any]) -> dict[str, Any] | None:
    subpath, _, filename = relpath.rpartition('/')
    parsed = _parse_filename(filename)
    if not parsed:
        return None
    role, name, gender = parsed
    return {
        'name': log.get('name') or name,
        'filename': filename,
        'relpath': relpath,
        'type': subpath.replace('/', '-'),
        'role': role,
        'gender': gender,
        'upstream_url': log.get('upstream_url', ''),
        'source': log.get('source', ''),
        'cropped': bool(log.get('cropped')),
        'ts': log.get('ts') or datetime.fromtimestamp(mtime, UTC).strftime('%Y-%m-%d %H:%M:%S'),
        'mtime': mtime,
    }


def _list_people(directory: str) -> list[dict[str, Any]]:
    """Every cached headshot (originals/ excluded) from the people_images index merged with crop-log
    metadata, newest first; entries carry relpath (served URL) and `type` (tab)."""
    rows = _index_conn().execute('SELECT rel_path, mtime FROM people_images ORDER BY rel_path').fetchall()
    if not rows:
        return _list_people_files(directory)
    logs = face_crop_log.entries_by_path()
    out = [_entry(str(r['rel_path']), float(r['mtime']), logs.get(str(r['rel_path']), {})) for r in rows]
    kept = [e for e in out if e is not None]
    kept.sort(key=lambda e: e['mtime'], reverse=True)
    return kept


def _list_people_files(directory: str) -> list[dict[str, Any]]:
    """Filesystem fallback for an empty index: walk the role/gender subfolders directly."""
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
            try:
                mtime = f.stat().st_mtime
            except OSError:
                mtime = 0.0
            entry = _entry(f'{subpath}/{f.name}', mtime, by_file.get(f.name) or {})
            if entry is not None:
                out.append(entry)
    out.sort(key=lambda e: e['mtime'], reverse=True)
    return out


def _gender_of(gender: str) -> Gender:
    match gender:
        case 'male' | 'female' | 'trans':
            return gender
        case _:
            return ''


def _gender_buttons(gender: str) -> str:
    cur = _gender_of(gender)
    out = []
    for key, css, label in _GENDERS:
        active = ' active' if key == cur else ''
        dis = ' disabled' if key == cur else ''
        out.append(f'<button class="g {css}{active}" data-g="{key}"{dis}>{label}</button>')
    return f'<div class="gender"><span>Gender:</span>{"".join(out)}</div>'


def _card(entry: dict[str, Any]) -> str:
    name = html.escape(str(entry.get('name', '')))
    filename = str(entry.get('filename', ''))
    role = str(entry.get('role', ''))
    upstream = str(entry.get('upstream_url', ''))
    cropped = bool(entry.get('cropped'))
    timestamp = html.escape(str(entry.get('ts', '')))
    gcss = next(css for key, css, _ in _GENDERS if key == _gender_of(str(entry.get('gender', ''))))
    relpath = str(entry.get('relpath', filename))
    ctype = html.escape(str(entry.get('type', '')), quote=True)
    local_src = f'/images/local/{quote(relpath, safe="/")}?v={int(entry.get("mtime", 0))}'
    role_badge = f'<span class="role {_ROLE_CSS.get(role, "")}">{html.escape(role)}</span>'
    crop_badge = '<span class="badge crop">cropped</span>' if cropped else '<span class="badge orig">original</span>'
    source = str(entry.get('source', ''))
    source_badge = f'<span class="badge src">{html.escape(source)}</span>' if source else ''
    filename_attr = html.escape(filename, quote=True)
    if upstream:
        upstream_fig = f'<figure><figcaption>Upstream Original</figcaption><img src="/images/proxy?url={quote(upstream, safe="")}" loading="lazy"></figure>'
        restore_btn = '<button class="restore">Use Original</button>' if cropped else '<button class="restore" disabled>Original Kept</button>'
    else:
        upstream_fig = ''
        restore_btn = '<button class="restore" disabled>No Upstream Recorded</button>'
    edit_btn = '<button class="edit">Edit</button>'
    purge_btn = '<button class="purge">Purge</button>'
    search_key = html.escape(str(entry.get('name', '')).casefold(), quote=True)
    flags = f'data-cropped="{1 if cropped else 0}" data-name="{search_key}" data-upstream="{1 if upstream else 0}"'
    return f"""<div class="card {gcss}" data-type="{ctype}" data-fn="{filename_attr}" {flags}>
      <div class="hd">{role_badge}<b>{name}</b> {crop_badge}{source_badge}<span class="ts">{timestamp}</span></div>
      <div class="imgs">
        <figure><figcaption>Cached (Shown in Plex)</figcaption><img src="{html.escape(local_src)}" loading="lazy"></figure>
        {upstream_fig}
      </div>
      {_gender_buttons(str(entry.get('gender', '')))}
      <div class="actions">{restore_btn}{edit_btn}{purge_btn}</div>
    </div>"""


@router.get('', response_class=HTMLResponse)
@router.get('/', response_class=HTMLResponse)
async def page(request: Request) -> HTMLResponse:
    entries = await run_in('store', _list_people, people_cache_dir())
    type_counts = {t: sum(1 for e in entries if e['type'] == t) for t, _ in _TABS}
    default_tab = next((t for t, _ in _TABS if type_counts[t]), _TABS[0][0])
    token = html.escape(request.query_params.get('token', ''), quote=True)
    warn = '' if face_crop.available() else '<p class="warn">⚠ opencv-python-headless is not installed — face cropping is a no-op until you install it.</p>'
    empty = '<p class="empty">No cached people yet. Enable <code>PEOPLE_CACHE_ENABLE</code>, then refresh a scene.</p>' if not entries else ''
    summary = ' · '.join(f'{type_counts[t]} {label.lower()}' for t, label in _TABS if type_counts[t]) or 'none yet'
    img_base = html.escape(image_base_url())
    img_opt = html.escape(env.image_base_url_raw)
    tabs = ''.join(
        f'<button class="tab" data-t="{t}" data-label="{label}" onclick="showTab({t!r})">{label} <span class="cnt">{type_counts[t]}</span></button>'
        for t, label in _TABS
    )
    cards = '\n'.join(_card(e) for e in entries)
    source_options = ''.join(f'<option value="{html.escape(s.name, quote=True)}">{html.escape(s.name)}</option>' for s in FETCHABLE_SOURCES)
    body = f"""<!doctype html><html><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0"><title>People Cache</title>
    <style>
      body{{font-family:system-ui,sans-serif;background:#0f1117;color:#e2e8f0;margin:0;padding:24px}}
      h1{{font-size:20px}} .sub{{color:#94a3b8;font-size:13px;margin-bottom:20px}}
      .warn{{background:#3b1d1d;border:1px solid #b91c1c;padding:8px 12px;border-radius:6px}}
      .empty{{color:#94a3b8}}
      .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:16px}}
      .card{{background:#1e2433;border:1px solid #334155;border-left:5px solid #475569;border-radius:8px;padding:12px;display:none}}
      .card.gf{{border-left-color:#db2777;background:#241a20}}
      .card.gm{{border-left-color:#2563eb;background:#1a1f2e}}
      .card.gt{{border-left-color:#9333ea;background:#211a2e}}
      .card.gn{{border-left-color:#64748b}}
      .hd{{display:flex;align-items:center;gap:8px;margin-bottom:8px}} .ts{{margin-left:auto;color:#64748b;font-size:12px}}
      .badge{{font-size:11px;padding:1px 7px;border-radius:10px}} .badge.crop{{background:#1e3a8a}} .badge.orig{{background:#334155}}
      .badge.src{{background:#0f172a;border:1px solid #334155;color:#94a3b8}}
      .role{{font-size:11px;padding:1px 7px;border-radius:10px;text-transform:capitalize;background:#475569}}
      .role.r-actor{{background:#0e7490}} .role.r-director{{background:#7c3aed}} .role.r-producer{{background:#b45309}}
      .imgs{{display:flex;gap:10px}} figure{{margin:0;flex:1;text-align:center}}
      figcaption{{font-size:11px;color:#94a3b8;margin-bottom:4px}}
      img{{width:100%;height:170px;object-fit:contain;background:#0b0d12;border-radius:6px}}
      .gender{{display:flex;align-items:center;gap:6px;margin-top:10px;font-size:12px;color:#94a3b8}}
      .gender .g{{flex:1;margin:0;padding:5px;font-size:12px}}
      .g.gf.active{{background:#db2777}} .g.gm.active{{background:#2563eb}} .g.gt.active{{background:#9333ea}} .g.gn.active{{background:#64748b}}
      button{{margin-top:10px;width:100%;padding:7px;border:0;border-radius:6px;background:#2563eb;color:#fff;cursor:pointer}}
      button:disabled{{cursor:default;opacity:.7}}
      .actions{{display:flex;gap:8px}}
      button.restore{{background:#2563eb;flex:1}} button.restore:disabled{{background:#334155;color:#94a3b8;opacity:1}}
      button.edit{{background:#1e2433;border:1px solid #334155;color:#cbd5e1;flex:0 0 80px}}
      button.edit:hover{{background:#2563eb;border-color:#2563eb;color:#fff}}
      button.purge{{background:#b91c1c;flex:0 0 90px}}
      .search{{margin-bottom:16px}}
      .search input{{width:320px;max-width:100%;background:#1e2433;border:1px solid #334155;color:#e2e8f0;padding:7px 10px;border-radius:6px;font-size:13px}}
      .search input:focus{{outline:0;border-color:#2563eb}}
      .search .cnt{{color:#64748b;font-size:12px;margin-left:10px}}
      .search{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
      .search select{{background:#1e2433;border:1px solid #334155;color:#e2e8f0;padding:7px 10px;border-radius:6px;font-size:13px}}
      button.bulk{{width:auto;margin:0;padding:7px 16px;background:#1e2433;border:1px solid #334155;color:#cbd5e1}}
      button.bulk:hover{{background:#2563eb;border-color:#2563eb;color:#fff}}
      button.bulk:disabled{{background:#1e2433;color:#64748b}}
      .progress{{flex:1 1 220px;max-width:320px;height:8px;background:#1e2433;border:1px solid #334155;border-radius:6px;overflow:hidden}}
      .progress .fill{{height:100%;width:0;background:#2563eb;transition:width .15s linear}}
      .filters-toggle{{display:none}}
      .tabs{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}}
      .tab{{width:auto;margin:0;padding:6px 12px;background:#1e2433;border:1px solid #334155;color:#94a3b8}}
      .tab.active{{background:#2563eb;color:#fff;border-color:#2563eb}}
      .croptoggle{{margin-left:auto}} .croptoggle.on{{background:#1e3a8a;color:#fff;border-color:#3b82f6}}
      .noupstream.on{{background:#7c2d12;color:#fff;border-color:#ea580c}}
      .tab .cnt{{opacity:.65;font-size:11px}}
      @media (max-width:720px){{
        body{{padding:14px}}
        .grid{{grid-template-columns:1fr}}
        .actions{{flex-wrap:wrap}} button.edit,button.purge{{flex:1 1 auto}}
        .filters-toggle{{display:block;width:100%;margin:0 0 12px;padding:9px;border:1px solid #334155;
          border-radius:6px;background:#1e2433;color:#cbd5e1;font-size:13px;cursor:pointer}}
        .filters-toggle.on{{border-color:#2563eb;color:#e2e8f0}}
        .tabs{{display:none;flex-direction:column;gap:6px}}
        body.filters-open .tabs{{display:flex}}
        .tab{{width:100%}} .croptoggle{{margin-left:0}}
        .search{{gap:10px}}
        .search input{{width:100%;flex:1 1 100%}}
        .search>select,.search>button.bulk,.search>.progress,.search>#bulkStatus{{display:none}}
        body.filters-open .search>select,body.filters-open .search>button.bulk{{display:block;width:100%;max-width:none}}
        body.filters-open .search>.progress{{display:block;max-width:none;flex:1 1 100%}}
        body.filters-open .search>#bulkStatus{{display:block}}
        body.filters-open .search>.progress[hidden]{{display:none}}
      }}
    </style></head><body>
    <h1>People Cache</h1>
    <div class="sub">Cached cast &amp; crew headshots ({summary}). Newest first.
      "Use Original" restores the preserved pre-crop original (Plex may need a refresh).
      <br>Serving people images via <code>IMAGE_BASE_URL={img_opt}</code> → <code>{img_base}</code></div>
    {warn}
    <button class="filters-toggle" id="filtersToggle" onclick="toggleFilters()" aria-expanded="false"></button>
    <div class="tabs">{tabs}<button class="tab croptoggle" id="cropToggle">Cropped Only</button>
      <button class="tab noupstream" id="upstreamToggle">No Upstream</button></div>
    <div class="search"><input type="text" id="nameSearch" placeholder="Search names…" autocomplete="off"><span class="cnt" id="searchCount"></span>
      <select id="bulkSource">{source_options}</select>
      <button class="bulk" id="bulkBtn">Fetch Images for Shown</button>
      <div class="progress" id="bulkProgress" hidden><div class="fill" id="bulkFill"></div></div>
      <span class="cnt" id="bulkStatus"></span></div>
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
        const j = await post('/people/restore', {{filename}});
        if(j.ok) location.reload(); else alert('Restore failed');
      }}
      async function setGender(filename, gender){{
        const j = await post('/people/gender', {{filename, gender}});
        if(j.ok) location.reload(); else alert('Set gender failed');
      }}
      async function purge(filename){{
        if(!confirm('Delete '+filename+' from the local cache?')) return;
        const j = await post('/people/purge', {{filename}});
        if(j.ok) location.reload(); else alert('Purge failed');
      }}
      function edit(filename){{
        const p = new URLSearchParams({{filename}});
        if (TOKEN) p.set('token', TOKEN);
        location.href = '/people/edit?' + p.toString();
      }}
      const STORE_KEY = 'people-cache-filters';
      let croppedOnly = false;
      let noUpstreamOnly = false;
      let curTab = '';
      function saveFilters(){{
        const search = document.getElementById('nameSearch').value;
        try {{ localStorage.setItem(STORE_KEY, JSON.stringify({{croppedOnly, noUpstreamOnly, search}})); }} catch {{}}
      }}
      function restoreFilters(){{
        let saved;
        try {{ saved = JSON.parse(localStorage.getItem(STORE_KEY) || 'null'); }} catch {{}}
        if(!saved) return;
        croppedOnly = !!saved.croppedOnly;
        noUpstreamOnly = !!saved.noUpstreamOnly;
        document.getElementById('nameSearch').value = saved.search || '';
        document.getElementById('cropToggle').classList.toggle('on', croppedOnly);
        document.getElementById('upstreamToggle').classList.toggle('on', noUpstreamOnly);
      }}
      function showTab(t){{
        curTab = t;
        history.replaceState(null, '', '#'+t);  // remember the tab across a reload (purge/restore/gender)
        document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('active', b.dataset.t===t));
        const needle = (document.getElementById('nameSearch').value || '').trim().toLowerCase();
        let n=0;
        document.querySelectorAll('.card').forEach(c=>{{
          const m = c.dataset.type===t && (!croppedOnly || c.dataset.cropped==='1') && (!noUpstreamOnly || c.dataset.upstream==='0')
            && (!needle || (c.dataset.name||'').includes(needle));
          c.style.display=m?'block':'none'; if(m)n++;
        }});
        document.getElementById('searchCount').textContent = needle ? n+' match'+(n===1?'':'es') : '';
        const ve=document.querySelector('.viewempty'); if(ve) ve.style.display=n?'none':'';
        updateFiltersToggle();
        saveFilters();
      }}
      function toggleFilters(){{
        const open = document.body.classList.toggle('filters-open');
        document.getElementById('filtersToggle').setAttribute('aria-expanded', open ? 'true' : 'false');
      }}
      function updateFiltersToggle(){{
        const active = (croppedOnly?1:0) + (noUpstreamOnly?1:0);
        const tab = document.querySelector('.tab.active');
        const label = tab ? tab.dataset.label : 'People';
        const btn = document.getElementById('filtersToggle');
        btn.textContent = label + ' · Filters' + (active ? ' ('+active+' Active)' : '');
        btn.classList.toggle('on', active > 0);
      }}
      document.getElementById('nameSearch').addEventListener('input', () => showTab(curTab));
      function shownFilenames(){{
        return Array.from(document.querySelectorAll('.card'))
          .filter(c => c.style.display !== 'none')
          .map(c => c.dataset.fn)
          .filter(Boolean);
      }}
      function setProgress(done, total){{
        const bar = document.getElementById('bulkProgress');
        bar.hidden = false;
        document.getElementById('bulkFill').style.width = (total ? (done/total)*100 : 0)+'%';
      }}
      async function* ndjson(response){{
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buf = '';
        for(;;){{
          const {{done, value}} = await reader.read();
          buf += done ? '' : decoder.decode(value, {{stream:true}});
          let cut;
          while((cut = buf.indexOf('\\n')) >= 0){{
            const line = buf.slice(0, cut).trim();
            buf = buf.slice(cut+1);
            if(line) yield JSON.parse(line);
          }}
          if(done) return;
        }}
      }}
      document.getElementById('bulkBtn').addEventListener('click', async () => {{
        const btn = document.getElementById('bulkBtn');
        const status = document.getElementById('bulkStatus');
        const source = document.getElementById('bulkSource').value;
        const filenames = shownFilenames();
        if(!filenames.length){{ status.textContent = 'Nothing shown to fetch'; return; }}
        if(!confirm('Replace the cached image for '+filenames.length+' shown '+(filenames.length===1?'person':'people')+' using '+source+'?')) return;
        btn.disabled = true;
        setProgress(0, filenames.length);
        status.textContent = 'Fetching 0 of '+filenames.length+' from '+source+'…';
        let summary = null;
        try {{
          const r = await fetch('/people/bulk-fetch', {{method:'POST', headers:hdrs(), body:JSON.stringify({{source, filenames}})}});
          if(!r.ok) {{
            const err = await r.json().catch(()=>({{}}));
            throw new Error(err.error || 'Bulk fetch failed');
          }}
          for await (const msg of ndjson(r)){{
            if(msg.done){{
              setProgress(msg.done, msg.total);
              status.textContent = 'Fetching '+msg.done+' of '+msg.total+' from '+source+'…';
            }}
            if(msg.ok) summary = msg;
          }}
        }} catch(err) {{
          btn.disabled = false;
          document.getElementById('bulkProgress').hidden = true;
          status.textContent = String(err.message || err);
          return;
        }}
        btn.disabled = false;
        if(!summary) {{ status.textContent = 'Bulk fetch ended early'; return; }}
        setProgress(1, 1);
        const parts = [summary.updated+' updated', summary.missed+' not found'];
        if(summary.failed) parts.push(summary.failed+' failed');
        if(summary.truncated) parts.push(summary.truncated+' skipped over the batch cap');
        status.textContent = parts.join(', ');
        if(summary.updated) setTimeout(() => location.reload(), 1200);
      }});
      document.getElementById('cropToggle').addEventListener('click', () => {{
        croppedOnly = !croppedOnly;
        document.getElementById('cropToggle').classList.toggle('on', croppedOnly);
        showTab(curTab);
      }});
      document.getElementById('upstreamToggle').addEventListener('click', () => {{
        noUpstreamOnly = !noUpstreamOnly;
        document.getElementById('upstreamToggle').classList.toggle('on', noUpstreamOnly);
        showTab(curTab);
      }});
      document.addEventListener('click', e => {{
        const b = e.target.closest('button');
        if (!b || b.disabled) return;
        const fn = b.closest('.card')?.dataset.fn;
        if (!fn) return;
        if (b.classList.contains('purge')) purge(fn);
        else if (b.classList.contains('edit')) edit(fn);
        else if (b.classList.contains('restore')) restore(fn);
        else if (b.classList.contains('g')) setGender(fn, b.dataset.g);
      }});
      const _tabs=new Set(Array.from(document.querySelectorAll('.tab')).map(b=>b.dataset.t));
      const _hash=decodeURIComponent(location.hash.replace(/^#/,''));
      restoreFilters();
      showTab(_tabs.has(_hash) ? _hash : {default_tab!r});
    </script></body></html>"""
    return HTMLResponse(body)


def _find_entry(filename: str) -> dict[str, Any] | None:
    return next((e for e in _list_people(people_cache_dir()) if e['filename'] == filename), None)


@router.get('/edit', response_class=HTMLResponse)
async def edit_page(request: Request, filename: str = '') -> HTMLResponse:
    entry = await run_in('store', _find_entry, filename) if filename else None
    if entry is None:
        return HTMLResponse('<p style="font-family:system-ui;color:#e2e8f0;background:#0f1117">No cached headshot with that filename.</p>', status_code=404)
    relpath = str(entry.get('relpath', filename))
    cached_src = f'/images/local/{quote(relpath, safe="/")}?v={int(entry.get("mtime", 0))}'
    origin = html.escape(str(entry.get('source', '')) or 'unrecorded')
    subtitle = f'{html.escape(str(entry["role"]))} · <code>{html.escape(relpath)}</code> · from {origin}'
    body = (
        _EDIT_TEMPLATE.replace('__ACTOR_NAME__', html.escape(str(entry['name'])))
        .replace('__SUBTITLE__', subtitle)
        .replace('__CACHED_SRC__', html.escape(cached_src, quote=True))
        .replace('__TOKEN__', _json_attr(request.query_params.get('token', '')))
        .replace('__FILENAME__', _json_attr(filename))
        .replace('__ENTRY__', _json_attr(entry))
        .replace('__SOURCES__', _json_attr([source.name for source in FETCHABLE_SOURCES]))
        .replace('__CROP_AVAILABLE__', 'true' if face_crop.available() else 'false')
    )
    return HTMLResponse(body)


@router.post('/lookup')
async def lookup(request: Request) -> JSONResponse:
    data = await read_json_body(request)
    filename = str(data.get('filename', ''))
    wanted = str(data.get('source', ''))
    entry = await run_in('store', _find_entry, filename) if filename else None
    if entry is None:
        return JSONResponse({'ok': False, 'error': 'unknown filename'}, status_code=404)
    source = next((s for s in FETCHABLE_SOURCES if s.name == wanted), None)
    if source is None:
        return JSONResponse({'ok': False, 'error': 'unknown source'}, status_code=400)
    role: Any = entry['role']
    try:
        hit = await source.find(str(entry['name']), PersonLookupContext(type=role))
    except Exception as err:  # noqa: BLE001 - a failing source is a miss, not a 500
        logger.warn('people-cache', f'{source.name} lookup failed for {entry["name"]}: {err!r}')
        return JSONResponse({'ok': False, 'error': f'{source.name} lookup failed'}, status_code=502)
    if hit is None or not hit.url:
        return JSONResponse({'ok': False, 'error': f'{source.name} has no image for "{entry["name"]}"'}, status_code=404)
    logger.info('people-cache', f'{source.name} offered an image for {entry["name"]}')
    return JSONResponse({'ok': True, 'url': hit.url, 'gender': hit.gender or '', 'source': source.name})


@router.post('/bulk-fetch')
async def bulk_fetch(request: Request) -> Response:
    data = await read_json_body(request)
    wanted = str(data.get('source', ''))
    raw = data.get('filenames')
    filenames = [str(f) for f in raw if isinstance(f, str)] if isinstance(raw, list) else []
    source = next((s for s in FETCHABLE_SOURCES if s.name == wanted), None)
    if source is None:
        return JSONResponse({'ok': False, 'error': 'unknown source'}, status_code=400)
    if not filenames:
        return JSONResponse({'ok': False, 'error': 'no people selected'}, status_code=400)

    truncated = max(0, len(filenames) - _BULK_MAX)
    known = {e['filename']: e for e in await run_in('store', _list_people, people_cache_dir())}
    stream = _bulk_stream(source, filenames[:_BULK_MAX], known, truncated)
    return StreamingResponse(stream, media_type='application/x-ndjson')


async def _fetch_into_cache(source: PersonSource, filename: str, entry: dict[str, Any] | None) -> tuple[str, str]:
    if entry is None:
        return 'failed', filename
    name = str(entry['name'])
    role: Any = entry['role']
    try:
        hit = await source.find(name, PersonLookupContext(type=role))
    except Exception as err:  # noqa: BLE001 - one person failing must not abort the batch
        logger.warn('people-cache', f'{source.name} threw for {name}: {err!r}')
        return 'failed', name
    if hit is None or not hit.url:
        return 'missed', name
    cached = await cache_photo(hit.url, name, role, _gender_of(str(entry['gender'])), replace=True, crop=bool(entry['cropped']), source=source.name)
    if cached is None:
        return 'failed', name
    await run_in('store', scene_store.flag_people_changed, name)
    return 'updated', name


async def _bulk_stream(source: PersonSource, filenames: list[str], known: dict[str, dict[str, Any]], truncated: int) -> AsyncIterator[str]:
    total = len(filenames)
    sem = asyncio.Semaphore(_BULK_CONCURRENCY)
    tally = {'updated': 0, 'missed': 0, 'failed': 0}
    queue: asyncio.Queue[tuple[str, str] | None] = asyncio.Queue()

    async def _one(filename: str) -> None:
        async with sem:
            outcome, name = await _fetch_into_cache(source, filename, known.get(filename))
        tally[outcome] += 1
        await queue.put((outcome, name))

    async def _run() -> None:
        try:
            await asyncio.gather(*(_one(f) for f in filenames))
        finally:
            await queue.put(None)

    runner = asyncio.create_task(_run())
    yield json.dumps({'source': source.name, 'total': total}) + '\n'
    done = 0
    try:
        while (item := await queue.get()) is not None:
            done += 1
            yield json.dumps({'done': done, 'total': total, 'outcome': item[0], 'name': item[1]}) + '\n'
    finally:
        runner.cancel()
    logger.info('people-cache', f'bulk fetch from {source.name}: {tally["updated"]} updated, {tally["missed"]} not found, {tally["failed"]} failed')
    yield json.dumps({'ok': True, 'source': source.name, **tally, 'truncated': truncated}) + '\n'


@router.post('/save')
async def save(request: Request) -> JSONResponse:
    data = await read_json_body(request)
    filename = str(data.get('filename', ''))
    upstream = str(data.get('upstream_url', '')).strip()
    picked = str(data.get('source', ''))
    wants_crop = bool(data.get('cropped'))
    if not filename:
        return JSONResponse({'ok': False, 'error': 'missing filename'}, status_code=400)
    entry = await run_in('store', _find_entry, filename)
    if entry is None:
        return JSONResponse({'ok': False, 'error': 'unknown filename'}, status_code=404)
    if not upstream:
        return JSONResponse({'ok': False, 'error': 'an upstream URL is required to re-cache the image'}, status_code=400)
    if upstream == entry['upstream_url'] and wants_crop == entry['cropped']:
        return JSONResponse({'ok': True, 'changed': False})
    role: Any = entry['role']
    source = picked if any(s.name == picked for s in FETCHABLE_SOURCES) else ''
    cached = await cache_photo(upstream, str(entry['name']), role, _gender_of(str(entry['gender'])), replace=True, crop=wants_crop, source=source)
    if cached is None:
        return JSONResponse({'ok': False, 'error': 'could not download or store that image'}, status_code=400)
    flagged = await run_in('store', scene_store.flag_people_changed, str(entry['name']))
    logger.info('people-cache', f'edited {filename}: upstream={upstream} cropped={wants_crop}; {len(flagged)} scene(s) flagged to re-push')
    return JSONResponse({'ok': True, 'changed': True, 'scenes': len(flagged)})


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
    return JSONResponse({'ok': await run_in('fs', purge, filename)})


@router.post('/gender')
async def gender(request: Request) -> JSONResponse:
    data = await read_json_body(request)
    filename = str(data.get('filename', ''))
    new_gender = str(data.get('gender', ''))
    if not filename:
        return JSONResponse({'ok': False, 'error': 'missing filename'}, status_code=400)
    if new_gender not in ('', 'male', 'female', 'trans'):
        return JSONResponse({'ok': False, 'error': 'invalid gender'}, status_code=400)
    new_filename = await run_in('fs', set_gender, filename, new_gender)
    return JSONResponse({'ok': new_filename is not None, 'filename': new_filename})
