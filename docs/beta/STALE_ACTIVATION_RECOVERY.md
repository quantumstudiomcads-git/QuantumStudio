# Individual stale activation recovery

The admin UI and its normal revoke action remain AUTHORIZED-only. Operators may
explicitly retire one never-authorized, unissued FLAGGED activation using the
existing POST `/api/operator/activations/<activation_request_id>/revoke` endpoint.

Authenticate using `Authorization: Bearer <OPERATOR_ACTIVATION_REVOKE_TOKEN>`.
The token stays on the operator workstation; never put it in browser JavaScript.
Use the token configured on the target environment's Pages deployment.

Before recovery, inspect the authoritative activation export using its separate
read credential. Verify the exact stale activation ID, FLAGGED state, null
`authorized_at`, and null `licence_id`. Record the current AUTHORIZED activation
and entitlement so they can be compared afterwards. Do not identify the target
by installation ID alone.

Send JSON (Content-Type: application/json):

```json
{
  "schema_version": 1,
  "expected_status": "FLAGGED",
  "reason_code": "ADMINISTRATIVE",
  "reason_text": "Retire stale never-authorized activation"
}
```

Only the URL's exact activation ID can change. The state and never-authorized,
unissued restrictions are rechecked in the SQL update. A successful atomic batch
sets REVOKED, timestamp, reason and a durable OPERATOR_DEVICE_REVOKED audit event
with old_status FLAGGED and actor operator-stale-activation-recovery. It preserves
history, flag reason, other activations, entitlements and signed envelopes.

Repeat only the identical request after a lost response. Identical retries return
already_revoked without another audit or timestamp change. HTTP 409 means stop
and re-inspect; do not change the expected state to force the operation.

Re-read both activations and the entitlement. Confirm only the stale record was
revoked, then retry issuance for the current AUTHORIZED activation. Signer conflict
validation is unchanged. This operation does not promise that other eligibility
checks will pass.

This recovery API requires a Pages deployment containing the change. No migration,
signing Worker change or desktop rebuild is required. No remote recovery is run by
these instructions automatically.
