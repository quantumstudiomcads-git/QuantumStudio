"""Qt-free transformations over ScientificResult only."""
from __future__ import annotations

def result_kind(result):
    return {"BandStructureResult":"Band Structure", "DOSResult":"Density of States", "PDOSResult":"Projected DOS", "PhononDOSResult":"Phonon DOS", "GroundStateResult":"Ground State", "RelaxationResult":"Relaxation", "WannierizationResult":"Wannier", "ElectronPhononResult":"EPW", "VolumetricResult":"Volumetric Field", "WorkFunctionResult":"Work Function"}.get(result.result_type, result.result_type)

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
        for key in ("dos","total_dos","integrated_dos","dos_up","dos_down"):
            if key in result.arrays: cols.append(key); values.append(_values(result,key))
        components=result.metadata.get("components",[])
        for index, component in enumerate(components):
            cols.append(str(component.get("label") or component.get("orbital") or f"component_{index+1}"))
            values.append(list(result.metadata.get("component_values", [])[index]))
        rows=[[x[i]]+[column[i] if i<len(column) else "" for column in values] for i in range(len(x))]
        return cols, rows
    if t=="WorkFunctionResult":
        x=_values(result,"distance_A"); raw=_values(result,"potential_raw_Ry"); ev=_values(result,"potential_eV"); macro=_values(result,"macroscopic_eV"); return ["distance_A","potential_raw_Ry","potential_eV","macroscopic_eV"], [[x[i],raw[i] if i<len(raw) else "",ev[i] if i<len(ev) else "",macro[i] if i<len(macro) else ""] for i in range(len(x))]
    if t=="RelaxationResult":
        atoms=result.metadata.get("final_structure",{}).get("atoms",[])
        return ["element","x_A","y_A","z_A"], [[atom.get("element",""),atom.get("x",""),atom.get("y",""),atom.get("z","")] for atom in atoms]
    if t=="WannierizationResult":
        centres=_values(result,"centres_A"); spreads=_values(result,"individual_spreads_A2")
        if centres: return ["wannier_index","centre_x_A","centre_y_A","centre_z_A","spread_A2"], [[index+1,*centre,spreads[index] if index<len(spreads) else ""] for index,centre in enumerate(centres)]
        return ["quantity","value"], [["num_wann",result.metadata.get("num_wann","")],["final_spread_A2",result.scalars.get("final_spread",{}).get("value","")]]
    if t=="PhononDOSResult":
        x=_values(result,"frequency"); y=_values(result,"dos")
        return ["frequency","dos"], [[x[i],y[i]] for i in range(min(len(x),len(y)))]
    return [], []


def pdos_channels(result, *, species=None, atom=None, orbital=None, component=None, spin=None, aggregation="None"):
    components=result.metadata.get("components", ())
    values=result.metadata.get("component_values", ())
    selected=[]
    for index, channel in enumerate(components):
        if species not in (None,"All") and str(channel.get("species", channel.get("element", ""))) != str(species): continue
        if atom not in (None,"All") and str(channel.get("atom", channel.get("atom_index", ""))) != str(atom): continue
        if orbital not in (None,"All") and str(channel.get("orbital", channel.get("label", ""))) != str(orbital): continue
        if component not in (None,"All") and str(channel.get("component", channel.get("m", ""))) != str(component): continue
        if spin not in (None,"All") and str(channel.get("spin", "")) != str(spin): continue
        if index < len(values): selected.append((channel, values[index]))
    if aggregation in (None,"None") or not selected: return selected
    key={"By species":"species","By atom":"atom","By orbital":"orbital","By spin":"spin"}.get(aggregation)
    if key is None: return selected
    groups={}
    for channel, data in selected: groups.setdefault(str(channel.get(key, channel.get("element", channel.get("label", "channel")))), []).append(data)
    import numpy as np
    return [({"label": label, "aggregated": True}, np.sum(np.asarray(series), axis=0).tolist()) for label, series in sorted(groups.items())]


def energy_reference(result, reference):
    """Return a copied energy axis aligned without mutating the Result."""
    import numpy as np
    energy=np.asarray(result.arrays.get("energy", result.arrays.get("path_coordinate", [])), dtype=float).copy()
    if reference == "Absolute": return energy
    key="fermi_energy" if reference == "Fermi = 0" else "vbm"
    value=result.metadata.get(key, result.metadata.get(key+"_eV") if key=="fermi_energy" else None)
    if value is None: value=result.scalars.get(key, {}).get("value") if isinstance(result.scalars.get(key),dict) else result.scalars.get(key)
    if value is None: raise ValueError(f"{reference} is unavailable for this Result.")
    return energy-float(value)


def exact_difference(left, right, *, key=None):
    """Subtract right-left only for equal shapes/axes; no interpolation."""
    import numpy as np
    if key is None: key = "dos" if "dos" in left.arrays and "dos" in right.arrays else "energy"
    a=np.asarray(left.arrays[key],dtype=float); b=np.asarray(right.arrays[key],dtype=float)
    if a.shape != b.shape: raise ValueError("Difference requires identical array shapes.")
    if key == "energy" and not np.allclose(a,b,rtol=1e-9,atol=1e-12): raise ValueError("Difference requires an identical energy grid.")
    return b-a


def frequency_convert(values, source, target):
    import numpy as np
    if source == target:return np.asarray(values,dtype=float).copy()
    factors={("THz","cm^-1"):33.3564095,("cm^-1","THz"):1/33.3564095}
    if (source,target) not in factors: raise ValueError(f"Unsupported frequency conversion: {source} to {target}.")
    return np.asarray(values,dtype=float)*factors[(source,target)]
