import type { ReactNode } from 'react';
import { Redirect } from '@docusaurus/router';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';

export default function Home(): ReactNode {
  const { siteConfig } = useDocusaurusContext();
  return <Redirect to={`${siteConfig.baseUrl}hosting`} />;
}
