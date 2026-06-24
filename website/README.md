# Website

The documentation site, built with [Docusaurus](https://docusaurus.io/). It
renders the markdown under the repo's top-level [`../docs`](../docs) folder (not a
`website/docs` folder) — `docusaurus.config.ts` points the docs plugin at
`../docs`, so editing a file there updates the site.

Mermaid diagrams are enabled (`@docusaurus/theme-mermaid`); the design doc and the
request-flow diagrams render natively.

## Develop

```bash
cd website
npm install
npm start          # local dev server with live reload
```

## Build

```bash
npm run build      # static site into website/build/
npm run serve      # preview the production build
```

## Deploy (Codeberg Pages)

The site is published to **Codeberg Pages** at
<https://phoenixadultprovider.codeberg.page/PhoenixAdult/> by the
[`.forgejo/workflows/pages.yml`](../.forgejo/workflows/pages.yml) workflow: on every
push to `main` that touches `website/` or `docs/`, it builds the site and
force-pushes the static output to the `pages` branch, which Codeberg serves.

`url` / `baseUrl` / `editUrl` in `docusaurus.config.ts` are set for that URL. The
`pages` branch is generated — never edit it by hand.

One-time setup on the repo:

1. **Settings → Actions** — enable Actions.
2. **Settings → Actions → Secrets** — add a secret named `CODEBERG_TOKEN` whose value
   is a Codeberg access token: **Settings → Applications → Generate New Token**, give
   it the `write:repository` scope, and copy the generated string (shown once). The
   workflow uses it to push the built site to the `pages` branch.

## Notes

- The generated `docs/sitelist.md` (from `python -m scripts.generate_sitelist`) and
  `docs/site-health.md` (from `python -m scripts.site_health`) are published; the
  giant `*-details.md` dumps are excluded from the nav in `docusaurus.config.ts`.
