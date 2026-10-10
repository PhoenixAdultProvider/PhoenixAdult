# Contributing

## Commit Message Format

Commits should follow the [Conventional Commits](https://www.conventionalcommits.org/) spec.
This keeps the history readable and lets the version in `phoenixadult/__init__.py` be bumped
in a predictable way. During the alpha every shipped change increments the alpha number (see
[Versioning](#versioning)); from 1.0 the types map to semantic versions (feat → minor,
fix → patch, `!`/`BREAKING CHANGE` → major).
The convention isn't enforced by a git hook — please follow it by hand.

### Shape

```
<type>(<scope>)?: <short description>

[optional body]

[optional footer(s)]
```

### Types We Use

| Type        | Meaning                                                    | Release (from 1.0) |
| ----------- | ---------------------------------------------------------- | ------------------ |
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

### Breaking Changes

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

### Scope (Optional but Encouraged)

The scope is usually the area touched — `scraper`, `registry`,
`dev-ui`, the site name (`cherrypimps`, `czechav`), or `deps` for
dependency bumps.

## Linting, Formatting and Types

This repo uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting (it also
keeps imports sorted), [mypy](https://mypy-lang.org/) for static type-checking, and
[pytest](https://docs.pytest.org/) with respx for tests. Run the full gate before every
commit — CI runs the same checks:

| Command | What it does |
| --- | --- |
| `ruff format` | Format the code (CI runs `ruff format --check`, which only checks) |
| `ruff check` | Lint (`--fix` auto-fixes what's safe) |
| `python scripts/check_comments.py` | Enforce the comment rules (CI checks the commit's own diff) |
| `mypy phoenixadult` | Static type-check the `phoenixadult/` package |
| `pytest` | Run the test suite, including the UI strings check and the event-loop guards |

Tests mirror the source tree under `tests/` — one test module per source module.
New scrapers should land with a fixture-driven test; see
[docs/scraper-test-plan.md](./docs/scraper-test-plan.md).

### Continuous Integration

The canonical repository is on Codeberg, mirrored to GitHub, and both run CI:

- **Codeberg** (`.forgejo/workflows/`): the gate, and the docs deploy to Codeberg Pages.
- **GitHub** (`.github/workflows/`): the same gate (also weekly), a docs typecheck and
  build on pull requests with a deploy to GitHub Pages from `main`, and a Docker check
  that builds the image and waits for `/health`.
- **Dependabot** (`.github/dependabot.yml`) opens weekly update PRs on GitHub. Merging one
  puts GitHub ahead of Codeberg, so pull it locally and push to both remotes.

The two `ci.yml` files name each other; change both when the gate changes.

## Versioning

The project version is written in exactly one place, `__version__` in
`phoenixadult/__init__.py`. Everything else derives from it: `pyproject.toml`
declares `dynamic = ["version"]` and reads that attribute, and the version Plex is
told (`PROVIDER_DEFINITIONS[0].version`) comes from `provider_version()`, which
spells the PEP 440 form out for display — `1.0.0a412` becomes `1.0.0-alpha.412`.
`tests/framework/test_version.py` fails if any of those are re-hardcoded, because the Plex
version silently drifted 29 releases behind the package once already.

Note this means `grep '^version' pyproject.toml` no longer returns anything — read
`phoenixadult/__init__.py` instead, or `python -c "import phoenixadult; print(phoenixadult.__version__)"`.

While in alpha, every release increments the alpha number. `python scripts/bump_version.py`
does it in place (`--read` prints the current version). The bump rides inside the last
content commit of a change, never as a separate release commit, and tests-, docs- or
CI-only changes don't bump at all.
