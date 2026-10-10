# Website

The documentation site, built with [Docusaurus](https://docusaurus.io/). It
renders the markdown under the repo's top-level [`../docs`](../docs) folder (not a
`website/docs` folder) — `docusaurus.config.ts` points the docs plugin at
`../docs`, so editing a file there updates the site.

Mermaid diagrams are enabled (`@docusaurus/theme-mermaid`), so the design pages under
`docs/design/` render their diagrams natively. The sidebar is defined in `sidebars.ts`;
add new pages there.

## Develop

```bash
cd website
npm install
npm start          # local dev server with live reload
```

## Build

```bash
npm run typecheck  # tsc over the site's TypeScript (CI runs this too)
npm run build      # static site into website/build/
npm run serve      # preview the production build
```

Broken links only warn (`onBrokenLinks: 'warn'`), so read the build output for them.

## Deploy

The site publishes to two hosts from the same config, on every push to `main` that touches
`website/` or `docs/`:

| Host | Workflow | URL |
| --- | --- | --- |
| Codeberg Pages | [`.forgejo/workflows/pages.yml`](../.forgejo/workflows/pages.yml) — builds and force-pushes the output to the `pages` branch | <https://phoenixadultprovider.codeberg.page/PhoenixAdult/> |
| GitHub Pages | [`.github/workflows/pages.yml`](../.github/workflows/pages.yml) — builds and deploys with the Pages actions | <https://phoenixadultprovider.github.io/PhoenixAdult/> |

Both typecheck before building. On GitHub the same workflow also runs on pull requests
(typecheck and build only, no deploy), which is how Dependabot's npm updates are tested.
`pwsh website/deploy-pages.ps1` publishes to Codeberg Pages by hand, using your local git
credentials, when CI isn't available.

`docusaurus.config.ts` is **host-agnostic**: it defaults to the Codeberg Pages URL and reads
these env vars, which the GitHub workflow sets, so the same config builds for either host.
The `pages` branch is generated; never edit it by hand.

| Env var | Default (Codeberg) | GitHub Pages |
| --- | --- | --- |
| `DOCS_SITE_URL` | `https://phoenixadultprovider.codeberg.page` | `https://phoenixadultprovider.github.io` |
| `DOCS_BASE_URL` | `/PhoenixAdult/` | `/PhoenixAdult/` |
| `DOCS_REPO_URL` | `https://codeberg.org/PhoenixAdultProvider/PhoenixAdult` | `https://github.com/PhoenixAdultProvider/PhoenixAdult` |
| `DOCS_REPO_LABEL` | `Codeberg` | `GitHub` |
| `DOCS_EDIT_URL` | `…/_edit/main/docs/` (Forgejo) | `…/edit/main/docs/` (GitHub) |

### One-Time Setup

- **Codeberg:** enable Actions (**Settings → Actions**), then add a secret named
  `CODEBERG_TOKEN` holding a Codeberg access token with the `write:repository` scope
  (**Settings → Applications → Generate New Token**). The workflow uses it to push the built
  site to the `pages` branch.
- **GitHub:** set **Settings → Pages → Source** to **GitHub Actions**.

## Notes

- The generated `docs/sitelist.md` (from `python -m scripts.generate_sitelist`) and
  `docs/site-health.md` (from `python -m scripts.site_health`) are published; the
  giant `*-details.md` dumps are excluded from the nav in `docusaurus.config.ts`.
