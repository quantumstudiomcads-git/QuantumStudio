"""Provider-neutral contracts; no network transport is implemented in B4."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping

from ..models import DeviceRegistrationRequest, DeviceRegistrationResponse, SessionClaim


class ConnectorError(RuntimeError):
    code = "server_rejected"


class LicensingConnector(ABC):
    @abstractmethod
    def register_device(self, request: DeviceRegistrationRequest) -> DeviceRegistrationResponse: ...
    @abstractmethod
    def refresh_device_lease(self, account_id: str, device_id: str) -> Mapping[str, Any]: ...
    @abstractmethod
    def get_entitlement_status(self, account_id: str, device_id: str) -> Mapping[str, Any]: ...
    @abstractmethod
    def open_session(self, account_id: str, device_id: str, *, seat_id: str | None = None) -> SessionClaim: ...
    @abstractmethod
    def refresh_session(self, session_id: str) -> SessionClaim: ...
    @abstractmethod
    def close_session(self, session_id: str) -> None: ...
    @abstractmethod
    def deactivate_device(self, account_id: str, device_id: str) -> None: ...


class AuthConnector(ABC):
    """Future system-browser OIDC Authorization Code + PKCE boundary."""
    @abstractmethod
    def begin_pkce_authorization(self) -> Mapping[str, str]: ...
    @abstractmethod
    def complete_pkce_authorization(self, authorization_result: Mapping[str, str]) -> Mapping[str, str]: ...


class PlanCatalogConnector(ABC):
    @abstractmethod
    def get_plans(self) -> tuple[Mapping[str, Any], ...]: ...


class BillingConnector(ABC):
    @abstractmethod
    def billing_event(self, event: Mapping[str, Any]) -> None: ...


class StudentVerificationConnector(ABC):
    @abstractmethod
    def verification_status(self, account_id: str) -> str: ...


class DesktopActivationConnector(ABC):
    """Short-lived browser confirmation; independent of lease/session connectors."""
    @abstractmethod
    def start_activation(self, facts: Mapping[str, str]) -> Mapping[str, Any]: ...
    @abstractmethod
    def poll_activation(self, challenge_id: str, device_code: str) -> Mapping[str, Any]: ...
    @abstractmethod
    def cancel_activation(self, challenge_id: str, device_code: str) -> None: ...
