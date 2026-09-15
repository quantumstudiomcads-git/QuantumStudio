# 24. Licensing and Plans

This chapter records current B4 client policy and behaviour. Commercial policy
is not the same thing as a currently implemented server purchase or sign-in
flow.

| Plan | Policy | Current relevant capability |
| --- | --- | --- |
| Free Starter | $0; 7 days; 1 device | No Device Builder. |
| Student | $20/month; 1 device | Explicit primitive grants: calc:scf, calc:nscf, calc:phonons; no Device Builder. |
| Plus | $50/month; 1 device | Broader automated-workflow policy; no Device Builder. |
| Plus Trial | $20 for 7 days | Plus-equivalent policy; billing credit is server-side future work; no Device Builder. |
| Pro | $80/month; 1 named user; 2 registered devices; 1 active session | Device Builder included. |
| Organization | $200/month; 5 named seats; +$35/month extra seat; 1 session/seat | Device Builder included. |
| Enterprise | Future | No current client workflow documented. |

## Current client behaviour

Quantum Studio can show safe local status, initialize a per-user encrypted
device identity, and enforce local capability decisions. Paid capability
requests fail closed when no valid entitlement is present. Project Hub, existing
project reading, existing Result reading, Analyze, and supported user-owned
export remain available according to the current policy.

Device identity storage uses Windows CurrentUser DPAPI. The client does not use
a plaintext private-key fallback. Device Builder is denied for Free Starter,
Student, Plus, and Plus Trial; it is allowed only for Pro and Organization.

## Deferred services

Quantum Studio 0.2.0 does not document a live account sign-in, billing checkout,
student verification portal, organization administration dashboard, production
licence server, server-authoritative session service, or trial authority. Those
are future integrations.

> **Screenshot pending:** A native r28 window-capture surface was unavailable during B5.3; no substitute image was used.
