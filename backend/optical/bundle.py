"""Coherent optical result bundle contract."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class OpticalResultBundle:
    dielectric_result_id: str
    derived_result_id: str | None = None
    band_coverage: dict[str, Any] | None = None
    convergence_evidence: dict[str, Any] | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
    scientific_status: str = "VALIDATED_UNCONVERGED"

    def to_dict(self):
        return {"dielectric_result_id": self.dielectric_result_id, "derived_result_id": self.derived_result_id,
                "band_coverage": self.band_coverage, "convergence_evidence": self.convergence_evidence,
                "warnings": list(self.warnings), "scientific_status": self.scientific_status}
