import type { SidebarsConfig } from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docs: [
    { type: 'category', label: 'Getting Started', collapsed: false, items: ['hosting', 'configuration'] },
    {
      type: 'category',
      label: 'Guides',
      collapsed: false,
      items: ['guides/plex-connections', 'guides/metadata-cache', 'guides/people-cache'],
    },
    {
      type: 'category',
      label: 'Usage',
      collapsed: false,
      items: ['manualsearch', 'file-naming'],
    },
    {
      type: 'category',
      label: 'Reference',
      collapsed: false,
      items: ['sitelist', 'selectors', 'healthcheck', 'site-health', 'database'],
    },
    {
      type: 'category',
      label: 'Development',
      collapsed: true,
      items: [
        {
          type: 'category',
          label: 'Design',
          link: { type: 'doc', id: 'design/index' },
          items: [
            'design/use-cases',
            'design/web-ui',
            'design/components',
            'design/data-model',
            'design/scrapers',
            'design/request-flows',
            'design/concurrency',
            'design/http-bypass',
            'design/people',
            'design/security',
            'design/configuration-model',
            'design/deployment',
            'design/conventions',
            'design/directory-map',
            'design/title-case',
          ],
        },
        'dev-ui',
        'scraper-test-plan',
      ],
    },
  ],
};

export default sidebars;
