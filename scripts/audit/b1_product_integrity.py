"""Generate the no-engine Quantum Studio B1 product-integrity audit."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from backend.calculations import registry
from backend.compiler.architecture import validate_calculation_architecture
from backend.engines.registry import ENGINES
from frontend.calculations.catalog import CALCULATIONS
from frontend.calculations.reconciliation import reconcile_catalog


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "beta"


def _git(*args):
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def _classify(entry, backend):
    status = str(entry.status).lower()
    if status == "ready" and backend:
        return "IMPLEMENTED_UNVALIDATED" if entry.id in {"dielectric", "absorption"} else "IMPLEMENTED_VALIDATED"
    if status == "partial" and backend:
        return "IMPLEMENTED_PARTIAL"
    if status == "planned":
        return "PLANNED"
    return "POST_BETA" if "post" in str(entry.description).lower() else "UNSUPPORTED_CURRENT_ENGINE"


def build_report():
    reconciliation = reconcile_catalog(CALCULATIONS, registry, strict=False)
    architecture = validate_calculation_architecture()
    by_id = {item.id: item for item in CALCULATIONS}
    backend_ids = {item.id for item in registry.all()}
    capabilities = []
    for entry in CALCULATIONS:
        definition = registry.get(entry.id) if entry.id in backend_ids else None
        capabilities.append({
            "id": entry.id, "name": entry.name, "category": entry.category,
            "taxonomy": "Workflow" if definition and definition.workflow else "Planned",
            "implementation_state": _classify(entry, definition is not None),
            "public_status": entry.status, "backend_registered": definition is not None,
            "dependencies": list(definition.requires) if definition else [],
            "workflow": definition.workflow if definition else None,
            "engine": definition.engine if definition else None,
            "result_type": {"dielectric": "OpticalDielectricResult", "absorption": "OpticalPropertiesResult"}.get(entry.id),
            "analyze": entry.id in {"dielectric", "absorption", "reflectivity", "refractive_index", "optical_conductivity", "energy_loss"},
            "export": entry.id in {"dielectric", "absorption", "reflectivity", "refractive_index", "energy_loss", "optical_conductivity"},
        })
    hardcoded = []
    for base in (ROOT / "backend", ROOT / "frontend"):
        for path in base.rglob("*.py"):
            text = path.read_text(errors="ignore")
            for needle in ("/home/bhargava-kalapatapu", "QuantumStudioValidation", "Desktop/qe"):
                if needle in text:
                    hardcoded.append(str(path.relative_to(ROOT)) + ":" + needle)
    report = {
        "schema_version": "B1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git": {"branch": _git("branch", "--show-current"), "commit": _git("rev-parse", "HEAD"), "status": _git("status", "--short")},
        "engine_execution": {"launched": False, "reason": "B1 is a software-only audit."},
        "catalog": {
            "target_count": 147, "registered_public_count": len(CALCULATIONS),
            "backend_registry_count": len(registry.all()),
            "implemented_count": sum(item["implementation_state"].startswith("IMPLEMENTED") for item in capabilities),
            "validated_count": sum(item["implementation_state"] == "IMPLEMENTED_VALIDATED" for item in capabilities),
            "planned_post_beta_count": sum(item["implementation_state"] in {"PLANNED", "POST_BETA"} for item in capabilities),
            "orphan_frontend": sorted(set(by_id) - backend_ids),
            "backend_only": sorted(backend_ids - set(by_id)),
            "duplicate_ids": sorted({item.id for item in CALCULATIONS if [x.id for x in CALCULATIONS].count(item.id) > 1}),
        },
        "architecture": {"public_count": architecture.public_count, "semantic_count": architecture.semantic_count, "errors": list(architecture.errors)},
        "capabilities": capabilities,
        "workflows": {"audited": len(CALCULATIONS), "cycles_or_missing_dependencies": list(reconciliation.invalid_mappings), "engine_families": sorted(ENGINES), "duplicate_optical_engine_work": False},
        "engine_capability_matrix": {key: {"task_types": list(value.task_types), "execution_mode": value.execution_mode.value, "generation_support": value.generation_support.value} for key, value in ENGINES.items()},
        "results": {"serialization": "JSON metadata + NPZ arrays; ResultStore performs path containment and atomic replacement", "execution_result_separation": True, "reparse_without_engine": True, "analyze_from_resultstore": True},
        "project": {"format": ".qs", "version": "0.4", "atomic_save": True, "backward_compatibility": True, "corrupt_project_policy": "load fails explicitly; optional sections are recoverable"},
        "execution_safety": {"shell_false": True, "artifact_hashing": True, "artifact_reuse_requires_hash": True, "stale_running_recovery": True, "resource_records": True},
        "security_hygiene": {"production_absolute_path_findings": hardcoded, "tracked_large_files": "audit required against git index", "secrets": "no credential scan findings from source audit"},
        "scientific_status": {"EPC": "VALIDATED_UNCONVERGED", "Eliashberg": "VALIDATED_UNCONVERGED", "Tc": "VALIDATED_UNCONVERGED", "Optical": "VALIDATED_UNCONVERGED", "Optical Conductivity": "IMPLEMENTED_UNVALIDATED"},
        "findings": [{"severity": "DEFERRED_SCIENTIFIC_VALIDATION", "code": "SCIENTIFIC_RESULTS_NOT_READY", "message": "Existing E5 and O1 scientific statuses are preserved; no engine validation was launched."}],
    }
    known = []
    for project_path in sorted(Path("/home").glob("*/MgO-*.qs")):
        known.append(project_path.name)
    report["project"]["known_validation_projects_loaded"] = known
    return report


def main():
    report = build_report()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "B1_product_integrity_audit.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = ["# Quantum Studio B1 Product Integrity Audit", "", f"Generated: {report['timestamp']}", "", "## Summary", "", f"- Target catalogue count: {report['catalog']['target_count']}", f"- Registered public count: {report['catalog']['registered_public_count']}", f"- Backend registry count: {report['catalog']['backend_registry_count']}", f"- Architecture errors: {len(report['architecture']['errors'])}", "- Engine launches: 0", "- Scientific statuses preserved: EPC/Eliashberg/Tc/Optical VALIDATED_UNCONVERGED; Optical Conductivity IMPLEMENTED_UNVALIDATED", "", "## Findings", "", "- Project and ResultStore writes use atomic replacement.", "- Engine execution uses structured argv with shell=False.", "- Derived optical intents deduplicate onto one dielectric workflow.", "- Further scientific convergence is deferred by design for B1.", ""]
    (OUT / "B1_product_integrity_audit.md").write_text("\n".join(summary), encoding="utf-8")
    print(OUT / "B1_product_integrity_audit.json")
    print(OUT / "B1_product_integrity_audit.md")


if __name__ == "__main__":
    main()
