import { themes as prismThemes } from 'prism-react-renderer';
import type { Config } from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'PhoenixAdult',
  tagline: 'A Plex metadata provider for adult content (FastAPI / Python)',
  favicon: 'img/favicon.ico',

  future: {
    v4: true,
  },

  // GitHub Pages URL: https://phoenixadultprovider.github.io/PAProvider/
  url: 'https://phoenixadultprovider.github.io',
  baseUrl: '/PAProvider/',

  organizationName: 'PhoenixAdultProvider',
  projectName: 'PAProvider',
  deploymentBranch: 'gh-pages',
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
          editUrl: 'https://github.com/PhoenixAdultProvider/PAProvider/edit/main/',
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
          href: 'https://github.com/PhoenixAdultProvider/PAProvider',
          label: 'GitHub',
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
            { label: 'GitHub', href: 'https://github.com/PhoenixAdultProvider/PAProvider' },
            { label: 'Issues', href: 'https://github.com/PhoenixAdultProvider/PAProvider/issues' },
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
