"""TLS-authenticated, cookie-free authorization checks using existing device keys."""
from .licence_delivery import WebsiteLicenceDeliveryConnector, LicenceDeliveryError


class DeviceStatusError(ValueError):
    """Protocol, proof, binding or freshness failure (not a network outage)."""


class DeviceStatusNetworkError(DeviceStatusError):
    """Transport unavailable; no cached authorization can grant access."""


class WebsiteDeviceStatusConnector(WebsiteLicenceDeliveryConnector):
    def _status_post(self, action, body):
        try:
            return self._post(action, body)
        except LicenceDeliveryError as error:
            if error.code == "network_error" or error.http_status in (429, 500, 502, 503, 504):
                raise DeviceStatusNetworkError("Online validation required; status service is unreachable.") from None
            raise DeviceStatusError("Device status service rejected the request or returned invalid data.") from None

    def challenge(self, device, licence_id, digest):
        data = self._status_post("device-status-challenge", {
            "installation_id": device.device_id, "licence_id": licence_id, "envelope_sha256": digest})
        if set(data) != {"challenge"} or not isinstance(data["challenge"], dict):
            raise DeviceStatusError("Invalid device-status challenge.")
        return data["challenge"]

    def status(self, proof):
        return self._status_post("device-status", proof)
