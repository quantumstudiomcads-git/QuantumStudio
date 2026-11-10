# Production and staging transactional email

Resend is the configured transactional provider for the existing Quantum Studio
OTP email flow. This implements transport only. OTP generation, ten-minute lifetime,
verifier hashing, issue throttling, consumption and authentication/session behavior
remain in the existing auth code and are unchanged. No real email was sent, real
API key installed, DNS changed or application deployed by this work.

## Server-only architecture

Auth routes call `issueChallengeForUser`, which calls `sendOtpEmail` in
`website/functions/_lib/email-delivery.js`. Providers implement
`send({email, otp, purpose, expiryMinutes})`. Local mode uses its existing test/stub
result; staging/production use `ResendEmailProvider` in `_lib/email/resend.js`.

The Resend adapter calls the fixed official HTTPS `POST /emails` API with Bearer
authentication, JSON, a User-Agent and the configured sender. It sends one recipient,
a plain-text Quantum Studio verification code and the supplied expiry. There was
no prior real-email template; existing generic browser wording is preserved.
[Official Resend send-email API](https://resend.com/docs/api-reference/emails/send-email).

The provider endpoint cannot be configured by callers. Redirects are rejected,
there are no automatic retries and a ten-second deadline covers the request AND
response body. The attempt is aborted on completion/failure/timeout. A success
requires a bounded JSON acknowledgement containing only a valid provider UUID `id`;
HTTP acceptance alone or an API error body is not success. Acceptance means the API
accepted the message, not that it reached the recipient's inbox.

Only Pages Functions import this provider. The API key is read from runtime bindings,
held in a private class field, and never placed in browser payloads, Docusaurus public
configuration, desktop configuration, logs, Git or an environment-variable default.
The static build accepts public settings only. Automated checks build with a synthetic
secret canary while network fetch is disabled, then scan final public artifacts for
that canary, the key binding name and provider transport code.

## Environment behavior and configuration

| Setting | Local | Staging / production |
| --- | --- | --- |
| `BETA_ENVIRONMENT` | Existing explicit `local` (`test` alias retained) | Exact deployed profile |
| `AUTH_EMAIL_TEST_MODE` | Existing `true` UI test-code flow remains available | Must remain false/unset; enabled values fail deployment validation |
| `AUTH_EMAIL_PROVIDER` | Not required or used | Required exact `resend` |
| `AUTH_EMAIL_FROM` | Not required or used | Required approved sender, syntax below |
| `RESEND_API_KEY` | Not required or used | Required encrypted Pages runtime secret |

Local mode never calls Resend, even if provider variables happen to be present.
The existing `local-dev`/`stub` result and `devOtp` response remain available under
explicit local mode. OTP console logging was removed; the existing local auth UI
already displays `devOtp`. This does not grant test delivery in a deployed profile.

Configure variables/secrets in the matching Pages dashboard slot. A dedicated
staging project's Pages Production slot may still correctly use
`BETA_ENVIRONMENT=staging`; do not confuse that slot label with application mode.
Use independent staging and production API keys and sender registrations, restricted
to sending access/the appropriate domain where supported. The service needs no Resend
SDK, provider-template ID, domain-management credential, webhook secret or new database
column. No actual key value belongs in tracked examples or a public build setting.

`AUTH_EMAIL_FROM` accepts a simple ASCII mailbox or an optional simple display name:

```text
<APPROVED_MAILBOX>@<VERIFIED_SENDER_DOMAIN>
Quantum Studio <APPROVED_MAILBOX@VERIFIED_SENDER_DOMAIN>
```

Use the normal `Name <mailbox@domain>` shape with a space before `<`. Mailbox local
parts support letters/digits and common dot/underscore/plus/hyphen characters;
quoted/complex RFC mailboxes, multiple senders, CR/LF/control characters, malformed
DNS labels, local/IP hosts and placeholder domains are rejected. Validation proves
syntax only, not account ownership, DNS verification or provider acceptance. API
keys are checked for the `re_` token shape and placeholders, but real validity and
sender authorization remain Resend's responsibility.

## DNS dependency and exact post-verification configuration

`quantumstudiomcads.com` is awaiting DNS access/verification. Do not perform real
send tests or add a usable API key to the running website until verification is
complete. Keeping `RESEND_API_KEY` unset makes the email path fail closed BEFORE
any provider request, while the existing configured non-email paths remain usable.

Manual prerequisites:

1. Obtain authorized DNS access, add the intended sender domain/subdomain in Resend,
   and apply the exact verification records Resend supplies. Do not guess DNS records.
2. Confirm the domain reports verified in Resend. A staging subdomain used for sending
   must itself be registered/verified; a staging WEBSITE hostname does not automatically
   become an email sender domain. Choose and approve the sender mailbox/display name.
3. Provision independent sending-scoped staging/production API keys and add each as
   the encrypted `RESEND_API_KEY` secret in the matching Pages environment. Do not reuse
   operator credentials, OTP peppers or private licence-signing keys for this purpose.
4. After separate deployment/testing authorization, configure the approved sender
   and perform a controlled delivery acceptance test. This implementation does not
   perform that test or make DNS/provider/account changes.

Resend requires verified sending domains and supports separate verified subdomains.
[Resend domain verification](https://resend.com/docs/dashboard/domains/introduction),
[API key scope](https://resend.com/changelog/new-api-key-permissions).

After verification, one possible MANUAL configuration is below. The mailbox is an
example requiring approval, not a hardcoded application sender:

```dotenv
BETA_ENVIRONMENT=staging
AUTH_EMAIL_TEST_MODE=false
AUTH_EMAIL_PROVIDER=resend
AUTH_EMAIL_FROM="Quantum Studio <no-reply@quantumstudiomcads.com>"
```

Set the encrypted `RESEND_API_KEY` to the separately approved STAGING sending key.
For production, set `BETA_ENVIRONMENT=production` and use its independent key and
approved production sender. A separately verified staging sender subdomain can
replace the root-domain mailbox. No real credentials or sender defaults are shipped.

## Safe failures and unchanged auth semantics

The internal result distinguishes `kind=configuration` (missing/invalid settings,
invalid deployment mode or provider HTTP 401/403) from `kind=delivery` (network,
HTTP rejection, malformed/oversized acknowledgement, invalid internal message or
timeout). Reasons are fixed codes, with no email, OTP, API key, provider message or
raw response attached. Provider failure bodies are not read or logged. No provider
success/failure data is written to the existing challenge record.

Existing auth code maps every email delivery failure to the unchanged HTTP 503
message `Verification delivery is temporarily unavailable.` Deployed successes do
not contain `devOtp`; browser auth responses keep `devOtp: null`. Provider identifiers
and credentials are not added to public responses. There is no fallback to stub/test
email in staging or production and no automatic credential/endpoint downgrade.

A timeout can be ambiguous: Resend may have accepted a request before the connection
timed out. The adapter does not retry automatically or mutate authentication policy.
The existing challenge may already have been persisted before delivery was attempted;
its expiry/throttle/consumption behavior is preserved. User-requested resend continues
through the existing path. This transport implementation does not fix or redesign
separately audited OTP/OAuth behavior.

All automated provider calls are mocked. The public-build leakage test uses only a
synthetic key and forbids fetch in its build subprocess. Real deliverability, DNS,
provider permissions, account limits and staged delivery acceptance remain manual
and blocked until sender verification is complete.
