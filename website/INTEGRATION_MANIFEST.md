# Quantum Studio website restoration manifest

This file records the controlled restoration of the canonical website starter and content package.

## Source packages

- Starter: `QuantumStudio-Website-starter.zip`
- Content: `QuantumStudio-Website-content-pack.zip`

## Starter files

The Docusaurus starter was restored intact, including its initial `.git` metadata,
configuration, public documentation skeleton, brand assets, and GitHub Actions
workflows. The included Git repository had an unborn `main` branch, no commit,
and no remote.

## Integrated content-pack files

- `docs/calculations/*.mdx` (23 selected public calculation-reference documents)
- Content concepts used to build the public catalogue and resource navigation

The three stale pack labels were mapped to the current product vocabulary:
Spin Texture and SOC PDOS are `PARTIAL`; Exchange Parameters is `PLANNED`.

## Deliberately skipped content-pack files

- `docs/user-guide/*.mdx` and `src/pages/user-guide.tsx`: complete manual
  content, intentionally not exposed in this public build.
- `static/downloads/Quantum_Studio_User_Guide_through_v0.21.pdf`: protected
  manual asset, intentionally not copied into `static/`.
- `src/pages/index.tsx`, `src/pages/calculations.tsx`, `sidebars.ts`, and
  `src/css/quantumatk-clickable.css`: the pack's version pre-dated the
  controlled 0.2.0 beta requirements and was replaced by the MVP's current
  navigation, readiness vocabulary, and dark graphite visual system.

## Conflicts and resolution

- Troubleshooting: the one canonical source remains
  `docs/troubleshooting/index.mdx`; the sidebar uses its document ID
  `troubleshooting/index` and all public links use `/docs/troubleshooting`.
- No framework configuration from the content pack was silently replaced.
- No protected manual, applicant data, private key, secret, Engine Pack, or
  application binary was copied into the website.
