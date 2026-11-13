# Beta entitlement and desktop licence display

These existing identifiers represent different layers:

- `account_entitlements.plan_id = beta`: the authoritative 90-day account grant,
  created by approval triggers in website/migrations/0010_activation_history.sql;
  its schema is in 0009_account_entitlements.sql.
- Signed `plan_id = pro`: the established licence tier, explicitly set in
  operator_tools/licence_manager/issuance.py. Deployed verification and Pages
  envelope validation already require this value for beta licences.
- Signed `policy_profile = PROFESSOR_BETA` and `channel = beta`: the beta licence
  profile and distribution channel.

The exported account_entitlement object contains entitlement_id, user_id,
application_id, plan_id, starts_at, expires_at, device_limit, revision, created_at
and updated_at. It is validated before issuance. Expiry and device limit come
from this grant; they are not replaced with Pro template defaults.

The private service calls issue_website_activation using its injected profile
provider. The Python Worker loads the build-generated frozen_profile.PROFILE,
whose build source is the canonical derive_profile(PROFESSOR_BETA). This grants
core workspaces plus Device Builder and implemented calculation intents, rather
than blindly granting every catalogue or planned calculation. Signed explicit
feature/calculation lists remain authoritative.

Account / Licensing previously displayed the signed plan_id as ?Plan?, conflating
licence tier and account entitlement. It now displays ?Licence profile: Professor
beta? and ?Capability tier: pro?. The profile comes only from the verified signed
envelope through safe diagnostics. No account entitlement is inferred from an
unsigned browser response. Existing envelopes remain unchanged.

Duplicate details came from copying licence_summary.text() into the operation
status label after online checks. The status label now gives a short operation
result; the profile, expiry and licence ID appear once in the summary.

This is a desktop display correction. Rebuild the Windows client/installer to
ship it. No reissuance, migration, website/signing deployment or staging data
change is required.
