"""Generate deterministic B3 catalogue and backend capability snapshots.

This is an audit tool, not a second calculation registry.  It records the
existing public catalogue, executable registry, semantic classification, and
the result-routing contract that is already implemented by Calculate.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from backend.calculations import registry
from backend.calculations.semantics import SEMANTICS
from frontend.calculations.catalog import CALCULATIONS
from frontend.calculations.reconciliation import reconcile_catalog


RESULT_ROUTES = {
    "scf": "QE_SCF_STDOUT",
    "relax": "QE_RELAX_STDOUT",
    "vc_relax": "QE_RELAX_STDOUT",
    "bands": "BAND_STRUCTURE_RAW_DATA",
    "dos": "DOS_RAW_DATA",
    "pdos": "PDOS_RAW_DATA",
    "phonons": "QE_PHONON_GAMMA",
    "phonon_dos": "PHONON_DOS_RAW_DATA",
    "phonon_band_structure": "PHONON_DISPERSION_RAW_DATA",
    "qe_matdyn_dispersion": "PHONON_DISPERSION_RAW_DATA",
    "raman": "QE_RAMAN",
    "infrared": "QE_DYNMAT_POLAR",
    "lo_to_splitting": "QE_DYNMAT_POLAR",
    "born_charges": "QE_POLAR_GAMMA",
    "dielectric_phonon": "QE_DYNMAT_PHONON_DIELECTRIC",
    "electron_phonon": "EPW_SUMMARY",
    "dielectric": "QE_EPSILON_TENSOR",
}


def _json_default(value):
    if hasattr(value, "value"):
        return value.value
    return str(value)


def _accepted_catalogue():
    source = subprocess.run(
        ["git", "show", "2a5b0a3:frontend/calculations/catalog.py"],
        check=True, capture_output=True, text=True,
    ).stdout
    module_name = "b3_accepted_catalogue"
    namespace = {"__name__": module_name}
    module = type(sys)(module_name)
    module.__dict__.update(namespace)
    sys.modules[module_name] = module
    namespace = module.__dict__
    exec(compile(source, "catalog.py@2a5b0a3", "exec"), namespace)
    return tuple(namespace["CALCULATIONS"])


def build_catalogue_snapshot(catalog=CALCULATIONS):
    reconciliation = reconcile_catalog(catalog, registry, strict=False)
    descriptors = {item.id: item for item in reconciliation.descriptors}
    rows = []
    for info in catalog:
        definition = registry.get(info.id) if registry.exists(info.id) else None
        semantics = SEMANTICS.get(info.id)
        rows.append(
            {
                "id": info.id,
                "name": info.name,
                "category": info.category,
                "description": info.description,
                "engine": info.engine,
                "tags": list(info.tags),
                "status": info.status,
                "public": True,
                "executable_while_partial": info.executable_while_partial,
                "backend_present": definition is not None,
                "execution_support": descriptors[info.id].execution_support.value,
                "backend_supported": descriptors[info.id].backend_supported,
                "requires": list(getattr(definition, "requires", ())),
                "workflow": getattr(definition, "workflow", None),
                "backend_engine": getattr(definition, "engine", None),
                "parameters": list(getattr(definition, "parameters", ())),
                "produces": list(getattr(definition, "produces", ())),
                "kind": getattr(getattr(semantics, "kind", None), "value", None),
                "input_cardinality": getattr(getattr(semantics, "input_cardinality", None), "value", None),
                "workflow_family": getattr(semantics, "workflow_family", None),
                "result_route": RESULT_ROUTES.get(info.id),
                "implementation_status": info.status,
            }
        )
    return {
        "schema_version": 1,
        "source": "frontend.calculations.catalog.CALCULATIONS",
        "catalogue_count": len(rows),
        "categories": sorted({row["category"] for row in rows}),
        "entries": rows,
        "reconciliation": {
            "backend_count": reconciliation.backend_count,
            "frontend_only_ids": list(reconciliation.frontend_only_ids),
            "backend_only_ids": list(reconciliation.backend_only_ids),
            "invalid_mappings": list(reconciliation.invalid_mappings),
        },
    }


def build_backend_snapshot():
    catalogue_ids = {item.id for item in CALCULATIONS}
    rows = []
    for definition in registry.all():
        rows.append(
            {
                "id": definition.id,
                "name": definition.name,
                "human_meaning": definition.description,
                "category": definition.category,
                "engine": definition.engine,
                "workflow": definition.workflow,
                "requires": list(definition.requires),
                "parameters": list(definition.parameters),
                "produces": list(definition.produces),
                "metadata": definition.metadata,
                "public_catalogue_mapping": definition.id if definition.id in catalogue_ids else None,
                "result_route": RESULT_ROUTES.get(definition.id),
            }
        )
    return {
        "schema_version": 1,
        "source": "backend.calculations.registry",
        "backend_definition_count": len(rows),
        "definitions": rows,
        "private_workflow_nodes": [
            "qe_ph",
            "qe_q2r",
            "qe_matdyn_dispersion",
            "qe_matdyn_dos",
            "qe_pw_nscf",
            "qe_bands",
            "qe_dos",
            "qe_projwfc",
        ],
    }


def main() -> None:
    repository = Path(__file__).resolve().parents[1]
    output = repository.parent / "reports"
    output.mkdir(parents=True, exist_ok=True)
    for filename, payload in (
        ("B3_catalogue_before.json", build_catalogue_snapshot(_accepted_catalogue())),
        ("B3_catalogue_after.json", build_catalogue_snapshot()),
        ("B3_backend_capabilities.json", build_backend_snapshot()),
    ):
        (output / filename).write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {output / filename}")


if __name__ == "__main__":
    main()
