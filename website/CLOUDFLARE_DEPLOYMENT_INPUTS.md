# Cloudflare deployment inputs — do not deploy from this document

Status: placeholders only. Select or create these values only after separate deployment authorization.

| Input | Required value / decision |
| --- | --- |
| Cloudflare authentication | Authorized operator login for `<Cloudflare account>` |
| Pages project name | `<quantum-studio-website>` |
| Production D1 database name | `<quantum-studio-beta-production>` |
| Production D1 database ID | `<Cloudflare D1 database UUID>`; replace the all-zero placeholder in `wrangler.toml` |
| Turnstile widget/site key | `<public Turnstile site key>` as Pages build variable `TURNSTILE_SITE_KEY` |
| Turnstile secret key | `<Turnstile secret>` as Pages Function secret `TURNSTILE_SECRET_KEY` |
| Initial Pages hostname | `<project>.pages.dev` |
| Allowed origin | `BETA_ALLOWED_ORIGIN=https://<approved-hostname>` |
| Privacy version | `BETA_PRIVACY_VERSION=<counsel-approved-version>` |
| Beta terms version | `BETA_TERMS_VERSION=<counsel-approved-version>` |
| Identity pepper | `BETA_IDENTITY_PEPPER=<generated server-side secret>`; generate/inject outside Git and this repository |
| Production branch | `<reviewed protected branch>`; do not deploy pull-request heads |
| Build command | `npm ci && npm run build` |
| Build output directory | `build` |
| Node version | `22` or another operator-approved version compatible with the committed lockfile; validate before deployment |
| D1 migration command | `npx wrangler d1 migrations apply <database-name> --remote --config wrangler.toml` |

## Required deployment sequence

1. Review the dependency decision, legal pages, and protected-branch controls.
2. Create the selected D1 database and securely record its ID outside Git.
3. Apply reviewed migrations to that selected database only.
4. Create the selected Turnstile widget with action `beta_registration` and the approved hostname.
5. Configure public build variables and Function secrets separately.
6. Verify `BETA_ALLOWED_ORIGIN` exactly matches the deployed origin.
7. Deploy only after a fresh `npm ci`, tests, typecheck, audit, and production build.

## Rollback

Rollback Pages to a previously reviewed deployment. Do not roll back D1 by
deleting applicant records; use a forward migration or an approved restore plan.
Before rollback, preserve audit evidence and confirm that no release/artifact,
licence-signing, or update-signing action is being performed.
