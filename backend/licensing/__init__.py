"""Cryptographic entitlement foundation for Quantum Studio product capabilities.

This package intentionally sits above scientific compilation and execution.  It
does not alter inputs, parsers, results, or project files.
"""

from .models import (
    DecisionReason,
    EntitlementState,
    ImplementationState,
    LicenseDecision,
    PlanId,
)
from .policy import EntitlementPolicy
from .service import LicensingService

__all__ = [
    "DecisionReason", "EntitlementPolicy", "EntitlementState",
    "ImplementationState", "LicenseDecision", "LicensingService", "PlanId",
]
