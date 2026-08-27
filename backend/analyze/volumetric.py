"""Qt-free volumetric slicing, profiles, and export helpers."""
from __future__ import annotations
from pathlib import Path
import json
import numpy as np
from backend.results.volumetric import field_slice,field_profile
def export_volumetric_npz(result,path):
 target=Path(path); target.parent.mkdir(parents=True,exist_ok=True); np.savez_compressed(target,values=np.asarray(result.arrays["values"]),metadata=json.dumps(result.metadata,sort_keys=True)); return target
def export_slice_csv(result,path,plane="XY",fractional_position=.5):
 field=field_slice(result,plane,fractional_position); target=Path(path); target.parent.mkdir(parents=True,exist_ok=True)
 with target.open("w",encoding="utf-8") as stream:
  stream.write("u_fractional,v_fractional,value\n")
  for i,u in enumerate(field.fractional_u):
   for j,v in enumerate(field.fractional_v): stream.write(f"{u:.12g},{v:.12g},{field.values[i,j]:.12g}\n")
 return target
def export_profile_csv(result,path,axis="Z"):
 profile=field_profile(result,axis); target=Path(path); target.parent.mkdir(parents=True,exist_ok=True)
 with target.open("w",encoding="utf-8") as stream:
  stream.write("fractional_coordinate,distance_A,value\n")
  for f,d,v in zip(profile["fractional_coordinate"],profile["distance_A"],profile["values"]): stream.write(f"{f:.12g},{d:.12g},{v:.12g}\n")
 return target

