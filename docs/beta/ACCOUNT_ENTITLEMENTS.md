# Milestone 9A: fixed beta account entitlements

This phase implements only account entitlement storage/provisioning, fixed expiry,
account device limits, activation history, and TEST issuance integration. It does
not implement revocation endpoints/UI, desktop status APIs, online-validation UI,
protected-action gating, periodic checks, billing, renewal or production signing.
No offline-grace/access logic is added. Existing desktop M7 cache behavior is
unchanged until the later online-validation phase; M9A alone does not enforce
the final online-only policy.

## Provisioning and ownership

`account_entitlements` is separate from application review and device activation.
Its fields are entitlement_id, user_id, application_id, plan_id, starts_at,
expires_at, device_limit, revision, created_at and updated_at. UTC timestamps are
canonical whole-second ISO 8601 values. Beta grants have plan_id `beta`, exactly
90 days, device_limit 1 and revision 1. Positive future device limits need no
schema redesign. One current account grant is supported; billing/renewal history
is outside this phase.

SQLite approval triggers provision the grant and its
ACCOUNT_ENTITLEMENT_PROVISIONED audit event in the existing approval transaction.
They run on a newly inserted approved linked account or the existing
UNDER_REVIEW -> APPROVED transition. Public registration always creates APPLIED;
only the existing approved-account workflow can transition it. Failed/conflicting
status writes cannot provision a grant. Approval retries return already_current
and do not change any entitlement dates or duplicate audit. Activation never
writes account_entitlements. No second human approval is introduced.

The grant starts at the approval review timestamp and ends exactly 90 days later.
The existing status endpoint and assertTransition validation are unchanged.

## Device limit and activation history

`registerActivationForUser` checks account validity before attempting an approved
account registration. Missing, expired or not-yet-valid entitlements return a
controlled denial. Existing AUTHORIZED device state is retained when the account
expires; expiry is not encoded as a device revocation/state transition.

The INSERT ... SELECT / ON CONFLICT write independently rechecks grant dates,
counts AUTHORIZED activations for the same account (excluding the current
device), and compares with the persisted entitlement.device_limit in one SQLite
write. There is no JS read/count/write slot allocation. Concurrent writers are
serialized by the database; two different devices cannot both take the final
slot. Excess devices remain FLAGGED, preserving the existing denial contract.

`BETA_MAX_ACTIVE_DEVICES` defaults to 1 and retains legacy configuration input
validation, but it cannot override or expand entitlement.device_limit. A grant
configured with device_limit 2 works without changing the schema.

Only current (non-REVOKED) account/device rows are unique. Revoked records retain
IDs, timestamps and licence metadata. A new authenticated registration for the
same physical device can create a new activation, rather than resurrecting the
old one. M9A adds no operation that revokes an activation. Future revocation will
release a slot by changing that specific activation's state, not deleting it.

## Existing signer integration

The read-only operator activation export includes the exact public account grant.
The client strictly validates its application binding, UTC timestamps, beta plan,
90-day duration, positive limit and revision. New M5 website issuance requires a
currently valid grant. It records the first grant snapshot in the existing local
operator database transaction and rejects conflicting later grant snapshots.
The existing TEST authority, canonical licence envelope, grants and signing path
are reused. No private key moves to the website.

For new website-path licences:

- issued_at is the current issuance time;
- not_before is max(issued_at, entitlement.starts_at);
- expires_at equals entitlement.expires_at;
- the existing offline_until field retains the same fixed expiry ceiling;
- registered_device_limit reflects the account grant.

`beta` is the account entitlement plan. It maps to the existing PROFESSOR_BETA
profile and signed `pro` capability plan; no new licence format or grant scheme
is introduced. The legacy manually imported request issuance path is unchanged.

An existing activation's stored signed envelope is recovered before new-issuance
checks, without changing its bytes or generating another signature, including
old records without a grant snapshot. Recovery does not invent an account term.
M8 metadata retry, immutable publication and explicit TEST trust are preserved.
Two narrow M8 history changes ignore confirmed revoked history as a competing
current activation/device licence; missing or ambiguous history still blocks.
M8 now reports the existing safe IssuanceRejected entitlement diagnostic.

## Migrations and legacy TEST data

Website migrations are `0009_account_entitlements.sql` and
`0010_activation_history.sql`; apply both before restarting the local website.
The first adds the grant table. The second rebuilds current-device uniqueness,
preserves every activation/publication/device challenge, recreates their foreign
keys/indexes, then installs approval provisioning triggers. Normal D1 migration
transactions provide atomicity; tests additionally exercise actual SQLite with
foreign keys enabled and verify all existing child rows and references survive.
No production or remote migration is performed by this change.

Local operator schema v6 adds only the public website_account_entitlements
snapshot table. Existing matched v4/v5 storage pairs migrate in place after the
existing DPAPI generation checks; protected data keys and signed envelopes are
not replaced.

There is deliberately no automatic legacy backfill. Previously APPROVED accounts
remain without a grant; repeated status sync does not start another 90 days.
Approval also refuses automatic grant creation over existing licence metadata
or AUTHORIZED/REVOKED device history. New signing/authorization then fail closed.
No maximum/latest historical expiry is guessed, and old signatures are not edited.

Safe local QA reset/provisioning procedure:

1. Stop website and worker before migrating. Preserve the existing local D1
   state, matched operator database/DPAPI key pair, trust file and desktop state.
   Do not delete or rewrite them to make an existing licence appear new.
2. Apply the two migrations only to the intended local TEST database. Existing
   approved records without a provable grant remain quarantined for new work.
3. Prefer a fresh disposable TEST account/application: submit APPLIED, then use
   the existing Licence Manager UNDER_REVIEW -> APPROVED workflow and status
   sync. That new approval provisions one explicit 90-day term; activate normally.
   For an isolated fresh QA run, choose a new explicit TEST operator root/trust
   path and a separate desktop runtime-data root. Retain all original paths for
   old licences. Old exported activations may correctly report recovery_required
   against that new operator root; never generate replacements for them.
4. To reuse historical data, first establish the original account grant and exact
   dates through operator review. An explicit local TEST provisioning operation
   must record those original dates and an audit event, never start a term at
   migration/retry/device activation time. No generic legacy provisioning or
   renewal tool is supplied by M9A. If dates cannot be proven, keep it blocked
   and use a new disposable QA account with separate retained history.
5. Keep the worker alive during fresh multi-device TEST QA. The prior M8 ephemeral
   signer/trust restart limitation remains; M9A does not persist private keys or
   silently rotate trust. An old website licence with missing local envelope
   still requires restoration of the original matched operator storage.

The exact signed account alias remains `sub_<application_id>`. Real account
ownership is resolved through application.user_id and the separate grant; there
is no change to desktop identity or explicit TEST trust.

## Validation scope

Focused coverage uses actual approval endpoint SQL/transactions, database triggers,
two concurrent SQLite connections competing for a slot, entitlement export,
M5 signing, M8 recovery/publication, same-device historical replacement, and
migrations containing existing published envelopes and outstanding challenges.
Tests cover duration/default limit, limit 2, partial/repeated approval, immutable
account dates, remaining replacement lifetime, missing/expired/future grants,
legacy quarantine and conflicting local snapshots. Full licensing and website
regressions are required before completion. Manual browser/GUI QA is separate.

## File manifest

Runtime source:

```text
operator_tools/licence_manager/entitlements.py                    (new)
operator_tools/licence_manager/database.py
operator_tools/licence_manager/storage.py
operator_tools/licence_manager/issuance.py
operator_tools/licence_manager/website_sync.py
operator_tools/licence_manager/beta_worker.py
website/functions/_lib/beta-activation.js
website/functions/api/operator/activations.js
```

Migrations:

```text
website/migrations/0009_account_entitlements.sql                  (new)
website/migrations/0010_activation_history.sql                    (new)
```

Tests and fixtures:

```text
tests/helpers/licensing.py                                      (new)
tests/licensing/test_account_entitlements.py                      (new)
tests/licensing/test_website_licences.py
tests/licensing/test_beta_worker.py
tests/licensing/test_licence_delivery.py
tests/licensing/test_private_licence_manager.py
tests/licensing/test_storage_bootstrap.py
website/tests/account-entitlements.test.mjs                       (new)
website/tests/beta-activation.test.mjs
website/tests/desktop-auth.test.mjs
website/tests/licence-delivery.test.mjs
website/tests/helpers/sqlite-d1.mjs
```

Documentation:

```text
docs/beta/ACCOUNT_ENTITLEMENTS.md                                 (new)
docs/beta/LICENCE_MANAGER_ARCHITECTURE.md
docs/beta/LICENCE_MANAGER_OPERATIONS.md
```

No desktop source, signature verifier, signing authority, licence publication,
TEST trust, application-status state machine, or scientific code changes.
Only the necessary M8 history eligibility and safe entitlement diagnostic hooks
are modified; its original signed-envelope recovery/publication paths remain.

Focused validation command, from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/licensing/test_account_entitlements.py tests/licensing/test_website_licences.py tests/licensing/test_beta_worker.py tests/licensing/test_storage_bootstrap.py -q -p no:cacheprovider
```

Full licensing uses `tests/licensing` with the same pytest options. Website tests
run through `npm test` from `website`. Local D1 migration verification additionally
uses temporary isolated Wrangler config/persistence with a populated pre-M9
schema, applies 0009/0010, and asserts original publication/challenge bytes,
foreign keys, and absent guessed legacy grants. Existing local D1 state is not
modified by the validation run.
