# B4 future server connector contract

The desktop uses browser authentication and signed entitlement responses. It
does not collect passwords, process payment webhooks, retain billing tokens, or
contain a provider client secret. Native authentication is expected to use OIDC
Authorization Code with PKCE and the system browser.

B4 provides abstract protocols and an in-memory test connector only. The
application makes no network request at startup.

| Operation | Illustrative endpoint | Response |
|---|---|---|
| Register device | `POST /v1/devices/register` | device ID, signed device lease |
| Deactivate device | `POST /v1/devices/deactivate` | revocation acknowledgement |
| Refresh lease | `POST /v1/leases/refresh` | signed device lease |
| Get status | `GET /v1/entitlements` | signed lease/current status |
| Open/refresh/close session | `/v1/sessions/*` | short-lived session claim/acknowledgement |
| List devices | `GET /v1/devices` | redacted device records |
| Plan catalogue | `GET /v1/plans` | display-only plan metadata |

Registration receives a generated device public key and minimal display
metadata—not MAC addresses, CPU serials, motherboard serials, or broad
hardware inventory. The lease binds both device ID and public-key hash.

The server owns subscription state, trial consumption, device/replacement rate
policy, named-seat assignment, extra-seat quantities, revocation, concurrent
sessions, offline duration, student verification, and promotional credit.
Organization seats are named accounts, never a shared token. Pro permits two
registered devices but one concurrent named-user session.

Adjacent contracts are `AuthConnector` (PKCE), `PlanCatalogConnector`
(non-authoritative display metadata), `BillingConnector` (server-side events
such as subscription/trial/seat changes), and `StudentVerificationConnector`
(`UNVERIFIED`, `PENDING`, `VERIFIED`, `EXPIRED`). Student documents and billing
webhooks remain server-side. The future Plus Trial credit is billing policy,
not desktop accounting.
