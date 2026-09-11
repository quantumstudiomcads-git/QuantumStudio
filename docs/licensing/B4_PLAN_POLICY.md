# B4 plan policy (current commercial input)

Prices are billing/display policy, never desktop authorization. Signed feature
and calculation grants remain authoritative and centrally configurable.

| Plan | Commercial policy | Device/session | Device Builder | Initial grants |
|---|---|---|---|---|
| Free Starter | $0, 7 days | 1 device, 1 session | No | core workspace trial |
| Student | $20/month | 1 device, 1 session | No | core plus `calc:scf`, `calc:nscf`, `calc:phonons` |
| Plus | $50/month | 1 device, 1 session | No | broader ready calculations |
| Plus Trial | $20, 7 days | 1 device, 1 session | No | Plus-equivalent short lease |
| Pro | $80/month | 2 devices, one user, 1 session | Yes | ready calculations and Device Builder |
| Organization | $200/month includes 5 seats; +$35/seat | named seats, server device policy, 1 session/seat | Yes | ready calculations and Device Builder |
| Enterprise | deferred | custom future policy | server controlled | future policy |

Student does not receive an arbitrary shell. All execution stays structured and
validated. `nscf` is a stable student entitlement key but is still subject to
the independent implementation-readiness gate; payment never creates missing
science.

B4 deliberately introduces no project-count limits. Future server policy can
manage replacement, deactivation, primary offline device, organization invites,
and pricing without client redesign. The Plus Trial purchase credit belongs to
the billing service, not QuantumStudio.exe.
