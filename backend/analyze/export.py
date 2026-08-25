from __future__ import annotations
import csv
from pathlib import Path
from .transforms import tabular_data

def export_csv(result, path):
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
