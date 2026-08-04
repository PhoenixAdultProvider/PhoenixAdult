from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

_ROOT = Path(__file__).resolve().parent.parent
_ICON = {'ok': '✅', 'nok': '❌', 'skip': '—'}
_FIELD_ORDER: list[tuple[str, str]] = [
    ('score', 'Score'),
    ('title', 'Title'),
    ('studio', 'Studio'),
    ('summary', 'Summary'),
    ('tagline', 'Tagline'),
    ('scenedate', 'Date'),
    ('actors', 'Actors'),
    ('directors', 'Directors'),
    ('producers', 'Producers'),
    ('collections', 'Collections'),
    ('genres', 'Genres'),
    ('images', 'Images'),
]
_SKIP = {'status': 'skip', 'expected': '', 'got': ''}


# ── Comparison Helpers (pure) ──────────────────────────────────────────────────


def _lc(s: str | None) -> str:
    return (s or '').lower()


def _eq(a: str | None, b: str | None) -> bool:
    return _lc(a).strip() == _lc(b).strip()


def _blank_fields() -> dict[str, dict[str, str]]:
    return {k: dict(_SKIP) for k, _ in _FIELD_ORDER}


def _check_scalar(exp: str | None, got: str | None, mode: str) -> dict[str, str]:
    if exp is None:
        return dict(_SKIP)
    ok = _eq(exp, got) if mode == 'exact' else _lc(exp) in _lc(got)
    return {'status': 'ok' if ok else 'nok', 'expected': exp, 'got': got or ''}


def _check_list(exp: list[str] | None, got: list[str], label_ok: str) -> dict[str, str]:
    if not exp:
        return dict(_SKIP)
    have = {_lc(g) for g in got}
    missing = [e for e in exp if _lc(e) not in have]
    ok = not missing
    return {
        'status': 'ok' if ok else 'nok',
        'expected': ', '.join(exp),
        'got': label_ok if ok else f'{", ".join(got) or "(none)"} — missing: {", ".join(missing)}',
    }


def _check_actors(exp: list[dict[str, Any]] | None, roles: list[Any]) -> dict[str, str]:
    if not exp:
        return dict(_SKIP)
    have_by_name = {_lc(r.tag): r for r in roles}
    missing: list[str] = []
    gender_mismatch: list[str] = []
    for want in exp:
        found = have_by_name.get(_lc(want['name']))
        if not found:
            missing.append(want['name'])
            continue
        g = want.get('gender')
        if g and g != 'none' and _lc(found.gender) != _lc(g):
            gender_mismatch.append(f'{want["name"]}: expected {g}, got {_lc(found.gender) or "(none)"}')
    ok = not missing and not gender_mismatch
    expected_str = ', '.join(f'{a["name"]} ({a["gender"]})' if a.get('gender') else a['name'] for a in exp)
    got_str = ', '.join(f'{r.tag} ({r.gender})' if r.gender else r.tag for r in roles)
    problems = []
    if missing:
        problems.append(f'missing: {", ".join(missing)}')
    if gender_mismatch:
        problems.append(f'gender: {"; ".join(gender_mismatch)}')
    return {'status': 'ok' if ok else 'nok', 'expected': expected_str, 'got': f'{got_str or "(none)"} — {" / ".join(problems)}' if problems else got_str}


def _check_threshold(min_val: int | None, got: float) -> dict[str, str]:
    if min_val is None:
        return dict(_SKIP)
    return {'status': 'ok' if got >= min_val else 'nok', 'expected': f'>= {min_val}', 'got': str(got)}


# ── Runner ─────────────────────────────────────────────────────────────────────


async def _run_one(fx: dict[str, Any]) -> dict[str, Any]:
    from phoenixadult.clients.base import SceneContext, SearchContext
    from phoenixadult.mappers.metadata_mapper import MetadataMapper
    from phoenixadult.registry import find_site, get_all_providers
    from phoenixadult.services.scraper_router import ScraperRouter
    from phoenixadult.utils.processors.filename_parser import get_site_name_from_registry
    from phoenixadult.utils.processors.search_query import build_search_pieces

    r: dict[str, Any] = {'site': fx['site'], 'filename': fx['filename'], 'ok': False, 'reason': '', 'fields': _blank_fields()}
    try:
        parsed = get_site_name_from_registry(fx['filename'], lambda token: find_site(token) is not None)
        if not parsed:
            r['reason'] = 'filename did not parse'
            return r
        site = find_site(parsed.site_token)
        if not site:
            r['reason'] = f'no site for token "{parsed.site_token}"'
            return r
        provider = next((p for p in get_all_providers() if p.id == site.provider_id), None)
        if not provider:
            r['reason'] = f'no provider for "{site.provider_id}"'
            return r

        router = ScraperRouter()
        # Mirror the real provider flow (match_service): pass scene_id + full_title,
        # not just the query — sceneId/sceneIdName scrapers do a direct ID lookup.
        pieces = build_search_pieces(site.content_type, parsed)
        query = pieces.query or ''
        captures: list[Any] = []
        results = await router.search(
            SearchContext(
                title=query,
                encoded=quote(query),
                search_site=parsed.site_token,
                site_info=site,
                search_date=parsed.date,
                scene_id=pieces.scene_id,
                full_title=pieces.full_title,
                capture=captures,
            )
        )
        if not results:
            r['reason'] = 'search returned 0 results'
            return r

        best = sorted(results, key=lambda x: x.score or 0, reverse=True)[0]
        best_score = best.score or 0
        detail = await router.fetch_scene_detail(router.decode(best.cur_id), site, SceneContext(capture=captures))
        if not detail:
            r['reason'] = 'fetch_scene_detail returned None'
            return r

        mapper = MetadataMapper()
        rating_key = mapper.to_rating_key(best.cur_id, site.name, parsed.date)
        meta = await mapper.to_metadata(detail, rating_key, provider.plex_identifier, parsed.date, site)

        e = fx.get('expect') or {}
        f = r['fields']
        f['score'] = _check_threshold(e.get('score'), best_score)
        f['title'] = _check_scalar(e.get('title'), meta.title, 'exact')
        f['studio'] = _check_scalar(e.get('studio'), meta.studio, 'exact')
        f['summary'] = _check_scalar(e.get('summary'), meta.summary, 'contains')
        f['tagline'] = _check_scalar(e.get('tagline'), meta.tagline, 'exact')
        f['scenedate'] = _check_scalar(e.get('scenedate'), meta.originallyAvailableAt, 'exact')
        f['actors'] = _check_actors(e.get('actors'), meta.Role or [])
        f['directors'] = _check_list(e.get('directors'), [d.tag for d in (meta.Director or [])], 'all present')
        f['producers'] = _check_list(e.get('producers'), [p.tag for p in (meta.Producer or [])], 'all present')
        f['collections'] = _check_list(e.get('collections'), [c.tag for c in (meta.Collection or [])], 'all present')
        f['genres'] = _check_list(e.get('genres'), [g.tag for g in (meta.Genre or [])], 'all present')
        f['images'] = _check_threshold(e.get('minImages'), len(meta.Image or []))

        checked = [v for v in f.values() if v['status'] != 'skip']
        r['ok'] = bool(checked) and all(v['status'] == 'ok' for v in checked)
        if not r['ok'] and not r['reason']:
            failing = [k for k, v in f.items() if v['status'] == 'nok']
            r['reason'] = f'field mismatch: {", ".join(failing)}'
        return r
    except Exception as err:  # noqa: BLE001 - health runner records any failure as a row
        r['reason'] = str(err)
        return r


# ── Markdown Report (pure, rendered from result dicts) ─────────────────────────


def _esc(s: str) -> str:
    return s.replace('|', '\\|').replace('\n', ' ')


def _summary_row_line(r: dict[str, Any]) -> str:
    any_ok = any(v['status'] == 'ok' for v in r['fields'].values())
    overall = f'❌ {_esc(r["reason"])}' if r['reason'] and not any_ok else ('✅' if r['ok'] else '❌')
    icons = ' | '.join(_ICON[r['fields'][k]['status']] for k, _ in _FIELD_ORDER)
    return f'| {_esc(r["site"])} | {overall} | {icons} |'


def _stamp() -> str:
    return datetime.now(UTC).strftime('%Y-%m-%d %H:%M') + ' UTC'


def _render_site_health(results: list[dict[str, Any]], passed: int, total: int) -> str:
    lines = ['# Scraper Health', '', f'_Last updated: **{_stamp()}** &middot; **{passed}/{total}** sites passing all checks_', '', '## Summary', '']
    header = ['Site', 'Overall', *[label for _, label in _FIELD_ORDER]]
    lines.append('| ' + ' | '.join(header) + ' |')
    lines.append('| ' + ' | '.join('---' if i == 0 else ':-:' for i in range(len(header))) + ' |')
    lines.extend(_summary_row_line(r) for r in results)
    lines.append('')
    lines.append('<sub>Auto-generated by `scripts/site_health.py` &mdash; edit `tests/health/fixtures.json` to change checks.</sub>')
    lines.append('')
    return '\n'.join(lines)


def _detail_block(r: dict[str, Any]) -> str:
    lines = [f'### {_esc(r["site"])} &mdash; {"✅ OK" if r["ok"] else "❌ NOK"}', '', f'- Filename: `{_esc(r["filename"])}`']
    if r['reason']:
        lines.append(f'- Reason: {_esc(r["reason"])}')
    lines.extend(['', '| Field | Status | Expected | Got |', '| --- | :-: | --- | --- |'])
    for key, label in _FIELD_ORDER:
        fr = r['fields'][key]
        if fr['status'] == 'skip':
            lines.append(f'| {label} | {_ICON["skip"]} | _(not checked)_ |  |')
        else:
            lines.append(f'| {label} | {_ICON[fr["status"]]} | {_esc(fr["expected"])} | {_esc(fr["got"])} |')
    return '\n'.join(lines)


def _render_details(results: list[dict[str, Any]], passed: int, total: int) -> str:
    lines = ['# Scraper Health', '', f'_Last updated: **{_stamp()}** &middot; **{passed}/{total}** sites passing all checks_', '', '## Details', '']
    for r in results:
        lines.append(_detail_block(r))
        lines.append('')
    lines.append('<sub>Auto-generated by `scripts/site_health.py` &mdash; edit `tests/health/fixtures.json` to change checks.</sub>')
    lines.append('')
    return '\n'.join(lines)


def _load_prior(sidecar: Path) -> list[dict[str, Any]]:
    if not sidecar.exists():
        return []
    try:
        data = json.loads(sidecar.read_text(encoding='utf-8'))
    except (ValueError, OSError):
        return []
    return data if isinstance(data, list) else []


# ── Entry Point ─────────────────────────────────────────────────────────────────


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run scraper health fixtures and write the markdown report.')
    parser.add_argument(
        'mode', nargs='?', default='full', choices=('full', 'new', 'retry'), help='full = every fixture, new = uncovered only, retry = failing only'
    )
    parser.add_argument('--output', help='write both reports to this path instead of docs/')
    parser.add_argument('--no-details', action='store_true', help='skip the details report')
    parser.add_argument('--keep-gender-skip', action='store_true', help='leave GENDER_SKIP_MALE_ENABLE untouched')
    parser.add_argument('--keep-flaresolverr', action='store_true', help='leave FLARESOLVERR_URL untouched')
    return parser.parse_args(argv)


async def _main(opts: argparse.Namespace) -> int:
    docs_dir = _ROOT / 'docs'
    out_health = Path(opts.output) if opts.output else docs_dir / 'site-health.md'
    out_details = Path(opts.output) if opts.output else docs_dir / 'site-health-details.md'
    sidecar = out_health.with_suffix('.json')
    fixtures_path = _ROOT / 'tests' / 'health' / 'fixtures.json'

    all_fixtures: list[dict[str, Any]] = json.loads(fixtures_path.read_text(encoding='utf-8'))
    if any(fx['site'] == 'Manual NFO' for fx in all_fixtures):
        os.environ['MANUAL_NFO_PATH'] = str(_ROOT / 'tests' / 'health' / 'manual-nfo-fixtures')

    prior = _load_prior(sidecar)
    fixtures = all_fixtures
    if opts.mode == 'new':
        covered = {r['site'] for r in prior}
        fixtures = [fx for fx in all_fixtures if fx['site'] not in covered]
        if not fixtures:
            print('[health] nothing to do — every fixture is already in the report.')
            return 0
    elif opts.mode == 'retry':
        failed = {r['site'] for r in prior if not r.get('ok')}
        fixtures = [fx for fx in all_fixtures if fx['site'] in failed]
        if not fixtures:
            print('[health] nothing to do — no failing sites in the report.')
            return 0

    concurrency = 3
    print(f'[health] running {len(fixtures)} fixture(s), {concurrency} at a time')
    gate = asyncio.Semaphore(concurrency)

    async def run(fx: dict[str, Any]) -> dict[str, Any]:
        async with gate:
            res = await _run_one(fx)
        if res['ok']:
            print(f'[health] {res["site"]} ... OK')
        else:
            failing = [k for k, v in res['fields'].items() if v['status'] == 'nok']
            print(f'[health] {res["site"]} ... NOK ({res["reason"]}{"; failing: " + ",".join(failing) if failing else ""})')
        return res

    results = list(await asyncio.gather(*(run(fx) for fx in fixtures)))

    fresh = {r['site'] for r in results}
    merged = [r for r in prior if r['site'] not in fresh] if opts.mode in ('new', 'retry') else []
    merged = sorted([*merged, *results], key=lambda r: str(r['site']).lower())
    passed = sum(1 for r in merged if r.get('ok'))
    total = len(merged)

    out_health.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(json.dumps(merged, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    out_health.write_text(_render_site_health(merged, passed, total), encoding='utf-8')
    if not opts.no_details:
        out_details.write_text(_render_details(merged, passed, total), encoding='utf-8')
    print(f'[health] wrote {out_health}')
    print(f'[health] summary: {passed}/{total} sites passing')
    return 0


def main() -> None:
    opts = _parse_args(sys.argv[1:])
    if not opts.keep_gender_skip:
        os.environ['GENDER_SKIP_MALE_ENABLE'] = 'false'
    if not opts.keep_flaresolverr:
        os.environ.pop('FLARESOLVERR_URL', None)
    sys.exit(asyncio.run(_main(opts)))


if __name__ == '__main__':
    main()
