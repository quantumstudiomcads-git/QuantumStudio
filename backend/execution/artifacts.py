"""Persistent, logical task-artifact contracts for generated workflows."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Iterable

class ArtifactError(RuntimeError): pass
class RequiredArtifactMissing(ArtifactError): pass

class MaterializationPolicy(str, Enum):
    COPY="COPY"; HARDLINK="HARDLINK"; REFERENCE="REFERENCE"; COPY_ON_WRITE="COPY_ON_WRITE"

@dataclass(frozen=True)
class TaskArtifactDeclaration:
    logical_name:str; relative_path:str; artifact_type:str="FILE"; required:bool=True; materialization_policy:MaterializationPolicy=MaterializationPolicy.COPY
    def to_dict(self):
        value=asdict(self); value["materialization_policy"]=self.materialization_policy.value; return value
    @classmethod
    def from_dict(cls,value):
        return cls(str(value["logical_name"]),str(value["relative_path"]),str(value.get("artifact_type","FILE")),bool(value.get("required",True)),MaterializationPolicy(value.get("materialization_policy","COPY")))

@dataclass(frozen=True)
class TaskArtifactRequirement:
    logical_name:str; relative_path:str; artifact_type:str="FILE"; materialization_policy:MaterializationPolicy=MaterializationPolicy.COPY
    def to_dict(self):
        value=asdict(self); value["materialization_policy"]=self.materialization_policy.value; return value
    @classmethod
    def from_dict(cls,value):
        return cls(str(value["logical_name"]),str(value["relative_path"]),str(value.get("artifact_type","FILE")),MaterializationPolicy(value.get("materialization_policy","COPY")))

@dataclass(frozen=True)
class ArtifactRecord:
    logical_name:str; artifact_type:str; producer_task_id:str; execution_id:str; source_path:str; size:int; sha256:str; relative_path:str; origin:str="PRODUCED"; consumer_execution_id:str=""; source_execution_id:str=""; source_task_id:str=""; source_logical_name:str=""; verified_sha256:str=""; materialization_policy:str=""; compatibility_fingerprint:str=""; verified_at:str=""
    def to_dict(self): return asdict(self)
    @classmethod
    def from_dict(cls,value): return cls(**{key:value[key] for key in ("logical_name","artifact_type","producer_task_id","execution_id","source_path","size","sha256","relative_path")}, **{key:value.get(key,getattr(cls,key)) for key in ("origin","consumer_execution_id","source_execution_id","source_task_id","source_logical_name","verified_sha256","materialization_policy","compatibility_fingerprint","verified_at")})

def content_sha256(path:Path)->str:
    digest=hashlib.sha256()
    if path.is_dir():
        rows=[(item.relative_to(path).as_posix(),content_sha256(item)) for item in sorted(path.rglob("*")) if item.is_file()]
        digest.update(json.dumps(rows,separators=(",",":"),ensure_ascii=True).encode()); return digest.hexdigest()
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(65536),b""): digest.update(block)
    return digest.hexdigest()

class ArtifactRegistry:
    """Atomic execution-local artifact metadata store."""
    def __init__(self,workflow_root,execution_id):
        self.root=Path(workflow_root).resolve(); self.execution_id=str(execution_id); self.path=self.root/"executions"/self.execution_id/"artifacts.json"
    def load(self):
        try: data=json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError: return {}
        except (OSError,json.JSONDecodeError) as error: raise ArtifactError("Artifact registry is corrupt.") from error
        return {key:ArtifactRecord.from_dict(value) for key,value in data.get("artifacts",{}).items()}
    def save(self,records):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        payload={"schema_version":"0.1","execution_id":self.execution_id,"artifacts":{key:value.to_dict() for key,value in sorted(records.items())}}
        temporary=self.path.with_suffix(".tmp"); temporary.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8"); os.replace(temporary,self.path)
    def register_external(self, *, logical_name, artifact_type, producer_task_id, source_path, relative_path, compatibility_fingerprint=""):
        """Reconcile a pre-existing declared artifact without re-running its producer."""
        source = Path(source_path).resolve()
        if not source.exists():
            raise RequiredArtifactMissing(f"Reusable artifact {logical_name!r} is missing.")
        size = sum(item.stat().st_size for item in source.rglob("*") if item.is_file()) if source.is_dir() else source.stat().st_size
        records = self.load()
        records[logical_name] = ArtifactRecord(
            logical_name, artifact_type, producer_task_id, self.execution_id, str(source), size,
            content_sha256(source), relative_path, compatibility_fingerprint=compatibility_fingerprint,
        )
        self.save(records)
        return records[logical_name]

    def register(self,task,declarations:Iterable[TaskArtifactDeclaration]):
        records=self.load(); directory=(self.root/task.working_directory).resolve()
        for declaration in declarations:
            source=(directory/declaration.relative_path).resolve()
            if self.root not in source.parents and source!=self.root: raise RequiredArtifactMissing(f"Declared artifact {declaration.logical_name!r} escapes workflow root.")
            if not source.exists() or (source.is_file() and source.stat().st_size==0):
                if declaration.required: raise RequiredArtifactMissing(f"Required workflow artifact {declaration.logical_name!r} was not produced by {task.task_id}.")
                continue
            size=sum(item.stat().st_size for item in source.rglob("*") if item.is_file()) if source.is_dir() else source.stat().st_size
            records[declaration.logical_name]=ArtifactRecord(declaration.logical_name,declaration.artifact_type,task.task_id,self.execution_id,str(source),size,content_sha256(source),declaration.relative_path)
        self.save(records); return records

class ArtifactResolver:
    def __init__(self,workflow,registry): self.workflow,self.registry=workflow,registry
    @staticmethod
    def declarations(task): return tuple(TaskArtifactDeclaration.from_dict(value) for value in task.artifact_declarations)
    @staticmethod
    def requirements(task): return tuple(TaskArtifactRequirement.from_dict(value) for value in task.artifact_requirements)
    def _upstream(self,task_id):
        task_map=self.workflow.task_map(); result=set(); pending=list(task_map[task_id].dependencies)
        while pending:
            item=pending.pop()
            if item not in result: result.add(item); pending.extend(task_map[item].dependencies)
        return result
    def validate(self):
        for task in self.workflow.tasks:
            upstream=self._upstream(task.task_id)
            for requirement in self.requirements(task):
                producers=[candidate for candidate in self.workflow.tasks if candidate.task_id in upstream and any(declaration.logical_name==requirement.logical_name and declaration.artifact_type==requirement.artifact_type for declaration in self.declarations(candidate))]
                if len(producers)!=1: raise ArtifactError(f"{task.task_id}: artifact {requirement.logical_name!r} requires exactly one upstream producer, found {len(producers)}.")
    def materialize(self,task):
        records=self.registry.load(); directory=(self.workflow.root/task.working_directory).resolve()
        for requirement in self.requirements(task):
            record=records.get(requirement.logical_name)
            if record is None: raise RequiredArtifactMissing(f"Required workflow artifact {requirement.logical_name!r} could not be prepared for {task.semantic_task_type}.")
            source=Path(record.source_path).resolve(); destination=(directory/requirement.relative_path).resolve()
            if not source.exists() or content_sha256(source)!=record.sha256: raise RequiredArtifactMissing(f"Required workflow artifact {requirement.logical_name!r} is missing or changed.")
            if self.workflow.root not in destination.parents: raise ArtifactError("Artifact materialization path escapes workflow root.")
            if requirement.materialization_policy is MaterializationPolicy.REFERENCE: continue
            destination.parent.mkdir(parents=True,exist_ok=True)
            if destination.exists():
                if content_sha256(destination)==record.sha256: continue
                if destination.is_dir(): shutil.rmtree(destination)
                else: destination.unlink()
            # COPY_ON_WRITE is deliberately an ordinary verified copy here.  A
            # later reflink optimization must preserve the same isolation rule.
            if source.is_dir(): shutil.copytree(source,destination)
            elif requirement.materialization_policy is MaterializationPolicy.HARDLINK:
                # A generated task is not proven read-only. Sharing an inode
                # could let a mutable consumer corrupt the retained parent.
                shutil.copy2(source,destination)
            else: shutil.copy2(source,destination)
            if content_sha256(destination)!=record.sha256: raise ArtifactError(f"Materialized artifact {requirement.logical_name!r} failed hash verification.")
