"""Qt-free Calculate-facing access to C8 execution-sidecar Results."""
from __future__ import annotations
from backend.execution import ExecutionStore
from backend.results import ResultStore, ResultStoreError

class ResultService:
 def executions(self, workflow_root): return ExecutionStore(workflow_root).list()
 def summaries(self, workflow_root, execution_id):
  store=ResultStore(workflow_root,execution_id); rows=[]
  for result_id in store.list():
   try:
    result=store.load(result_id); status=store.validate_sources(result)
    rows.append({"result_id":result_id,"type":result.result_type,"status":status.value,"summary":result.summary(),"provenance":result.provenance})
   except ResultStoreError as error: rows.append({"result_id":result_id,"type":"Unreadable Result","status":"PARSE_FAILED","summary":str(error),"provenance":None})
  return tuple(rows)
