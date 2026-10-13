# Dependency security decision: serialize-javascript

Decision date: 20 September 2026
Required review date: 20 December 2026
Status: high-severity advisory remediated by a narrow lockfile override; maintainer review remains required.

## Advisory and evidence

- Advisory: [GHSA-5c6j-r48x-rmvq](https://github.com/advisories/GHSA-5c6j-r48x-rmvq)
- npm advisory source: `1113686`
- Severity: high (CVSS 8.1 in `npm audit`)
- Vulnerable range: `serialize-javascript <= 7.0.2`
- Vulnerable installed version before this decision: `6.0.2`
- Patched high-severity range: `>= 7.0.3`; this decision pins `7.1.1`, which also exceeds the separate DoS advisory's `7.0.5` fix level.
- Reported behavior: crafted `RegExp.flags` and `Date.prototype.toISOString()` values could produce code execution through vulnerable serialization.

The package is transitive, not a direct website dependency. The complete immediate dependency paths are:

```text
@docusaurus/core@3.10.2
  -> @docusaurus/bundler@3.10.2
     -> copy-webpack-plugin@11.0.0 -> serialize-javascript@6.0.2
     -> css-minimizer-webpack-plugin@5.0.1 -> serialize-javascript@6.0.2
```

`npm explain serialize-javascript`, `npm ls serialize-javascript --all`, and
the committed lockfile were used to establish these paths.

## Remediation evaluation and selected change

1. No compatible direct-parent patch was available from the existing
   Docusaurus 3.10.2 dependency ranges.
2. An uncontrolled Docusaurus update was not accepted; the audit's proposed
   change was not a compatible, evidence-backed upgrade for this frozen site.
3. A narrow root `overrides` entry was tested with `serialize-javascript@7.1.1`.
   `npm ci`, `npm test`, `npm run typecheck`, `npm run d1:migrate:local`,
   `npm run build`, `npm audit --json`, and `npm ls --all` all passed. The
   resulting audit contains zero high-severity findings and the dependency tree
   has no invalid dependency errors.

The selected override is retained because both immediate parents use the
package's stable serialization interface during the tested static build. It is
not a containment claim: the vulnerable package version is no longer installed.

## Exploitability and remaining controls

The package is used by local/CI webpack build tooling, not by the generated
browser output or Pages Function source. The production build was searched for
`serialize-javascript` and contains no package/module artifact. Pages Functions
contain no import of this package. Website docs/pages are repository-controlled;
there is no untrusted remote-content ingestion in the build configuration.

Controls that remain required:

- use the committed `package-lock.json` with `npm ci`;
- run builds only in isolated CI/operator environments;
- do not expose production Cloudflare secrets to pull-request workflows;
- deploy only from reviewed protected-branch commits after a separate
  authorization gate;
- use the weekly Dependabot configuration in `.github/dependabot.yml`;
- re-run `npm audit --json` and review this override by the required review date.

Residual risk: the override crosses the two parents' original major-version
range, even though the complete install, dependency tree, tests, D1 migration,
and production build pass. This is an engineering remediation decision pending
maintainer review, not a guarantee of future upstream compatibility.
