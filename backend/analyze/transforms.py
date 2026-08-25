"""Qt-free transformations over ScientificResult only."""
from __future__ import annotations

def result_kind(result):
    return {"BandStructureResult":"Band Structure", "DOSResult":"Density of States", "PDOSResult":"Projected DOS", "PhononDOSResult":"Phonon DOS", "GroundStateResult":"Ground State", "RelaxationResult":"Relaxation", "WannierizationResult":"Wannier", "ElectronPhononResult":"EPW"}.get(result.result_type, result.result_type)

def _values(result, key):
    value = result.arrays.get(key, ())
    return list(value.tolist() if hasattr(value, "tolist") else value)

def tabular_data(result):
    t=result.result_type
    if t=="BandStructureResult":
        x=_values(result,"path_coordinate") or _values(result,"kpoint") or _values(result,"energy")
        energies=result.arrays.get("energies")
        if energies is not None:
            rows=energies.tolist() if hasattr(energies,"tolist") else energies
            return (["path_coordinate"]+[f"band_{i+1}" for i in range(len(rows[0]) if rows else 0)], [[x[i], *rows[i]] for i in range(min(len(x),len(rows)))])
    if t in {"DOSResult","PDOSResult"}:
        x=_values(result,"energy")
        cols=["energy"]
        values=[]
        for key in ("dos","total_dos"):
            if key in result.arrays: cols.append(key); values.append(_values(result,key))
        components=result.metadata.get("components",[])
        for index, component in enumerate(components):
            cols.append(str(component.get("label") or component.get("orbital") or f"component_{index+1}"))
            values.append(list(result.metadata.get("component_values", [])[index]))
        rows=[[x[i]]+[column[i] if i<len(column) else "" for column in values] for i in range(len(x))]
        return cols, rows
    if t=="PhononDOSResult":
        x=_values(result,"frequency"); y=_values(result,"dos")
        return ["frequency","dos"], [[x[i],y[i]] for i in range(min(len(x),len(y)))]
    return [], []
