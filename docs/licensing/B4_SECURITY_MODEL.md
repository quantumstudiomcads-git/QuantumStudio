# B4 licensing security model

Protected assets are capability grants, registered-device identity, named-seat
assignment, and session policy. User projects, structures, results, and exports
are not DRM collateral. A future signer holds the Ed25519 private key; desktop
builds contain public verification keys and an OS-protected device key only.

Defence layers are: Nuitka compilation (not secrecy), signed versioned leases,
device proof-of-possession, atomic cache/clock detection, centralized policy,
pre-compiler enforcement, server device/seat/session policy, and future
Authenticode. Authenticode establishes binary authenticity; it does not grant a
licence.

Editing a cached plan, expiry, grants, device ID, or signature invalidates the
lease. Copying a lease to another device fails binding validation. Local file
deletion cannot obtain a new server-authoritative trial. UI manipulation cannot
bypass normal calculation-service or Device Builder product composition.

No locally executed application is mathematically unpatchable. Offline clients
cannot receive instant revocation or perfectly coordinate sessions. Those limits
are bounded by signed lease/session lifetime and future server policy; Quantum
Studio makes no claim of absolute DRM.

Never commit/package production private keys, valid-key databases, account or
billing tokens, passwords, provider secrets, or student documents. Logs retain
only redacted licence identity, plan, decision, and expiry. Diagnostics may
contain safe plan/status/expiry/device state; they exclude leases, signatures,
private keys, auth/billing tokens, projects, coordinates, scientific data, and
pseudopotential contents.
