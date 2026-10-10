from __future__ import annotations

from pathlib import Path

from phoenixadult.registry import ResolvedSiteInfo, get_all_providers, get_sites_for_provider

_METHOD_ICON = {'enhanced': '✅', 'limited': '✓', 'exact': '❌'}
_METHOD_RANK = {'enhanced': 3, 'limited': 2, 'exact': 1}

_LEGEND = '\n'.join(
    [
        '# Supported Sites',
        '#### Key: Supported Search Methods',
        '+ ✅ = **[Enhanced Search](./manualsearch.md#enhanced-search)**. This includes searching by title and/or actor(s), enhanced with date and/or SceneID matching.',  # noqa: E501
        '+ ✓ = **[Limited Search](./manualsearch.md#limited-search)**. Only title and/or actor can be used, unless otherwise noted.',
        '+ ❌ = **[Exact Match](./manualsearch.md#exact-match)** only. Either using a numerical Scene&nbsp;ID or a Direct&nbsp;URL.',
        '+ *Backend* Required = the site blocks plain requests, so every request goes through the named [bypass backend](./design/http-bypass.md#bypass-chain), tried in the order listed.',  # noqa: E501
        '',
        'If the site is not listed below &mdash; i.e. the site is not yet supported &mdash; use the instructions for [manual adding](./manualsearch.md#manual-nfo).',  # noqa: E501
        '',
        'To update the site list run `python -m scripts.generate_sitelist`',
        '## All Supported Networks and Sites',
        '',
    ]
)


class _Group:
    def __init__(self, title: str) -> None:
        self.title = title
        self.sites: list[ResolvedSiteInfo] = []


def _group_sites(sites: list[ResolvedSiteInfo]) -> list[_Group]:
    groups: dict[str, _Group] = {}
    ungrouped: list[_Group] = []
    for site in sites:
        key = (site.provider_name or '').strip()
        if key:
            g = groups.get(key)
            if not g:
                g = _Group(key)
                groups[key] = g
            g.sites.append(site)
        else:
            g = _Group(site.name)
            g.sites.append(site)
            ungrouped.append(g)
    return sorted([*groups.values(), *ungrouped], key=lambda g: g.title.lower())


def _group_icon(g: _Group) -> str:
    best_rank = 0
    best_method = 'limited'
    for s in g.sites:
        m = s.search_method
        if not m:
            continue
        rank = _METHOD_RANK[m]
        if rank > best_rank:
            best_rank = rank
            best_method = m
    return _METHOD_ICON[best_method]


def _group_notes(g: _Group) -> str:
    counts: dict[str, int] = {}
    for s in g.sites:
        n = (s.search_notes or '').strip()
        if n:
            counts[n] = counts.get(n, 0) + 1
    if len(g.sites) == 1:
        return next(iter(counts), '')
    if len(counts) != 1:
        return ''
    note, count = next(iter(counts.items()))
    return note if count >= 2 else ''


def bypass_label(backends: tuple[str, ...]) -> str:
    if not backends:
        return ''
    names = list(backends)
    joined = names[0] if len(names) == 1 else f'{", ".join(names[:-1])} and {names[-1]}'
    return f'{joined} Required'


def _group_bypass(g: _Group) -> tuple[str, ...]:
    found = {s.bypass for s in g.sites}
    return next(iter(found)) if len(found) == 1 else ()


def _emit_group(g: _Group) -> str:
    icon = _group_icon(g)
    heading_note = _group_notes(g)
    heading_bypass = _group_bypass(g)
    bypass_tail = f' | {bypass_label(heading_bypass)}' if heading_bypass else ''
    header_tail = f' | {icon}{bypass_tail}' + (f' - **{heading_note}**' if heading_note else '')
    lines: list[str] = [f'+ #### {g.title}{header_tail}']

    sorted_sites = sorted(g.sites, key=lambda s: s.name.lower())

    if len(sorted_sites) == 1 and not (sorted_sites[0].aliases) and sorted_sites[0].name.strip().lower() == g.title.strip().lower():
        return '\n'.join(lines)

    def emit_site(site: ResolvedSiteInfo) -> None:
        aliases = sorted(site.aliases or [], key=str.lower)
        note = (site.search_notes or '').strip()
        note_suffix = f' - **{note}**' if note and note != heading_note else ''
        if site.bypass and site.bypass != heading_bypass:
            note_suffix = f' | {bypass_label(site.bypass)}{note_suffix}'
        if site.name.strip().lower() == g.title.strip().lower():
            for alias in aliases:
                lines.append(f'  - {alias}')
        else:
            lines.append(f'  - {site.name}{note_suffix}')
            for alias in aliases:
                lines.append(f'    - {alias}')

    sub_grouped = [s for s in sorted_sites if (s.sub_group or '').strip()]
    if not sub_grouped:
        for site in sorted_sites:
            emit_site(site)
        return '\n'.join(lines)

    for site in (s for s in sorted_sites if not (s.sub_group or '').strip()):
        emit_site(site)

    buckets: dict[str, list[ResolvedSiteInfo]] = {}
    for site in sub_grouped:
        buckets.setdefault((site.sub_group or '').strip(), []).append(site)

    for key in sorted(buckets, key=str.lower):
        leaf_entries: list[tuple[str, str]] = []
        for m in buckets[key]:
            leaf_entries.append((m.name, (m.search_notes or '').strip()))
            for alias in m.aliases or []:
                leaf_entries.append((alias, ''))
        if len(leaf_entries) == 1 and leaf_entries[0][0] == key:
            note = leaf_entries[0][1]
            suffix = f' - **{note}**' if note and note != heading_note else ''
            lines.append(f'  - {key}{suffix}')
            continue
        lines.append(f'  - {key}')
        for label, note in sorted(leaf_entries, key=lambda e: e[0].lower()):
            if label == key:
                continue
            suffix = f' - **{note}**' if note and note != heading_note else ''
            lines.append(f'    - {label}{suffix}')
    return '\n'.join(lines)


def build() -> str:
    chunks: list[str] = [_LEGEND]
    for provider in get_all_providers():
        for g in _group_sites(get_sites_for_provider(provider.id)):
            chunks.append(_emit_group(g))
    return '\n'.join(chunks) + '\n'


def main() -> None:
    out = build()
    target = Path(__file__).resolve().parent.parent / 'docs' / 'sitelist.md'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(out, encoding='utf-8')
    group_count = len([ln for ln in out.splitlines() if ln.startswith('+ #### ')])
    bullet_count = len([ln for ln in out.splitlines() if ln.lstrip().startswith('- ')])
    print(f'Wrote {target}')
    print(f'  {group_count} group headings, {bullet_count} entries (sub-groups, sites, aliases)')


if __name__ == '__main__':
    main()
