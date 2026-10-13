# Private beta-registration operations

Status: implementation prepared locally; **not deployed**. This runbook is for authorized operators and contains placeholders only.

## Prerequisites and Pages configuration

After deployment authorization, create the selected Cloudflare Pages project and a D1 database. Replace the all-zero `database_id` in `wrangler.toml` with that database's ID, preserving the `BETA_DB` binding. Configure Pages to run `npm ci && npm run build`, publish `build/`, and include Pages Functions from `functions/`.

Create a Turnstile widget for the approved hostname and `beta_registration` action. Set its public key as the Pages build variable `TURNSTILE_SITE_KEY`. Set Function variables:

```text
BETA_ALLOWED_ORIGIN=https://approved-site.example
BETA_PRIVACY_VERSION=draft-0.1
BETA_TERMS_VERSION=draft-0.1
BETA_ENVIRONMENT=production
```

Set the following only as Function secrets, never build variables or tracked files:

```text
TURNSTILE_SECRET_KEY=<Turnstile secret>
BETA_IDENTITY_PEPPER=<long random server-side value>
```

Do not set `BETA_TURNSTILE_TEST_MODE=true` in production. Production fails closed if the Turnstile secret is missing.

## Local development and migrations

Copy `.dev.vars.example` to ignored `.dev.vars`, replace local placeholders, and use only synthetic data. The local adapter accepts `test-pass` only when the environment is not production.

```powershell
npm ci
npm run d1:migrate:local
$env:TURNSTILE_SITE_KEY = 'local-public-test-value'
$env:BETA_TURNSTILE_TEST_MODE = 'true'
npm run build
npm run pages:dev
```

Wrangler local D1 data is under ignored `.wrangler/`. After authenticated operator review of the selected remote database, an authorized remote migration uses this placeholder command:

```powershell
npx wrangler d1 migrations apply <database-name> --remote --config wrangler.toml
```

Never run remote migrations merely to test this repository.

## Review workflow

The public endpoint records only `APPLIED` and `APPLICATION_SUBMITTED`; it cannot return applicant data, approve, reject, or issue a licence. Later state changes create audit events:

```text
APPLIED -> UNDER_REVIEW -> APPROVED -> LICENSE_ISSUED -> EXPIRED
                     \-> REJECTED
Any eligible active state -> REVOKED
```

`LICENSE_ISSUED` is recordkeeping only. This CLI never signs, generates, emails, or otherwise issues a licence file.

```powershell
node scripts/beta-admin.mjs list --status APPLIED --environment local
node scripts/beta-admin.mjs inspect --application <uuid> --environment local
node scripts/beta-admin.mjs transition --application <uuid> --to UNDER_REVIEW --actor <operator-reference> --environment local
node scripts/beta-admin.mjs transition --application <uuid> --to APPROVED --actor <operator-reference> --environment local
node scripts/beta-admin.mjs transition --application <uuid> --to REJECTED --actor <operator-reference> --environment local
node scripts/beta-admin.mjs record-licence --application <uuid> --licence-id <opaque-licence-id> --expires-at 2030-01-01T00:00:00Z --actor <operator-reference> --environment local
node scripts/beta-admin.mjs transition --application <uuid> --to EXPIRED --actor <operator-reference> --environment local
node scripts/beta-admin.mjs transition --application <uuid> --to REVOKED --actor <operator-reference> --environment local
```

Production commands require both `--environment production` and `--production`. The CLI refuses applicant output in CI.

## Export, deletion, retention, and recovery

Use exports only for an authorized purpose. They are written to ignored `applicant-exports/`; encrypt and securely deliver them, then remove the local copy when its purpose is complete.

```powershell
node scripts/beta-admin.mjs export --status APPROVED --environment local
node scripts/beta-admin.mjs anonymize --application <uuid> --actor <operator-reference> --environment local --confirm-delete
```

Anonymization replaces direct application values with non-personal placeholders, clears optional review content and communications consent, and preserves a non-PII audit record. It is destructive and requires an authorized request. D1 backups may retain historical data until their own policy cycle.

Proposed conservative retention pending counsel approval: rejected applications for 90 days; approved/licence records for the beta period plus 12 months; required audit events for the same period. Do not automate deletion until legal retention and backup policy are approved.

Before production changes, establish and test a D1 backup/export process on non-production data. Changing privacy or terms versions records new values for new applications. Rotate the identity pepper only with a duplicate-lookup migration plan. Roll back Pages using a known-good deployment; do not roll back D1 by deleting records—use a forward migration or approved restore plan.

Deployment remains blocked pending Cloudflare authentication, Pages project, D1 database, Turnstile keys, approved origin, final privacy/legal review, administrator authentication, temporary-licence issuance, controlled artifact hosting, and production update signing.
