"""One device-proof delivery transaction through the existing licence service."""
from __future__ import annotations

import hashlib
from .canonical import canonical_json
from .connectors.licence_delivery import LicenceDeliveryError


class LicenceDeliveryService:
    def __init__(self, licensing_service, connector, identity_service, *, trust_loader=None):
        self.licensing = licensing_service
        self.connector = connector
        self.identity_service = identity_service
        self.trust_loader = trust_loader

    def retrieve_and_install(self, activation_request_id=None, *, cancelled=None):
        def check_cancelled():
            if cancelled is not None and cancelled.is_set():
                raise LicenceDeliveryError("Licence check cancelled.", code="cancelled")
        check_cancelled()
        device = self.licensing.device_identity
        if device is None:
            raise LicenceDeliveryError("The protected device identity is unavailable.")
        challenge = self.connector.get_device_challenge(device.device_id, activation_request_id)
        check_cancelled()
        if activation_request_id is not None and challenge.get("activation_request_id") != activation_request_id:
            raise LicenceDeliveryError("The delivery challenge does not match the selected activation.")
        proof = self.identity_service.sign_licence_challenge(challenge, device)
        data = self.connector.retrieve_device_licence(proof)
        check_cancelled()
        if data == {"state": "pending"}:
            return "pending"
        if (not isinstance(data, dict) or set(data) != {"state", "envelope", "envelope_sha256"}
                or data.get("state") != "available" or not isinstance(data.get("envelope"), dict)):
            raise LicenceDeliveryError("The licence delivery result is invalid.")
        envelope = data["envelope"]
        if hashlib.sha256(canonical_json(envelope)).hexdigest() != data["envelope_sha256"]:
            raise LicenceDeliveryError("The published licence digest does not match its envelope.")
        if self.trust_loader is not None:
            self.trust_loader()  # Explicit LOCAL file configuration only, never response keys.
        check_cancelled()
        self.licensing.install_delivered_lease(envelope)
        return "installed"
