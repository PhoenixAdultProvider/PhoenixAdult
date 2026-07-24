# Developer UI

The provider ships with an interactive debug UI at `/dev`. It's the fastest way to
point at a network, type in a Plex-style filename, and watch the search-and-scrape
pipeline run end-to-end — every parsed token, every upstream HTTP request, every
XPath selector hit. It's also where you build fixture entries for
`tests/health/fixtures.json`.

The `/dev` surface is **admin-guarded and non-production**: it's mounted only
outside production and its pipeline endpoints (`POST /dev/test`, `POST /dev/metadata`)
require the admin token, the same guard as `/config` (see `phoenixadult/utils/auth/env_auth.py`).
In a real deployment the route disappears.

## Getting Started

Start the dev server with auto-reload. The `/dev` UI is only mounted outside
production, and production is now the default — so set `NODE_ENV=development`:

```bash
NODE_ENV=development python -m phoenixadult.main   # auto-reloads outside production; PORT defaults to 3000
```

Open `http://localhost:3000/dev` in a browser. The page is a single scrollable
column with five functional areas, top to bottom:

1. **Filename input** — what you'd type into a Plex library
2. **Search pipeline** — step-by-step trace of how the filename was parsed and what was searched
3. **Results grid** — clickable cards for each search hit
4. **Metadata panel** — the full scrape of the result you clicked, plus a fixture builder
5. **Registered sites table** — every site the provider knows about, grouped by network

You don't need to fill the whole page — work top-down. Type a filename, press
Enter, click a result card, build a fixture if it scraped clean.

## The Filename Input

Type any filename the way Plex would hand it to the matching service. Extension is
optional. The buttons under the input drop in example formats so you can see the
supported shapes:

- **dash + date** — `Site Name - 2024-03-15 - Scene Title`
- **dot style** — `sitename.24.03.15.scene.title`
- **no date** — `Site Name - Scene Title`
- **id + name** — `sitename - 12345 - Scene Title`

The site token comes first in every form. After parsing, the UI shows what the
filename parser (`phoenixadult/utils/processors/filename_parser.py`) pulled out (site, date,
content) so you can confirm it understood you. If the parse fails or the site token
doesn't resolve to a registered site, the pipeline stops there and shows the
failure in red.

## The Search Pipeline Panel

Each search runs as a series of collapsible step cards with an OK/FAIL badge:

1. **Parse filename** — site token, date, content extracted
2. **Site lookup** — resolved `SiteInfo` from the registry, including aliases
3. **Provider lookup** — the umbrella `ProviderInfo` the site belongs to
4. **Search query** — the actual URL/query built for the upstream
5. **Search results** — the scraped result list with scores

The first three are fast (no I/O). Steps four and five trigger HTTP requests and
carry a "Raw upstream responses" sub-section with the actual responses (the
per-request `capture` buffer). OK steps default to expanded; FAIL steps collapse so
the error is the first thing you see.

## The Results Grid

Successful searches render as cards: thumbnail (or placeholder), scraped title, and
the assigned score. Click a card to fetch full metadata; the selected card's border
turns purple. Scores follow the project convention:

- **100** — Scene-ID direct hit
- **80** — exact title or date match (highest fuzzy score)
- **< 80** — fuzzy; Levenshtein distance subtracted from 80
- **Negative** — title completely different from the query

When a score lands in the 70s, eyeball the scraped title against the filename
before trusting it. Below ~60, treat the match as speculative.

## The Metadata Panel

Clicking a result fetches detail and renders poster + scraped fields: title,
studio, tagline, release date, summary, genres, actor list (with gender chips when
known), directors, producers, collections, and image counts. A horizontal image
strip shows every poster/art URL — click any to open the full image in a new tab
(confirms the URL resolves and the right photo is pulled). The detail-fetch
pipeline renders below with the same collapsible steps and inline captures.

## Captures: the Killer Feature

Both pipelines push their raw HTTP responses into a capture buffer the UI exposes
inline. Every fetch shows a method+URL label (clickable), a JSON/HTML content-type
badge, the response size, and **Copy URL** / **Copy Body** buttons. Click the
header to toggle the body (JSON pretty-printed, HTML as-is; scrollable, height
capped).

This is the panel to live in when a scraper misbehaves: if search returned zero
results but the upstream returned 200, expand the capture body and look at the HTML
— your XPath probably doesn't match what's on the page. Copy the URL, open it,
view-source, confirm the structure.

## Building a Fixture

Once a result scrapes cleanly, the metadata panel's "Fixture" block emits a JSON
object pre-shaped for `tests/health/fixtures.json`:

```json
{
  "site": "Trick Your GF",
  "filename": "trickyourgf - 2023-08-12 - Sample Title",
  "expect": {
    "title": "Sample Title",
    "studio": "Dirty Flix",
    "tagline": "Trick Your GF",
    "scenedate": "2023-08-12",
    "summary": "...",
    "actors": [{ "name": "Actor One", "gender": "female" }],
    "directors": [],
    "producers": [],
    "collections": ["Trick Your GF"],
    "genres": ["Girlfriend", "Revenge"],
    "minImages": 2,
    "score": 80
  }
}
```

**Copy** flattens each array to one line for easy tweaking; **Copy one-liner**
minifies. Paste it into `tests/health/fixtures.json` and `python -m
scripts.site_health` will regression-check that site against this filename. The
`score` defaults to whatever the selected result got, so a future change that drops
match quality below that threshold fails the check. Trim `summary` to a sentence
(it's a substring match) and drop any genre the upstream re-orders.

## The Registered Sites Table

A sortable table of every registered site. Click column headers to sort; umbrella
networks are grouped with a "N sites" badge you can expand. Useful for finding an
exact alias, confirming a newly registered site loaded, or checking which scraper
type a site uses.

## Tips

- **Enter to search** — same as clicking Search.
- **Click step headers** to toggle bodies (all expanded except failed ones).
- **Clipboard copies** work on `localhost` over HTTP (falls back to
  `document.execCommand('copy')` when `navigator.clipboard` is unavailable).

## What it Doesn't Do

Intentionally minimal: it doesn't persist results across reloads, edit the
registry/selectors live (those are file edits + restart), replay a previous search,
or run against production data. It's a fast scratchpad, not a state-keeping tool.
