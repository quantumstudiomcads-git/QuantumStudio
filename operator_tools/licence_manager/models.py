"""Stable local contracts for the private licence manager."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ApplicantStatus(str, Enum):
    APPLIED = "APPLIED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    LICENCE_ISSUED = "LICENCE_ISSUED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


TRANSITIONS = {
    ApplicantStatus.APPLIED: {ApplicantStatus.UNDER_REVIEW, ApplicantStatus.REJECTED, ApplicantStatus.REVOKED},
    ApplicantStatus.UNDER_REVIEW: {ApplicantStatus.APPROVED, ApplicantStatus.REJECTED, ApplicantStatus.REVOKED},
    ApplicantStatus.APPROVED: {ApplicantStatus.LICENCE_ISSUED, ApplicantStatus.REVOKED},
    ApplicantStatus.LICENCE_ISSUED: {ApplicantStatus.EXPIRED, ApplicantStatus.REVOKED},
    ApplicantStatus.EXPIRED: {ApplicantStatus.APPROVED, ApplicantStatus.REVOKED},
    ApplicantStatus.REJECTED: set(),
    ApplicantStatus.REVOKED: set(),
}


class Profile(str, Enum):
    PROFESSOR_BETA = "PROFESSOR_BETA"
    INTERNAL_VALIDATION = "INTERNAL_VALIDATION"


@dataclass(frozen=True)
class Applicant:
    application_id: str
    pii: dict[str, str]
    status: ApplicantStatus
