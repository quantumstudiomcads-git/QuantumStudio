"""Engine-neutral C8B scientific result records."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import hashlib, json

class ResultStatus(str, Enum): VALID="VALID"; PARTIAL="PARTIAL"; NOT_CONVERGED="NOT_CONVERGED"; UNVERIFIED="UNVERIFIED"; PARSE_FAILED="PARSE_FAILED"; STALE="STALE"

@dataclass(frozen=True)
class ResultProvenance:
    request_id:str; execution_id:str; source_task_id:str; engine_id:str; tool_id:str; source_paths:tuple[str,...]; source_hashes:dict[str,str]; parser_id:str; parser_version:str="1"
    structure_fingerprint:str=""; workflow_fingerprint:str=""; public_intent:str=""

@dataclass
class ScientificResult:
    result_type:str; status:ResultStatus; provenance:ResultProvenance; scalars:dict[str,dict]=field(default_factory=dict); arrays:dict[str,object]=field(default_factory=dict); metadata:dict=field(default_factory=dict); warnings:list[str]=field(default_factory=list); result_id:str=""
    def __post_init__(self):
        if not self.result_id:
            source=json.dumps({"type":self.result_type,"task":self.provenance.source_task_id,"execution":self.provenance.execution_id,"parser":self.provenance.parser_id,"hashes":self.provenance.source_hashes},sort_keys=True).encode()
            self.result_id=hashlib.sha256(source).hexdigest()[:24]
    def summary(self):
        if self.result_type=="GroundStateResult" and "total_energy" in self.scalars: return f"{self.status.value}, E = {self.scalars['total_energy']['value']:.8g} eV"
        if "energy" in self.arrays: return f"{self.status.value}, {len(self.arrays['energy'])} samples"
        if self.result_type=="VolumetricResult" and "values" in self.arrays: return f"{self.status.value}, grid {tuple(self.arrays['values'].shape)}"
        if self.result_type=="VolumetricResult" and "values" in self.arrays: return f"{self.status.value}, grid {tuple(self.arrays['values'].shape)}"
        if "frequency" in self.arrays: return f"{self.status.value}, {len(self.arrays['frequency'])} samples"
        return self.status.value

@dataclass
class CalculationResultBundle:
    request_id:str; execution_id:str; results:list[ScientificResult]
