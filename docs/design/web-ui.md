---
sidebar_label: Web UI
description: The admin pages' shell, navigation, theme kit, shared components and localization.
---

# Web UI

## Page Shell

Every admin page extends one shell, `phoenixadult/routes/html/base.html`: the doctype, head, favicon and title skeleton, plus `title`/`head`/`page`/`chrome`/`content`/`scripts` blocks. Each page keeps only its own `<style>`, markup and script. Shared front-end helpers (`esc`/`qs`/`hdrs` and the SFW-toggle mechanics) live in `common.html`.

Navigation between routes is a progressive enhancement, and both features are no-ops on browsers that lack them:

- **View Transitions.** `theme.html` opts into cross-document transitions (`@view-transition { navigation: auto }`, disabled under `prefers-reduced-motion`), and the fixed nav stays put via `view-transition-name`.
- **Speculation Rules.** `nav.html` prerenders a nav destination on hover, so the click activates an already-rendered page.
- **In-place swaps.** `nav_swap.html` replaces only `<main>` and re-runs the new page's scripts in global scope. That is why page scripts declare `var`, never top-level `const`/`let`, and why chrome scripts that must keep running use `setTimeout` chains rather than `setInterval` (intervals from the previous page are cleared on every swap).

## Navigation

Every admin page shares one fixed top nav — Metadata, People, Logos, Queue, Searches (admins only), Dev, Config:

- It is rendered from `phoenixadult/routes/html/nav.html`, a Jinja2 partial each page pulls in with `{% include 'nav.html' %}`. The shared autoescaping environment and `render_page()` live in `phoenixadult/routes/__init__.py`.
- The `/metadata/edit` and `/people/edit` sub-pages highlight their parent.
- The Dev link appears only when `DEV_UI_ENABLE` is on.
- The signed-in username links to `/account` and sits beside a Log Out button. The session cookie carries auth across navigation, so no token is threaded through links.
- **Network banner.** Below the nav, a banner shows while the network is down. It is rendered from `network_down()` and then polled from `GET /api/network` (every 60s while hidden, 15s while shown), so it clears on its own. See [HTTP and Bypass](./http-bypass.md#network-down-fast-fail).

## Theme Kit

Every color on every page is a CSS custom property named for the **element it styles** (`--card-bg`, `--button-primary-bg`, `--female`, …):

- **Theme files.** Variables are defined in per-theme stylesheets under `phoenixadult/routes/html/themes/`: `midnight` and `forest` (dark), `sky` and `meadow` (light). They are served publicly at `/themes/<name>.css`, validated against `THEME_NAMES` (`phoenixadult/routes/__init__.py`).
- **Per-page overrides.** Each theme file lists the shared element variables by category, then one `[data-page="…"]` block per page, so one element on one page can be recolored without touching anything else. Each `<body>` carries its `data-page`.
- **Mode.** Pages follow the system light/dark mode by default. The sun/moon/Auto toggle in the nav overrides it (`localStorage` `pa-theme`).
- **Theme per mode.** The Config UI's **Theme** tab picks which theme each mode loads. The choice is **stored on the signed-in user's account** (`users.theme_dark`/`theme_light`, saved via `POST /config/api/theme`, injected as `window.paUserTheme` at render), so one user's choice never touches another's. `localStorage` (`pa-theme-dark`/`pa-theme-light`) is the instant-apply and signed-out fallback.
- **Preview.** The Theme tab renders a per-page element preview of the selected light and dark themes side by side.
- **Loader.** `theme.html` is only the boot loader that swaps the `<link>`.

Two tests hold the kit together (`tests/routes/test_nav.py`): templates never use raw hex colors, and every referenced variable must exist in every theme.

## Shared Tokens and Components

Color is per theme; everything else is shared. `base.html` declares the non-color tokens once:

- two font roles (`--font-ui`, `--font-mono`);
- a seven-step type scale (`--text-2xs` … `--text-2xl`);
- spacing (`--space-1` … `--space-6`), radii and one elevation shadow;
- the `box-sizing` reset, the `body` font and background, the shared `h1`/`.sub`, and the `:focus-visible` ring.

It also owns every UI component: `pa-btn`, `pa-input`, `pa-card`, `pa-badge`, `pa-chip`, `pa-label`/`pa-fieldset`/`pa-hint`/`pa-status`/`pa-empty`, the `pa-reveal` password toggle (CSS and click handler), `pa-meter`, `pa-progress-*` and `pa-spinner`.

Rules:

- **Pages never restyle a component.** They add layout under their own class names and set only their own `padding`. `tests/routes/test_readonly_uis.py` fails any template that redeclares a component, and the theme-variable test skips tokens declared in `base.html`.
- **Fonts.** The two typefaces are vendored as OFL latin subsets under `phoenixadult/routes/html/fonts/` and served at `/fonts/<name>.woff2`, allowlisted against `FONT_NAMES` like themes. `@font-face` lives in `theme.html` so the standalone `login`/`setup`/`account` templates get them too. `package-data` must keep shipping `**/*.woff2`, or the port serves a missing font.
- **Mono is semantic.** It marks identifiers (hashes, `cur_id`s, keys, paths), never decoration.

## Phones and Desktops

Every page is built for both:

- a real `<head>` with `width=device-width`;
- inputs at 16px (smaller makes iOS zoom on focus);
- one 720px breakpoint that lifts buttons and inputs to a 44px tap target, so both render the same components and differ only in layout;
- a `@media (max-width: 720px)` block that collapses each wide table into stacked label/value rows via `data-label`.

`tests/routes/test_mobile_layout.py` enforces this.

## Logos UI

`/logos` browses the clearLogo cache, and `/logos/add` fills the gaps. It lists every sub-site of a studio that still lacks a logo, one row apiece, each taking a pasted URL or a dropped file.

- **Logo URL template.** Networks that serve logos from a predictable path are handled in bulk by one address carrying placeholders: `{domain}`, the `{subsiteclean}` / `{subsite-name}` / `{subsite_name}` / `{subsite}` name forms, their `{studio…}` equivalents, and `{ext}` to try `.svg`/`.png`/`.webp`/`.jpg` in turn. It is expanded server-side by `phoenixadult/utils/images/logo_template.py`, so the slug rules stay in Python.
- **Try All Subsites** expands the template into every row and fetches them in one pass, deliberately skipping the whole-studio row. An unknown placeholder is refused by name rather than producing a page of broken URLs.
- **Remembered templates.** A template that fetched something is remembered per studio and offered back the next time that studio is picked.
- **Fetching.** Fetches reuse the ordinary image chain (referers, then the impersonate bypass). Hosts that are loopback, link-local or a private IP literal are rejected, so a template cannot become a LAN sweep.
- **Processing.** Every logo is trimmed of dead space, and SVGs are rasterized on the way in.

## Localization

Every string the web pages show lives in **one file, `phoenixadult/i18n/en.po`**, under a stable key and grouped by page with `# ── Section ──` comments. Code never holds display text, only keys. Scraped data (site, scene and performer names) is not translated.

| Where the text is used | How it references a key |
|---|---|
| Jinja template markup | `{{ _('people.title') }}`; values as `{{ _('dev.n_sites', count=n) }}` with `%(count)s` in the text |
| Page JavaScript | `var T = {{ strings('people', 'common') \| tojson }};` once per page, then `T.title`; values with `tr(T.progress, { done, total })` and `{done}` in the text |
| Python (routes, services, validation) | `gettext('plex.no_connection') % {...}`; a key stored for later lookup is marked `N_('nav.metadata')` |
| Config UI settings | derived as `settings.<KEY>.label` / `.description` (`EnvVarSpec.text_keys()`) |

Rules:

- Keys are `section.name` in lowercase.
- `strings()` exposes only single-level keys of the named sections.
- A literal `%` is written `%%`.
- `UI_LANGUAGE` picks the catalog (`<code>.po` beside `en.po`). Missing keys fall back to English, then to the key itself.

Tooling:

- `python -m scripts.i18n check` reports keys used in code but missing from `en.po`, unused entries, bad `T.` references, bare `%`, and placeholder mismatches in other languages. `init <code>` starts a new language file and `update` re-syncs existing ones.
- `tests/framework/test_strings_file.py` runs the checker.
- `tests/routes/test_untranslated_text.py` renders every page with a placeholder catalog and fails on any visible English left in the markup.
