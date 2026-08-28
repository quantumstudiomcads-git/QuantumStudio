"""Qt-free transformations over ScientificResult only."""
from __future__ import annotations

def result_kind(result):
    return {"BandStructureResult":"Band Structure", "DOSResult":"Density of States", "PDOSResult":"Projected DOS", "PhononDOSResult":"Phonon DOS", "GroundStateResult":"Ground State", "RelaxationResult":"Relaxation", "WannierizationResult":"Wannier", "ElectronPhononResult":"EPW", "VolumetricResult":"Volumetric Field", "WorkFunctionResult":"Work Function", "BandGapResult":"Band Gap Analysis", "EffectiveMassResult":"Effective Mass", "BaderChargeResult":"Bader Charge Analysis", "ChargeTransferResult":"Atomic Charge Transfer (Bader)", "LowdinPopulationResult":"Löwdin Population Analysis", "MagneticMomentResult":"Magnetic Moments", "OrbitalCharacterResult":"Orbital Character / Orbital Texture"}.get(result.result_type, result.result_type)

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
    if t=="BandGapResult":
        rows=[["sampled_fundamental_gap",result.scalars.get("sampled_gap",{}).get("value", ""),"eV"],["minimum_sampled_direct_gap",result.scalars.get("minimum_sampled_direct_gap",{}).get("value", ""),"eV"],["VBM_energy",result.scalars.get("vbm",{}).get("value", ""),"eV"],["CBM_energy",result.scalars.get("cbm",{}).get("value", ""),"eV"],["classification",result.metadata.get("classification", ""),""],["VBM_k_index",(result.metadata.get("vbm") or {}).get("path_sample_index", ""),""],["CBM_k_index",(result.metadata.get("cbm") or {}).get("path_sample_index", ""),""],["VBM_band",(result.metadata.get("vbm") or {}).get("band_index", ""),""],["CBM_band",(result.metadata.get("cbm") or {}).get("band_index", ""),""]]
        return ["quantity","value","unit"], rows
    if t=="EffectiveMassResult":
        x=_values(result,"k_distance_Ainv"); y=_values(result,"energy_eV"); fit=_values(result,"fit_energy_eV"); rows=[[x[i],y[i],fit[i] if i<len(fit) else ""] for i in range(len(x))]
        return ["k_distance_Ainv","energy_eV","fit_energy_eV"], rows
    if t=="LowdinPopulationResult":
        arrays=result.arrays; species=list(result.metadata.get("species",())); n=len(_values(result,"population"));
        cols=["atom_index","species","projector_index","projector_label","l","population"]
        if "population_up" in arrays: cols += ["population_up","population_down","spin_difference"]
        labels=list(result.metadata.get("projector_labels",()))
        rows=[]
        for i in range(n):
            row=[_values(result,"atom_index")[i],species[i] if i<len(species) else "",_values(result,"projector_index")[i],labels[i] if i<len(labels) else "",_values(result,"l")[i],_values(result,"population")[i]]
            if "population_up" in arrays: row += [_values(result,key)[i] for key in ("population_up","population_down","spin_difference")]
            rows.append(row)
        return cols,rows
    if t=="MagneticMomentResult":
        idx=_values(result,"atom_index"); moments=_values(result,"projected_local_moment"); species=list(result.metadata.get("species",()))
        return ["atom_index","species","projected_local_moment"], [[idx[i],species[i] if i<len(species) else "",moments[i]] for i in range(min(len(idx),len(moments)))]
    if t=="OrbitalCharacterResult":
        n=len(_values(result,"projection_weight")); species=list(result.metadata.get("species",())); labels=list(result.metadata.get("projector_labels",())); rows=[]
        keys=("k_index","k_distance","band_index","energy_eV","atom_index","projector_index","l","m","projection_weight")
        cols=[key for key in keys if key in result.arrays]
        rows=[[(_values(result,key)[i] if i<len(_values(result,key)) else "") for key in cols] for i in range(n)]
        if "species" not in cols: cols.insert(5,"species"); [row.insert(5,species[i] if i<len(species) else "") for i,row in enumerate(rows)]
        if "projector_label" not in cols: cols.insert(6,"projector_label"); [row.insert(6,labels[i] if i<len(labels) else "") for i,row in enumerate(rows)]
        return cols,rows
    if t=="BaderChargeResult":
        idx=_values(result,"atom_index"); pos=result.arrays.get("positions_A",()); pos=pos.tolist() if hasattr(pos,"tolist") else list(pos)
        columns={"bader_electrons":_values(result,"bader_electrons"),"pseudo_valence":_values(result,"pseudo_valence_charge") or _values(result,"z_valence"),"net_charge":_values(result,"net_charge"),"basin_volume":_values(result,"basin_volume_A3"),"min_distance":_values(result,"minimum_distance_A")}
        species=list(result.metadata.get("species",()))
        rows=[]
        for i,atom in enumerate(idx):
            xyz=list(pos[i]) if i<len(pos) else ["","",""]
            rows.append([atom,species[i] if i<len(species) else "",*(xyz+["","",""])[:3],*[columns[key][i] if i<len(columns[key]) else "" for key in columns]])
        return ["atom_index","species","x","y","z",*columns], rows
    if t=="ChargeTransferResult":
        idx=_values(result,"atom_index"); transfer=_values(result,"charge_transfer") or _values(result,"transfer") or _values(result,"net_charge"); species=list(result.metadata.get("species",()))
        return ["atom_index","species","charge_transfer"], [[idx[i],species[i] if i<len(species) else "",transfer[i]] for i in range(min(len(idx),len(transfer)))]
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
