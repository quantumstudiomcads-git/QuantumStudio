# Automatic issuance after device authorization

`registerActivationForUser` is shared by authenticated browser activation and
browser-confirmed desktop sign-in. Its activation upsert commits before readback.
After readback and identity conflict validation, an AUTHORIZED activation in
staging or production invokes the existing `issueLicenceViaService` function.
Admin Issue Licence continues to call that same function.

The existing Pages service binding, HMAC caller, private Worker eligibility,
Durable Object serialization/idempotency, signature verification and immutable
publication path remain authoritative. Pages never signs or constructs grants.
Local TEST issuance stays with the existing operator worker.

The call is awaited in the authorization request, using the existing 30-second
service timeout. No queue or background infrastructure is introduced. Signer
failure does not undo authorization or change its success response. A pending
failure emits only `qs-automatic-licence-issuance-pending` with the validated
environment and integer HTTP status; no identities, credentials or bodies.

A new authenticated activation/sign-in attempt retries issuance for an existing
AUTHORIZED record. Repeated or concurrent calls rely on existing private signer
idempotency and immutable publication consistency checks. Already-current
publication succeeds. There is no new scheduled retry loop: the administrator
can use Issue Licence for recovery if the initial call fails or is interrupted.
A consumed desktop challenge retains its existing single-use behavior.

The desktop contract is unchanged. It receives AUTHORIZED through the existing
challenge/poll flow, then retrieves the licence using device proof. Pending
publication continues to show the existing licence-pending state. If signing is
still in progress, polling may remain pending until confirmation completes.

Before staging deployment verify the Pages SIGNING_SERVICE binding, caller
secret, licence trust and private Worker authoritative website configuration.
Expect extra signer requests for authenticated authorization retries; existing
rate limits, HMAC freshness and private signer serialization still apply.
Temporary signing conflicts stay pending; they do not bypass eligibility.

Only Pages code needs deployment for this feature. No migration, new variable,
private Worker change or desktop rebuild is required by automatic issuance.
The separately pending Windows rebuild for the completed licence-display fix
remains necessary and unchanged. Beta entitlement/Profile/Pro mapping is intact.
