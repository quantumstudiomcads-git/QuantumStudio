"""Licensing connector contracts, desktop activation transport, and test connector."""

from .base import AuthConnector, BillingConnector, DesktopActivationConnector, LicensingConnector, PlanCatalogConnector, StudentVerificationConnector
from .mock import InMemoryLicensingConnector
from .desktop_auth import DesktopAuthError, WebsiteDesktopActivationConnector

__all__ = ["DesktopActivationConnector", "DesktopAuthError", "WebsiteDesktopActivationConnector", "AuthConnector", "BillingConnector", "InMemoryLicensingConnector", "LicensingConnector", "PlanCatalogConnector", "StudentVerificationConnector"]
