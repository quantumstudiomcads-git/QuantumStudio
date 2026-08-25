"""Machine-local tool configuration; intentionally not persisted in CalculationRequest."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import os, shutil
from .errors import ExecutableNotFoundError
@dataclass(frozen=True)
class LocalToolConfiguration:
 tool_paths:dict[str,str]=field(default_factory=dict); engine_directories:dict[str,str]=field(default_factory=dict); environment:dict[str,str]=field(default_factory=dict)
 def resolve(self,tool_id,program,engine_id=None):
  candidates=[]
  if tool_id in self.tool_paths:candidates.append(Path(self.tool_paths[tool_id]))
  if engine_id and engine_id in self.engine_directories:candidates.append(Path(self.engine_directories[engine_id])/program)
  found=shutil.which(program,path=self.environment.get("PATH") or os.environ.get("PATH"))
  if found:candidates.append(Path(found))
  for candidate in candidates:
   if candidate.is_file() and os.access(candidate,os.X_OK): return candidate.resolve()
  raise ExecutableNotFoundError(f"Local executable for {tool_id!r} ({program!r}) is not configured or executable.")
