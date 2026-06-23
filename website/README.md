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

## Notes

- The generated `docs/sitelist.md` (from `python -m scripts.generate_sitelist`) and
  `docs/site-health.md` (from `python -m scripts.site_health`) are published; the
  giant `*-details.md` dumps are excluded from the nav in `docusaurus.config.ts`.
- `url` / `baseUrl` / `organizationName` / `projectName` / `editUrl` in
  `docusaurus.config.ts` assume GitHub Pages at
  `https://phoenixadultprovider.github.io/PAProvider/` — adjust them to match the
  actual repository remote before deploying.
