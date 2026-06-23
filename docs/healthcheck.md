# Scraper Health Checks

Live-HTTP smoke tests for the registered scrapers. Run on demand from the repo root:

```bash
python -m scripts.site_health            # full sweep
python -m scripts.site_health new        # only fixtures not yet in the report
python -m scripts.site_health retry      # only sites whose last run failed
```

Output lands at [`docs/site-health.md`](./site-health.md) (summary grid) and
[`docs/site-health-details.md`](./site-health-details.md) (per-site expected-vs-actual
tables). Each site gets a row in the summary grid with one icon per field type.

`new` and `retry` merge their fresh rows back into the existing report in place,
preserving the other sites without re-running them. Useful flags: `--output <path>`,
`--no-details`, `--keep-gender-skip`, `--keep-flaresolverr`.

### Fixture schema (`tests/health/fixtures.json`)

Each fixture is `{ site, filename, expect }` where `expect` may set any subset of the supported assertions:

```json
{
  "site":     "MYLF",
  "filename": "Anal Mom - 2024-01-15 - Some Real Scene.mp4",
  "expect": {
    "title":       "Some Real Scene",
    "studio":      "MYLF",
    "tagline":     "Anal Mom",
    "scenedate":   "2024-01-15",
    "summary":     "a substring you know is in the description",
    "actors":      [
      { "name": "Jane Doe",   "gender": "female" },
      { "name": "John Smith", "gender": "male"   }
    ],
    "directors":   ["Director Name"],
    "producers":   ["Producer Name"],
    "collections": ["Anal Mom"],
    "genres":      ["Anal", "MILF"],
    "minImages":   3,
    "score":       80
  }
}
```

| Field | Comparison |
|---|---|
| `title` / `studio` / `tagline` | Exact match, case-insensitive |
| `summary` | Case-insensitive substring (summaries vary; substring keeps the check robust) |
| `scenedate` | Exact ISO `YYYY-MM-DD` |
| `actors` | Each expected actor must appear in `Role[]`. Gender is checked when provided (`female` / `male` / `trans` / `none`); omit `gender` to skip the gender check |
| `directors` / `producers` / `collections` / `genres` | Every expected string must appear in the corresponding tag array (case-insensitive). Extras in the actual output are OK |
| `minImages` | `Image[].length >= minImages` |
| `score` | The highest-scoring search result's score must be `>= score` (0-100) |

Any field you don't list is skipped (shown as `—` in the report). A site is "OK" only when every checked field is OK.

### Run-time env overrides

The runner forces a couple of env vars for the duration of the sweep so user
preferences don't mask real regressions:

- `GENDER_ENABLE` → `false` (so the male-actor skip doesn't drop cast members the
  fixtures expect). Pass `--keep-gender-skip` to honour your env value.
- `FLARESOLVERR_URL` → unset (so checks hit the primary upstream directly; a flaky
  bypass would otherwise paper over a broken scraper). Pass `--keep-flaresolverr`
  to leave it alone.
- `MANUAL_NFO_PATH` → pointed at `tests/health/manual-nfo-fixtures` when a
  Manual NFO fixture is present.
