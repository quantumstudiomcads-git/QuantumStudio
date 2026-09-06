from __future__ import annotations
from dataclasses import dataclass
from math import isfinite
from typing import Any
import numpy as np

class DenseElectronicStateError(ValueError):
    pass

@dataclass(frozen=True)
class DenseElectronicState:
    cell_A: np.ndarray
    reciprocal_cell: np.ndarray
    kpoints_fractional: np.ndarray
    weights: np.ndarray
    eigenvalues_eV: np.ndarray
    fermi_energy_eV: float
    electron_count: float
    spin_mode: str
    spin_degeneracy: float
    volume_A3: float
    number_of_bands: int
    number_of_kpoints: int
    pbc: tuple[bool, bool, bool]
    provenance: dict[str, Any]

    def __post_init__(self):
        arrays=[np.asarray(self.cell_A,float),np.asarray(self.reciprocal_cell,float),np.asarray(self.kpoints_fractional,float),np.asarray(self.weights,float),np.asarray(self.eigenvalues_eV,float)]
        cell, reciprocal, kpoints, weights, eigenvalues=arrays
        if cell.shape!=(3,3) or reciprocal.shape!=(3,3): raise DenseElectronicStateError("Dense state cells must be 3x3.")
        if kpoints.ndim!=2 or kpoints.shape[1]!=3 or weights.shape!=(kpoints.shape[0],): raise DenseElectronicStateError("Dense state k-points and weights have incompatible shapes.")
        if eigenvalues.ndim not in (2,3) or eigenvalues.shape[-2:]!=(kpoints.shape[0],self.number_of_bands): raise DenseElectronicStateError("Dense state eigenvalues have incompatible dimensions.")
        if any(not np.all(np.isfinite(array)) for array in arrays): raise DenseElectronicStateError("Dense state arrays must contain only finite values.")
        if not isfinite(float(self.fermi_energy_eV)) or not isfinite(float(self.electron_count)) or not isfinite(float(self.volume_A3)) or self.volume_A3<=0: raise DenseElectronicStateError("Dense state scalar values must be finite and volume positive.")
        if self.number_of_bands<1 or self.number_of_kpoints<1 or len(tuple(self.pbc))!=3: raise DenseElectronicStateError("Dense state dimensions are invalid.")

    @classmethod
    def from_boltztrap_data(cls,data,*,qe_version=""):
        from BoltzTraP2 import units
        eigenvalues=np.asarray(data.ebands,float)
        if eigenvalues.ndim==3 and eigenvalues.shape[0]==1: eigenvalues=eigenvalues[0]
        kpoints=np.asarray(data.kpoints,float)
        if kpoints.ndim==2 and kpoints.shape[0]==3: kpoints=kpoints.T
        cell=np.asarray(data.atoms.get_cell(),float); nk=int(kpoints.shape[0])
        if eigenvalues.ndim==2 and eigenvalues.shape[1]==nk: eigenvalues=eigenvalues.T
        elif eigenvalues.ndim==3 and eigenvalues.shape[-1]==nk: eigenvalues=np.swapaxes(eigenvalues,-1,-2)
        return cls(cell/float(units.Angstrom),2*np.pi*np.linalg.inv(cell).T,kpoints,np.ones(nk)/nk,eigenvalues/float(units.eV),float(data.fermi)/float(units.eV),float(data.nelect),"SCALAR_NONSPIN" if float(getattr(data,"dosweight",2.0))==2.0 else "COLLINEAR_SPIN",float(getattr(data,"dosweight",2.0)),abs(float(np.linalg.det(cell)))/float(units.Angstrom)**3,int(eigenvalues.shape[-1]),int(eigenvalues.shape[-2]),(True,True,True),{"backend":"BoltzTraP2","qe_version":qe_version})
