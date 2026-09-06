"""Atomic result metadata/array storage beneath C7 execution history."""
from __future__ import annotations
import hashlib, json, os
import tempfile
from pathlib import Path
import numpy as np
from .models import ResultProvenance, ResultStatus, ScientificResult

class ResultStoreError(RuntimeError): pass
class ResultStore:
 def __init__(self, workflow_root, execution_id): self.root=Path(workflow_root).resolve(); self.base=self.root/"executions"/execution_id/"results"; self.data=self.base/"data"
 def _safe(self,path):
  value=path.resolve()
  if self.root not in value.parents: raise ResultStoreError("Result path escapes workflow root.")
  return value
 def save(self,result):
  self.data.mkdir(parents=True,exist_ok=True); arrays={key:np.asarray(value) for key,value in result.arrays.items()}; array_target=self._safe(self.data/(result.result_id+".npz")); fd, temporary=tempfile.mkstemp(prefix="."+result.result_id+".", suffix=".npz", dir=str(self.data)); os.close(fd)
  try:
   np.savez_compressed(temporary,**arrays); os.replace(temporary,array_target)
  except Exception:
   try: os.unlink(temporary)
   except FileNotFoundError: pass
   raise
  payload={"result_id":result.result_id,"result_type":result.result_type,"status":result.status.value,"provenance":result.provenance.__dict__,"scalars":result.scalars,"metadata":result.metadata,"warnings":result.warnings,"array_file":"data/"+result.result_id+".npz"}
  target=self._safe(self.base/(result.result_id+".json")); temporary=target.with_suffix(".tmp"); target.parent.mkdir(parents=True,exist_ok=True)
  with temporary.open("w",encoding="utf-8") as stream: json.dump(payload,stream,sort_keys=True); stream.flush(); os.fsync(stream.fileno())
  os.replace(temporary,target); self._write_index(); return result.result_id
 def _write_index(self):
  entries=sorted(path.stem for path in self.base.glob("*.json") if path.name!="index.json"); target=self.base/"index.json"; tmp=target.with_suffix(".tmp"); tmp.write_text(json.dumps(entries)+"\n"); os.replace(tmp,target)
 def list(self):
  try: return tuple(json.loads((self.base/"index.json").read_text()))
  except FileNotFoundError: return ()
  except (OSError,json.JSONDecodeError): raise ResultStoreError("Result index is corrupt.")
 def load(self,result_id):
  try: data=json.loads(self._safe(self.base/(result_id+".json")).read_text())
  except (OSError,json.JSONDecodeError): raise ResultStoreError("Result metadata is corrupt.")
  source=data["provenance"]; provenance=ResultProvenance(**source); array_path=self._safe(self.base/data["array_file"])
  if not array_path.is_file(): raise ResultStoreError("Result numeric payload is missing.")
  with np.load(array_path) as values: arrays={key:values[key] for key in values.files}
  return ScientificResult(data["result_type"],ResultStatus(data["status"]),provenance,data.get("scalars",{}),arrays,data.get("metadata",{}),data.get("warnings",[]),data["result_id"])
 def validate_sources(self,result):
  for path,digest in result.provenance.source_hashes.items():
   source=Path(path)
   if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=digest: return ResultStatus.STALE
  return result.status
