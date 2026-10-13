# Quantum Studio Website

Independent product website and documentation repository for Quantum Studio.

## Stack

- Docusaurus 3.10.2
- React 19
- TypeScript 6
- Markdown / MDX
- Mermaid
- GitHub Pages compatible

All core site tooling is open source. No paid documentation, hosting, analytics, or search service is required by this baseline.

## Requirements

Node.js 20 or newer. Node 22 LTS is recommended for this repository.

## Local development

```bash
npm install
npm run start
```

Docusaurus serves the development site at `http://localhost:3000` by default.

## Validation

```bash
npm run typecheck
npm run build
npm run serve
```

## GitHub Pages

The checked-in configuration assumes the repository is:

```text
kalapatapubhargava/QuantumStudio-Website
```

and therefore uses:

```text
https://kalapatapubhargava.github.io/QuantumStudio-Website/
```

In GitHub, set **Settings → Pages → Source** to **GitHub Actions**.

When a custom domain is purchased later:

1. change `url` in `docusaurus.config.ts` to the domain;
2. change `baseUrl` to `/`;
3. add `static/CNAME` containing the domain.

## Content architecture

```text
docs/
├── getting-started/
├── builder/
├── calculate/
├── analyze/
├── tutorials/
├── concepts/
├── reference/
└── troubleshooting/
```

This is intentionally structured for long scientific tutorials and versionable user guides.

## Brand assets

`static/img/brand/quantum-studio-v0.1.svg` is the canonical Quantum Studio SVG copied from the application repository for this website. Keep the original application asset unchanged; do not redraw, recolour, or rasterize the mark.
