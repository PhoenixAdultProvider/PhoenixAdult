import type { SidebarsConfig } from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docs: [
    { type: 'category', label: 'Getting started', collapsed: false, items: ['hosting', 'configuration'] },
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
      items: ['sitelist', 'selectors', 'healthcheck', 'site-health'],
    },
    {
      type: 'category',
      label: 'Development',
      collapsed: true,
      items: ['DESIGN', 'dev-ui', 'scraper-test-plan', 'notes'],
    },
  ],
};

export default sidebars;
