"""Qt-free volumetric field contracts and Gaussian-cube parser utilities."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import numpy as np

BOHR_TO_ANGSTROM = 0.529177210903
MAX_VOXELS = 16_777_216
MAX_SOURCE_BYTES = 512 * 1024 * 1024
FIELD_SPECS = {"charge":{"quantity_kind":"CHARGE_DENSITY","plot_num":0,"source_unit":"e/bohr^3","unit":"e/bohr^3","signed":False,"definition":"electron pseudo-charge density"},"spin":{"quantity_kind":"SPIN_DENSITY","plot_num":6,"source_unit":"e/bohr^3","unit":"e/bohr^3","signed":True,"definition":"collinear spin polarization rho(up)-rho(down)"},"elf":{"quantity_kind":"ELF","plot_num":8,"source_unit":"dimensionless","unit":"dimensionless","signed":False,"definition":"electron localization function"},"potential":{"quantity_kind":"ELECTROSTATIC_POTENTIAL","plot_num":11,"source_unit":"Ry","unit":"Ry","signed":True,"definition":"bare ionic plus Hartree potential (V_bare + V_H)"},"band_decomposed_charge":{"quantity_kind":"BAND_DECOMPOSED_CHARGE_DENSITY","plot_num":7,"source_unit":"e/bohr^3","unit":"e/bohr^3","signed":False,"definition":"selected QE state probability density |psi_nk(r)|²"}}
class VolumetricParseError(RuntimeError): pass
@dataclass(frozen=True)
class FieldSlice:
 plane:str; fractional_position:float; values:np.ndarray; fractional_u:np.ndarray; fractional_v:np.ndarray; cartesian_u:np.ndarray; cartesian_v:np.ndarray; unit:str
def _finite(value,shape,label):
 array=np.asarray(value,float)
 if array.shape!=shape or not np.isfinite(array).all(): raise VolumetricParseError(f"{label} is invalid.")
 return array
def validate_volumetric(values,cell,origin,grid_shape):
 shape=tuple(int(x) for x in grid_shape)
 if len(shape)!=3 or any(x<=0 for x in shape): raise VolumetricParseError("Grid shape must contain three positive dimensions.")
 if int(np.prod(shape))>MAX_VOXELS: raise VolumetricParseError(f"Field exceeds the safe {MAX_VOXELS:,}-voxel in-memory limit.")
 field=np.asarray(values,float)
 if field.shape!=shape: raise VolumetricParseError("Field value count does not match its declared grid shape.")
 if not np.isfinite(field).all(): raise VolumetricParseError("Field contains NaN or infinity.")
 lattice=_finite(cell,(3,3),"Cell")
 if abs(float(np.linalg.det(lattice)))<1e-12: raise VolumetricParseError("Cell volume must be non-zero.")
 _finite(origin,(3,),"Origin"); return field,lattice
def parse_gaussian_cube(path):
 source=Path(path)
 if not source.is_file(): raise VolumetricParseError("Volumetric artifact is missing.")
 if source.stat().st_size>MAX_SOURCE_BYTES: raise VolumetricParseError("Volumetric artifact exceeds the safe source-file limit.")
 lines=source.read_text(encoding="utf-8",errors="replace").splitlines()
 if len(lines)<6: raise VolumetricParseError("Gaussian cube header is truncated.")
 try:
  head=lines[2].split(); nat=abs(int(head[0])); origin=np.asarray([float(x) for x in head[1:4]],float)*BOHR_TO_ANGSTROM; dimensions=[]; steps=[]
  for line in lines[3:6]:
   row=line.split(); dimensions.append(abs(int(row[0]))); steps.append([float(x)*BOHR_TO_ANGSTROM for x in row[1:4]])
 except (ValueError,IndexError) as error: raise VolumetricParseError("Gaussian cube header is malformed.") from error
 shape=tuple(dimensions); cell=np.asarray(steps,float)*np.asarray(shape,float)[:,None]; start=6+nat
 if len(lines)<=start: raise VolumetricParseError("Gaussian cube has no field samples.")
 try: values=np.asarray([float(token.replace("D","E").replace("d","e")) for line in lines[start:] for token in line.split()],float)
 except ValueError as error: raise VolumetricParseError("Gaussian cube contains non-numeric field data.") from error
 if values.size!=int(np.prod(shape)): raise VolumetricParseError(f"Gaussian cube declares {int(np.prod(shape))} samples but contains {values.size}.")
 values,cell=validate_volumetric(values.reshape(shape,order="C"),cell,origin,shape); return values,cell,origin,shape
def field_slice(result,plane="XY",fractional_position=.5):
 values=np.asarray(result.arrays["values"]); cell=np.asarray(result.metadata["cell"],float); plane=str(plane).upper()
 if plane not in {"XY","XZ","YZ"}: raise ValueError("Slice plane must be XY, XZ, or YZ.")
 fraction=float(fractional_position)%1.0; axis={"XY":2,"XZ":1,"YZ":0}[plane]; index=int(np.floor(fraction*values.shape[axis]))%values.shape[axis]
 if plane=="XY": data=values[:,:,index]; u,v=0,1
 elif plane=="XZ": data=values[:,index,:]; u,v=0,2
 else: data=values[index,:,:]; u,v=1,2
 fu=np.arange(data.shape[0])/data.shape[0]; fv=np.arange(data.shape[1])/data.shape[1]
 return FieldSlice(plane,fraction,np.asarray(data),fu,fv,fu[:,None]*cell[u],fv[:,None]*cell[v],result.metadata.get("unit",""))
def field_profile(result,axis="Z"):
 values=np.asarray(result.arrays["values"]); cell=np.asarray(result.metadata["cell"],float); index={"X":0,"Y":1,"Z":2}[str(axis).upper()]; mean=np.mean(values,axis=tuple(x for x in range(3) if x!=index)); fractional=np.arange(values.shape[index])/values.shape[index]; distance=fractional*float(np.linalg.norm(cell[index])); return {"axis":"XYZ"[index],"fractional_coordinate":fractional,"distance_A":distance,"values":mean,"unit":result.metadata.get("unit","")}

