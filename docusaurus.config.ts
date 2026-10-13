import {themes as prismThemes} from 'prism-react-renderer';
import rehypeKatex from 'rehype-katex';
import remarkMath from 'remark-math';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const isCloudflareLocal = process.env.CLOUDFLARE_LOCAL === 'true';

const config: Config = {
  title: 'Quantum Studio',
  tagline: 'Atomistic and electronic-structure research',
  favicon: 'img/brand/quantum-studio-v0.1.svg',

  url: isCloudflareLocal
    ? 'http://127.0.0.1:8788'
    : 'https://kalapatapubhargava.github.io',

  baseUrl: isCloudflareLocal
    ? '/'
    : '/QuantumStudio-Website/',

  organizationName: 'kalapatapubhargava',
  projectName: 'QuantumStudio-Website',
  trailingSlash: false,
  onBrokenLinks: 'throw',

  customFields: {
    // The site key is public by design. Secrets are available only to Pages
    // Functions through Cloudflare bindings and must never appear here.
    turnstileSiteKey: process.env.TURNSTILE_SITE_KEY ?? '',
    turnstileTestMode: process.env.BETA_TURNSTILE_TEST_MODE === 'true',
  },

  markdown: {
    mermaid: true,
    hooks: {
      onBrokenMarkdownLinks: 'warn',
    },
  },

  stylesheets: [
    'https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.css',
  ],

  themes: ['@docusaurus/theme-mermaid'],

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          routeBasePath: 'docs',
          showLastUpdateAuthor: false,
          showLastUpdateTime: false,
          remarkPlugins: [remarkMath],
          rehypePlugins: [rehypeKatex],
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    image: 'img/brand/social-card.svg',

    colorMode: {
      defaultMode: 'light',
      disableSwitch: true,
      respectPrefersColorScheme: false,
    },

    navbar: {
      title: 'Quantum Studio',
      logo: {
        alt: 'Quantum Studio',
        src: 'img/brand/quantum-studio-v0.1.svg',
      },
      items: [
        {to: '/capabilities', label: 'Capabilities', position: 'left'},
        {to: '/applications', label: 'Applications', position: 'left'},
        {to: '/documentation', label: 'Documentation', position: 'left'},
        {to: '/technical-preview', label: 'Technical Preview', position: 'left'},
        {to: '/contact', label: 'Research Collaboration', position: 'left'},
        {
          to: '/beta-access',
          label: 'Request Beta Access',
          position: 'right',
          className: 'navbar__beta-action',
        },
      ],
    },

    footer: {
      style: 'light',
      links: [
        {
          title: 'Quantum Studio',
          items: [
            {label: 'Capabilities', to: '/capabilities'},
            {label: 'Applications', to: '/applications'},
            {label: 'Technical Preview', to: '/technical-preview'},
          ],
        },
        {
          title: 'Documentation',
          items: [
            {label: 'Overview', to: '/documentation'},
            {label: 'Calculation Catalogue', to: '/calculations'},
            {label: 'Troubleshooting', to: '/docs/troubleshooting'},
          ],
        },
        {
          title: 'Beta',
          items: [
            {label: 'Privacy', to: '/privacy'},
            {label: 'Beta Terms', to: '/beta-terms'},
            {label: 'Research Collaboration', to: '/contact'},
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} Quantum Studio. Controlled technical beta; not a public production release.`,
    },

    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'python', 'json'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;