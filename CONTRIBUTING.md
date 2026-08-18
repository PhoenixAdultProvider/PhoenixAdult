# Contributing

## Commit message format

Commits should follow the [Conventional Commits](https://www.conventionalcommits.org/) spec.
This keeps the history readable and lets the version in `phoenixadult/__init__.py` be bumped
in a predictable way (feat → minor, fix → patch, `!`/`BREAKING CHANGE` → major).
The convention isn't enforced by a git hook — please follow it by hand.

### Shape

```
<type>(<scope>)?: <short description>

[optional body]

[optional footer(s)]
```

### Types we use

| Type        | Meaning                                                    | Triggers release? |
| ----------- | ---------------------------------------------------------- | ----------------- |
| `feat`      | A new feature or capability                                | **minor** bump    |
| `fix`       | A bug fix                                                  | **patch** bump    |
| `perf`      | A performance improvement                                  | **patch** bump    |
| `refactor`  | Code change that neither fixes a bug nor adds a feature    | patch bump        |
| `docs`      | Documentation only                                         | no release        |
| `build`     | Build system or dependency changes (`pyproject.toml` deps) | no release        |
| `ci`        | CI configuration changes (workflows, hooks)                | no release        |
| `test`      | Adding or correcting tests                                 | no release        |
| `style`     | Formatting, whitespace, no semantic change                 | no release        |
| `chore`     | Maintenance work that doesn't fit elsewhere                | no release        |

### Breaking changes

Add an exclamation mark after the type, or include a `BREAKING CHANGE:`
footer:

```
feat!: drop Python 3.11 support

BREAKING CHANGE: minimum Python version is now 3.12.
```

Either form triggers a **major** version bump.

### Examples

```
feat(networks): port the Wankz network as a dedicated client
fix(czechav): strip "Czech Casting NNNN:" prefix from titles
docs(readme): document the dev UI fixture builder
refactor(registry): split JSON selectors from network definitions
build(deps): bump httpx2 to 2.4.0
test(health): add Cherry Pimps fixture with score=82
```

### Scope (optional but encouraged)

The scope is usually the area touched — `scraper`, `registry`,
`dev-ui`, the site name (`cherrypimps`, `czechav`), or `deps` for
dependency bumps.

## Linting, formatting & types

This repo uses [ruff](https://docs.astral.sh/ruff/) for both linting and
formatting (it also keeps imports sorted), [mypy](https://mypy-lang.org/) for
static type-checking, and [pytest](https://docs.pytest.org/) for tests. Run the
full gate before every commit:

| Command                  | What it does                                        |
| ------------------------ | --------------------------------------------------- |
| `ruff format`            | Format the code, auto-fixing layout                 |
| `ruff format --check`    | Check formatting only (no writes) — what CI runs    |
| `ruff check`             | Lint only (no writes)                               |
| `ruff check --fix`       | Lint and auto-fix what's safe                       |
| `mypy app`               | Static type-check the `app/` package                |
| `pytest`                 | Run the test suite                                  |

Tests mirror the source tree under `tests/` — one test module per source module
(e.g. `tests/utils/test_processors.py`). New scrapers should land with a
fixture-driven test; see [docs/scraper-test-plan.md](./docs/scraper-test-plan.md).

## Versioning

The project version is written in exactly one place, `__version__` in
`phoenixadult/__init__.py`. Everything else derives from it: `pyproject.toml`
declares `dynamic = ["version"]` and reads that attribute, and the version Plex is
told (`PROVIDER_DEFINITIONS[0].version`) comes from `provider_version()`, which
spells the PEP 440 form out for display — `1.0.0a412` becomes `1.0.0-alpha.412`.
`tests/test_version.py` fails if any of those are re-hardcoded, because the Plex
version silently drifted 29 releases behind the package once already.

Note this means `grep '^version' pyproject.toml` no longer returns anything — read
`phoenixadult/__init__.py` instead, or `python -c "import phoenixadult; print(phoenixadult.__version__)"`.

There is no automated release tooling yet — bump the version by hand when cutting a
release, choosing the bump (major/minor/patch) from the Conventional Commit types
since the last one.
