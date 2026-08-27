from __future__ import annotations
import csv
from pathlib import Path
from .transforms import tabular_data, pdos_channels, energy_reference

def export_dos_pdos_csv(result, path, *, reference="Absolute", channels=None):
    import numpy as np
    raw=np.asarray(result.arrays.get("energy",()),dtype=float)
    display=energy_reference(result,"Fermi = 0") if reference=="Fermi = 0" else raw.copy()
    target=Path(path); target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("w",newline="",encoding="utf-8") as stream:
        writer=csv.writer(stream)
        if result.result_type=="DOSResult":
            if "dos_up" in result.arrays and "dos_down" in result.arrays:
                headers=["energy_raw_eV","energy_display_eV","dos_up_states_per_eV_cell","dos_down_states_per_eV_cell"]
                columns=[raw,display,np.asarray(result.arrays["dos_up"],dtype=float),np.asarray(result.arrays["dos_down"],dtype=float)]
            else:
                headers=["energy_raw_eV","energy_display_eV","dos_total_states_per_eV_cell"]
                columns=[raw,display,np.asarray(result.arrays.get("dos",result.arrays.get("total_dos",())),dtype=float)]
            if "integrated_dos" in result.arrays: headers.append("integrated_dos_states_per_cell"); columns.append(np.asarray(result.arrays["integrated_dos"],dtype=float))
            writer.writerow(headers); writer.writerows(zip(*columns))
        elif result.result_type=="PDOSResult":
            selected=channels if channels is not None else pdos_channels(result)
            writer.writerow(["energy_raw_eV","energy_display_eV","species","atom_index","orbital","spin","aggregation_label","pdos_states_per_eV_cell"])
            for component,values in selected:
                for index,value in enumerate(values):
                    writer.writerow([raw[index],display[index],component.get("species",""),component.get("atom_index",component.get("atom","")),component.get("orbital",component.get("orbital_label","")),component.get("spin",""),component.get("label","") if component.get("aggregated") else "",value])
        else: raise ValueError("DOS/PDOS CSV export requires a DOSResult or PDOSResult.")
    return target

def export_csv(result, path):
    if result.result_type in {"DOSResult","PDOSResult"}: return export_dos_pdos_csv(result,path)
    headers, rows=tabular_data(result)
    if not headers: raise ValueError("This result does not expose tabular data.")
    target=Path(path); target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("w",newline="",encoding="utf-8") as stream:
        writer=csv.writer(stream); writer.writerow(headers); writer.writerows(rows)
    return target


def export_comparison(model, directory, *, operation="overlay", reference="Absolute"):
    from pathlib import Path
    import json
    root=Path(directory); root.mkdir(parents=True,exist_ok=True)
    manifest={"result_family":model.result_family,"compatibility":model.compatibility,"operation":operation,"reference":reference,"series":[]}
    for index,series in enumerate(model.series,1):
        path=root/f"series_{index:02d}.csv"; export_csv(series.scientific_result,path)
        p=series.scientific_result.provenance
        manifest["series"].append({"order":index,"label":series.label,"request_id":series.request_id,"execution_id":series.execution_id,"status":series.status,"functional":series.functional,"structure_fingerprint":p.structure_fingerprint,"units":series.units})
    (root/"comparison.json").write_text(json.dumps(manifest,indent=2,sort_keys=True),encoding="utf-8")
    return root
