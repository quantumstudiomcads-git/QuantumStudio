from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
class TaskState(str,Enum): PENDING="PENDING"; READY="READY"; RUNNING="RUNNING"; COMPLETED="COMPLETED"; FAILED="FAILED"; CANCELLED="CANCELLED"; BLOCKED="BLOCKED"; INTERRUPTED="INTERRUPTED"
class WorkflowState(str,Enum): PENDING="PENDING"; RUNNING="RUNNING"; COMPLETED="COMPLETED"; FAILED="FAILED"; CANCELLED="CANCELLED"
def now(): return datetime.now(timezone.utc).isoformat()
@dataclass
class TaskExecutionRecord:
 task_id:str; state:TaskState=TaskState.PENDING; started_at:str|None=None; finished_at:str|None=None; return_code:int|None=None; stdout_path:str|None=None; stderr_path:str|None=None; error_message:str=""; error_type:str=""; timeout_seconds:float|None=None; attempt_count:int=0; resolved_executable:str|None=None; process_id:int|None=None; requested_cores:int|None=None; actual_mpi_ranks:int|None=None; omp_threads_per_rank:int|None=None; mpi_launcher:str|None=None; command_argv:list[str]=field(default_factory=list); engine_version:str|None=None; completion_origin:str=""; reused_from_execution_id:str=""; reused_from_task_id:str=""
@dataclass
class WorkflowExecutionRecord:
 request_id:str; workflow_root:str; tasks:dict[str,TaskExecutionRecord]; events:list[dict]=field(default_factory=list); execution_id:str=""; request_fingerprint:str=""; structure_fingerprint:str=""; workflow_fingerprint:str=""; manifest_fingerprint:str=""; input_fingerprints:dict[str,str]=field(default_factory=dict); created_at:str|None=None; started_at:str|None=None; finished_at:str|None=None; parent_execution_id:str=""; branch_reason:str=""; reuse_plan_identity:str=""; reuse_bindings:list[dict]=field(default_factory=list); invalidated_tasks:tuple[str,...]=(); provider_provenance:dict=field(default_factory=dict)
 @property
 def state(self):
  states={x.state for x in self.tasks.values()}
  if TaskState.RUNNING in states or TaskState.READY in states:return WorkflowState.RUNNING
  if TaskState.FAILED in states or TaskState.INTERRUPTED in states:return WorkflowState.FAILED
  if TaskState.CANCELLED in states:return WorkflowState.CANCELLED
  return WorkflowState.COMPLETED if states=={TaskState.COMPLETED} else WorkflowState.PENDING
