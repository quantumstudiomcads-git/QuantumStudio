"""Application-facing entitlement service with fail-closed production defaults."""
from __future__ import annotations

import logging
import hashlib
from copy import deepcopy
from threading import RLock
from datetime import datetime, timezone
from typing import Callable, Mapping

from .canonical import canonical_json
from .device_identity import DeviceIdentityService, SecureStorageUnavailable, production_secure_store
from .lease_store import LeaseStore, LeaseStoreError
from .models import DeviceIdentity, DeviceLease, LicenseDecision
from .policy import EntitlementPolicy
from .verifier import LeaseValidationError, LeaseVerifier

LOGGER = logging.getLogger("quantumstudio.licensing")
CLOCK_ROLLBACK_TOLERANCE_SECONDS = 300


class LicensingService:
    """One UI-facing source of policy decisions; it never exposes raw tokens."""
    def __init__(
        self,
        *,
        trusted_public_keys: Mapping[str, bytes] | None = None,
        device_identity: DeviceIdentity | None = None,
        lease_store: LeaseStore | None = None,
        now: Callable[[], int] | None = None,
        test_mode: bool = False,
    ):
        self.test_mode = bool(test_mode)
        self._install_lock = RLock()
        self._envelope_digest = None
        self._trusted_public_keys = dict(trusted_public_keys or {})
        self.device_identity = device_identity
        self.lease_store = lease_store
        self._now = now or (lambda: int(datetime.now(timezone.utc).timestamp()))
        self.lease: DeviceLease | None = None
        self.error_code: str | None = None
        self.clock_validation_required = False
        self._load_cached_lease()

    @classmethod
    def production(cls) -> "LicensingService":
        """Create a fail-closed production service with no implicit developer grant.

        Trusted production public keys will be injected by the future release
        configuration.  An empty key set is intentional until that authority
        exists; it cannot unlock paid capabilities.
        """
        store = LeaseStore()
        try:
            identity = DeviceIdentityService(production_secure_store(store.paths)).load_or_create()
        except SecureStorageUnavailable as error:
            LOGGER.warning("Device identity unavailable; paid capabilities remain unavailable: %s", error)
            identity = None
        return cls(trusted_public_keys={}, device_identity=identity, lease_store=store)

    @classmethod
    def for_testing(cls, *, trusted_public_keys: Mapping[str, bytes], device_identity: DeviceIdentity, lease: Mapping | None = None, now: Callable[[], int] | None = None) -> "LicensingService":
        service = cls(trusted_public_keys=trusted_public_keys, device_identity=device_identity, now=now)
        if lease is not None:
            service.accept_lease(lease, persist=False)
        return service

    @property
    def policy(self) -> EntitlementPolicy:
        return EntitlementPolicy(self.lease, now=self._now, clock_validation_required=self.clock_validation_required)

    def accept_lease(self, envelope: Mapping, *, persist: bool = True, reset_clock_validation: bool = True) -> DeviceLease:
        if self.device_identity is None:
            self.error_code = "device_identity_unavailable"
            raise LeaseValidationError("A protected device identity is required before accepting a licence.")
        verification = LeaseVerifier(self._trusted_public_keys).verify(envelope, self.device_identity)
        self.lease = verification.lease
        self._envelope_digest = hashlib.sha256(canonical_json(verification.envelope)).hexdigest()
        self.error_code = None
        if reset_clock_validation:
            # A newly verified server-issued timestamp is the recovery route
            # for a prior local-clock rollback warning.
            self.clock_validation_required = False
        self._record_trusted_time(verification.lease.issued_at)
        if persist and self.lease_store is not None:
            self.lease_store.save_lease(verification.envelope)
        LOGGER.info("Accepted signed licence plan=%s licence=%s expiry=%s", self.lease.plan_id, _redact(self.lease.licence_id), self.lease.expires_at)
        return self.lease

    def reload_local_test_trust(self, path):
        """Explicit file-based TEST trust refresh; never a production fallback."""
        import os
        from .local_test_trust import load_test_trust
        if not self.test_mode or os.environ.get("QS_TEST_LICENSING") != "1":
            raise LeaseValidationError("Explicit local TEST licensing is not enabled.")
        keys = load_test_trust(path)
        with self._install_lock:
            cached = self.lease_store.load_lease() if self.lease_store else None
            if self.lease is not None and cached is not None:
                # A changed trust file cannot silently replace an installed issuer.
                LeaseVerifier(keys).verify(cached, self.device_identity)
            self._trusted_public_keys = keys
            if self.error_code in ("test_trust_invalid", "licence_cache_invalid"):
                self.error_code = None
            if self.lease is None:
                self._load_cached_lease()

    def install_delivered_lease(self, envelope: Mapping) -> DeviceLease:
        """Verify issuer/device/policy, preserve identity, then cache and activate.

        Delivery is not a renewal API. A different cached envelope is never
        silently replaced, even under the same licence ID.
        """
        with self._install_lock:
            if self.device_identity is None or self.lease_store is None:
                raise LeaseValidationError("A protected identity and persistent LeaseStore are required.")
            snapshot = deepcopy(dict(envelope))
            verification = LeaseVerifier(self._trusted_public_keys).verify(snapshot, self.device_identity)
            decision = EntitlementPolicy(verification.lease, now=self._now,
                                         clock_validation_required=self.clock_validation_required).validity_decision()
            if not decision.allowed:
                raise LeaseValidationError("Delivered licence is not currently valid: " + decision.reason.value)
            digest = hashlib.sha256(canonical_json(snapshot)).hexdigest()
            cached = self.lease_store.load_lease()
            if ((self._envelope_digest is not None and self._envelope_digest != digest)
                    or (cached is not None and canonical_json(cached) != canonical_json(snapshot))):
                raise LeaseValidationError("A different licence envelope is already installed; explicit recovery is required.")
            # Persistence failures must not grant an in-memory entitlement.
            if cached is None:
                self.lease_store.save_lease(snapshot)
            return self.accept_lease(snapshot, persist=False, reset_clock_validation=False)

    def refresh_from_connector(self, connector, account_id: str) -> DeviceLease:
        """Future HTTPS connector hook; tests use the deterministic mock.

        Transport/authentication are deliberately owned by the connector, not
        by this policy service.  This method cannot make a network request on
        its own and therefore never creates an online startup dependency.
        """
        if self.device_identity is None:
            raise LeaseValidationError("A protected device identity is required before refreshing a licence.")
        envelope = connector.refresh_device_lease(account_id, self.device_identity.device_id)
        return self.accept_lease(envelope)

    def authorize_feature(self, feature_id: str, **kwargs) -> LicenseDecision:
        return self.policy.authorize_feature(feature_id, **kwargs)

    def authorize_calculation(self, calculation_id: str, implementation_state) -> LicenseDecision:
        return self.policy.authorize_calculation(calculation_id, implementation_state)

    def authorize_read(self, feature_id: str = "data:read") -> LicenseDecision:
        return self.policy.authorize_read(feature_id)

    def diagnostics_summary(self) -> dict[str, object]:
        """Safe metadata only; never return a token, signature, or public key."""
        validity = self.policy.validity_decision()
        return {
            "status": self.error_code or ("active" if validity.allowed else validity.entitlement_state.value),
            "test_mode": self.test_mode,
            "licence_id": self.lease.licence_id if self.lease else None,
            "plan_id": self.lease.plan_id if self.lease else None,
            "expires_at": self.lease.expires_at if self.lease else None,
            "device_registered": self.device_identity is not None,
            "clock_validation_required": self.clock_validation_required,
        }

    def _load_cached_lease(self) -> None:
        if self.lease_store is None or self.device_identity is None:
            return
        try:
            last_trusted = self.lease_store.load_last_trusted_time()
            if last_trusted is not None and self._now() + CLOCK_ROLLBACK_TOLERANCE_SECONDS < last_trusted:
                self.clock_validation_required = True
                self.error_code = "clock_validation_required"
            cached = self.lease_store.load_lease()
            if cached is not None:
                self.accept_lease(cached, persist=False, reset_clock_validation=False)
        except (LeaseStoreError, LeaseValidationError, OSError) as error:
            self.error_code = "licence_cache_invalid"
            LOGGER.warning("Cached licence was rejected safely: %s", error)

    def _record_trusted_time(self, issued_at: int) -> None:
        if self.lease_store is None:
            return
        try:
            current = self.lease_store.load_last_trusted_time() or 0
            self.lease_store.save_last_trusted_time(max(current, issued_at, self._now()))
        except (LeaseStoreError, OSError) as error:
            LOGGER.warning("Trusted clock metadata was not persisted: %s", error)


def _redact(value: str) -> str:
    return value[:8] + "…" if value else "unknown"
