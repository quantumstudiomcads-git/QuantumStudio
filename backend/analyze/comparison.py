"""Qt-free, engine-neutral ScientificResult comparison models."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class AnalysisSeries:
    series_id: str
    label: str
    result_type: str
    request_id: str
    execution_id: str
    scientific_result: Any
    functional: str = ""
    status: str = ""
    units: dict[str, str] = field(default_factory=dict)
    visible: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_result(cls, result, label=None):
        p=result.provenance
        functional=str(result.metadata.get("functional", ""))
        if not functional:
            functional=str(result.metadata.get("xc_functional", ""))
        return cls(result.result_id, label or functional or result.result_type, result.result_type,
                    p.request_id, p.execution_id, result, functional, result.status.value,
                    dict(result.metadata.get("units", {})), True, dict(result.metadata))

@dataclass
class ComparisonModel:
    title: str
    result_family: str
    series: list[AnalysisSeries] = field(default_factory=list)
    compatibility: str = ""
    common_units: dict[str, str] = field(default_factory=dict)
    alignment_policy: str = "independent_axes"
    warnings: list[str] = field(default_factory=list)

    def visible_series(self):
        return [item for item in self.series if item.visible]

    def check(self):
        if not self.series: self.compatibility="EMPTY"; return self
        types={item.result_type for item in self.series}
        families={"BandStructureResult":"bands","DOSResult":"dos","PDOSResult":"pdos","PhononDOSResult":"phonon_dos"}
        family={families.get(item,"scalar") for item in types}
        if len(family)>1:
            self.compatibility="INCOMPATIBLE"; self.warnings=["Results belong to different scientific families."]; return self
        self.result_family=next(iter(family))
        self.compatibility="POTENTIALLY_COMPATIBLE"
        paths=[]
        for item in self.series:
            path=item.scientific_result.metadata.get("band_path") or item.scientific_result.metadata.get("path")
            if path: paths.append(tuple(str(point.get("label", "")) for point in path))
        if paths and any(path != paths[0] for path in paths[1:]):
            self.compatibility="INCOMPATIBLE"; self.warnings=["Band path topologies differ; direct overlay is not valid."]
        statuses={item.status for item in self.series if item.status}
        if statuses-{ "VALID" }: self.warnings.append("One or more series is not VALID: " + ", ".join(sorted(statuses-{ "VALID" })))
        return self

def provenance_differences(model):
    rows=[]
    for key in ("functional", "soc", "structure_fingerprint", "workflow_fingerprint"):
        values=[str(item.metadata.get(key, item.scientific_result.provenance.__dict__.get(key, ""))) for item in model.series]
        if len(set(values))>1: rows.append((key, values))
    return rows

def compatible_results(left, right):
    return ComparisonModel("Comparison", "", [AnalysisSeries.from_result(left), AnalysisSeries.from_result(right)]).check()


def difference_eligible(model):
    visible=model.visible_series()
    if len(visible)!=2 or model.compatibility == "INCOMPATIBLE": return False, "Difference requires exactly two compatible visible series."
    a,b=visible
    if a.result_type=="BandStructureResult":
        try:
            import numpy as np
            ya=np.asarray(a.scientific_result.arrays.get("energies",a.scientific_result.arrays.get("energy"))); yb=np.asarray(b.scientific_result.arrays.get("energies",b.scientific_result.arrays.get("energy")))
            if ya.shape!=yb.shape:return False,"Band difference requires identical sampling and band counts."
        except Exception:return False,"Band difference data is unavailable."
    return True, ""
