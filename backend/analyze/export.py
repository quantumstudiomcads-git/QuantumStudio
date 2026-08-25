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
