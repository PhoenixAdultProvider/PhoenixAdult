import { themes as prismThemes } from 'prism-react-renderer';
import type { Config } from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

// Host-agnostic: defaults target Codeberg Pages (the live deploy). Override these
// env vars to build the same config for another host (e.g. GitHub Pages).
const repoUrl = process.env.DOCS_REPO_URL ?? 'https://codeberg.org/PhoenixAdultProvider/PhoenixAdult';
const repoLabel = process.env.DOCS_REPO_LABEL ?? 'Codeberg';
const siteUrl = process.env.DOCS_SITE_URL ?? 'https://phoenixadultprovider.codeberg.page';
const siteBaseUrl = process.env.DOCS_BASE_URL ?? '/PhoenixAdult/';
// Forgejo/Codeberg edit path is /_edit/<branch>/; GitHub uses /edit/<branch>/.
const editUrl = process.env.DOCS_EDIT_URL ?? `${repoUrl}/_edit/main/docs/`;

const config: Config = {
  title: 'PhoenixAdult',
  tagline: 'A Plex metadata provider for adult content (FastAPI / Python)',
  favicon: 'img/favicon.svg',

  future: {
    v4: true,
  },

  url: siteUrl,
  baseUrl: siteBaseUrl,

  organizationName: 'PhoenixAdultProvider',
  projectName: 'PhoenixAdult',
  deploymentBranch: 'pages',
  trailingSlash: false,

  onBrokenLinks: 'warn',

  markdown: {
    mermaid: true,
    hooks: { onBrokenMarkdownLinks: 'warn' },
  },

  themes: ['@docusaurus/theme-mermaid'],

  i18n: { defaultLocale: 'en', locales: ['en'] },

  presets: [
    [
      'classic',
      {
        docs: {
          // Source the existing top-level docs/ folder rather than website/docs.
          path: '../docs',
          // `*-details.md` are giant per-site dumps — keep them out of the published nav.
          // The summary `site-health.md` is included and refreshes when the checker runs.
          exclude: ['site-health-details.md', 'site-health-new.md', 'site-health-new-details.md'],
          sidebarPath: './sidebars.ts',
          routeBasePath: '/',
          editUrl,
        },
        blog: false,
        theme: { customCss: './src/css/custom.css' },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    colorMode: { respectPrefersColorScheme: true },
    navbar: {
      title: 'PhoenixAdult',
      items: [
        { type: 'docSidebar', sidebarId: 'docs', position: 'left', label: 'Docs' },
        {
          href: repoUrl,
          label: repoLabel,
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Docs',
          items: [
            { label: 'Hosting', to: '/hosting' },
            { label: 'Manual search', to: '/manualsearch' },
            { label: 'Site list', to: '/sitelist' },
          ],
        },
        {
          title: 'Project',
          items: [
            { label: repoLabel, href: repoUrl },
            { label: 'Issues', href: `${repoUrl}/issues` },
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} PhoenixAdult contributors.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'json', 'yaml', 'python'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
