# Milestone 9B: operator device revocation

M9B ends at authoritative website revocation and device-slot release. Desktop online
revocation detection is deferred to M9C. An already downloaded offline licence is not
changed or invalidated by this milestone.

## State and history

Only a selected AUTHORIZED activation can transition to REVOKED. REVOKED is terminal
for that activation ID, enforced by migration `0011_device_revocation.sql`. The
migration adds nullable `revocation_reason_code` and `revocation_reason_text` columns
without rebuilding tables or changing licence foreign keys. Pre-existing records
remain unchanged; legacy revoked records without a matching reason fail closed.
There is no existing activation revision, so the endpoint guards the expected state.

Only AUTHORIZED records consume the existing account device limit. Revocation does
not modify the application, account entitlement, other activations, licence metadata,
or signed/publication bytes. A FLAGGED replacement remains FLAGGED until it repeats
the normal authenticated activation flow. The same physical device can register
again with a new activation ID while its revoked history remains intact.

## Operator endpoint

`POST /api/operator/activations/:activationId/revoke`

Use `Authorization: Bearer <dedicated credential>` and JSON content type. Configure
`OPERATOR_ACTIVATION_REVOKE_TOKEN` on the website and the matching
`QS_OPERATOR_ACTIVATION_REVOKE_TOKEN` in Licence Manager. Read, status-sync, metadata,
and publication credentials do not authorize revocation. Production requires HTTPS.
The local launcher imports the dedicated value from `.dev.vars`; never commit it.

```json
{
  "schema_version": 1,
  "reason_code": "DEVICE_REPLACED",
  "expected_status": "AUTHORIZED"
}
```

Controlled reasons: DEVICE_REPLACED, DEVICE_LOST, USER_REQUEST, BETA_ACCESS_REVOKED,
ADMINISTRATIVE, OTHER. Optional `reason_text` accepts a trimmed, nonempty note of at
most 240 characters without control characters. The UI requires a reason and does
not request free-form notes. Notes are stored but not echoed in responses or audits.

Success (HTTP 200) has exactly `schema_version`, `activation_request_id`, `status`
(REVOKED), `result` (revoked/already_revoked), `revoked_at`, and `reason_code`.
An identical retry preserves the first timestamp/reason and writes no second audit.
A different reason/note or incompatible/stale state returns HTTP 409
`activation_conflict`. Missing IDs return 404, malformed JSON/payload returns 400,
missing/rejected authentication returns 401/403, and unavailable storage returns 503.
Bodies are bounded to 2048 bytes. Errors contain controlled codes only.

The guarded update and one OPERATOR_DEVICE_REVOKED audit event share a D1 batch
transaction. The audit records application linkage, activation ID, source/target
state, timestamp, and controlled reason code. Audit failure rolls back revocation.
A lost response or post-commit read failure can be retried with the identical request;
no entitlement/provisioning work is performed. Concurrent identical requests yield
one revoked and one already_revoked result; conflicting requests fail closed.

## Licence Manager

Activation Requests -> Website beta activations -> select one AUTHORIZED row ->
Revoke device -> select controlled reason -> confirm the activation ID and decision.
The action is disabled for other states. The server outcome is validated before
refreshing. A successful response disables issuance for that activation even if the
following read refresh fails. Authentication, network/unknown outcome, conflict,
already revoked, and unexpected response have distinct safe messages. On an unknown
network outcome, refresh and retry with the same reason if needed.

M8 code is unchanged: it already ignores non-AUTHORIZED history, including revoked
records with published licences. Existing envelopes remain historical. A replacement
licence inherits the original account expiry, rather than a fresh 90-day term.

## Local TEST manual QA

1. Apply all local migrations, including 0011, using the existing local migration
   command. Preserve current QA data; no database reset is required.
2. Set a separate local `OPERATOR_ACTIVATION_REVOKE_TOKEN` in `website/.dev.vars`.
   Reload the local launcher environment, restart website and Licence Manager so
   both receive the matching dedicated value. Keep TEST signing/trust settings.
3. Approve a fresh account. Record its entitlement ID, starts_at, expires_at,
   device_limit=1, and revision. Authenticate Device A normally; verify AUTHORIZED.
4. Authenticate a different Device B for the same account; verify FLAGGED/DEVICE_LIMIT.
5. Refresh Licence Manager activations, select Device A, choose Revoke device,
   select DEVICE_REPLACED, and confirm. Refresh: A must show REVOKED. B must still
   show FLAGGED. Verify one audit and the stored revocation reason/timestamp.
6. Retry authentication/activation normally on Device B. It may now become AUTHORIZED.
   A remains REVOKED. Do not edit rows manually to authorize B.
7. Run the existing M8 TEST worker. Verify it skips A and issues/publishes for B.
   B's signed licence expiry must equal the originally recorded account expiry.
   A's old signed envelope/publication must remain byte-for-byte unchanged.
8. Verify entitlement ID/dates/limit/revision are unchanged. Retry the exact revoke
   request: already_revoked, same revoked_at/reason, one audit. A different reason
   must conflict. Try registering A again only after releasing any occupied slot;
   its new activation ID must differ from the preserved REVOKED history.

These are manual QA instructions, not a claim of completed manual click-through.
No M9C online checks, offline grace, billing, renewal, self-service, or production
signing changes are included.

M9C desktop authorization is now implemented; the earlier milestone descriptions above are historical. See [ONLINE_AUTHORIZATION.md](ONLINE_AUTHORIZATION.md) for current no-offline-grace behavior, protocol, gating, and two-device QA.
