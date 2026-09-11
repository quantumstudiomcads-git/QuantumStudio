import os
import sys
import json
from pathlib import Path as _Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from backend.runtime import BUILD_CHANNEL, PRODUCT_NAME, VERSION, build_identity, configure_logging
from backend.runtime.resources import initialize_application_data

from frontend.app.project_hub import ProjectHub
from frontend.analyze import AnalyzeWorkspace
from frontend.builder import Builder
from frontend.calculate import CalculateWorkspace
from frontend.core.project import Project
from backend.licensing import LicensingService


def main():

    logger = configure_logging()
    try:
        initialize_application_data()
    except OSError:
        # Basic GUI use must survive missing/unwritable optional user-data
        # roots; individual save/export actions report their own failures.
        logger.exception("Application data initialization failed; continuing in degraded mode")
    app = QApplication(
        sys.argv
    )

    app.setApplicationName(PRODUCT_NAME)
    app.setApplicationVersion(VERSION)

    app.setOrganizationName(
        PRODUCT_NAME
    )

    display_identity = PRODUCT_NAME if BUILD_CHANNEL == "development" else f"{PRODUCT_NAME} {VERSION} {BUILD_CHANNEL}"
    app.setApplicationDisplayName(display_identity)
    from frontend.app.theme import application_stylesheet
    app.setStyleSheet(application_stylesheet())

    # Production startup receives a fail-closed service.  It never creates a
    # developer entitlement, even on the development build channel.
    hub = ProjectHub(licensing_service=LicensingService.production())

    hub.show()

    if os.environ.get("QUANTUM_STUDIO_PACKAGED_CATALOGUE_SMOKE") == "1":
        def packaged_catalogue_smoke() -> None:
            calculate = CalculateWorkspace(Project("Packaged Catalogue Smoke"))
            from frontend.calculations.catalog import public_catalogue_snapshot
            payload = {
                "identity": build_identity(),
                "product_footer": hub.product_identity_label.text(),
                "catalogue": public_catalogue_snapshot(),
                "workspace_ids": tuple(descriptor.id for descriptor in calculate.catalog_descriptors),
                "workspace_categories": tuple(
                    calculate.category_combo.itemText(index)
                    for index in range(1, calculate.category_combo.count())
                ),
            }
            calculate.close()
            print("PACKAGED_CATALOGUE: " + json.dumps(payload, sort_keys=True), flush=True)
            app.quit()
        QTimer.singleShot(0, packaged_catalogue_smoke)

    if os.environ.get("QUANTUM_STUDIO_PACKAGED_SMOKE") == "1":
        def packaged_smoke() -> None:
            project = Project("Packaged Smoke")
            smoke_root = _Path(os.environ.get("QUANTUM_STUDIO_PACKAGED_SMOKE_DATA", _Path.home())) / "Quantum Studio Smoke ü"
            smoke_root.mkdir(parents=True, exist_ok=True)
            project_path = smoke_root / "My Quantum Studio Test.qs"
            project.save(project_path)
            restored = Project.load(project_path)
            if restored.name != project.name:
                raise RuntimeError("packaged project round-trip failed")
            Builder(project)
            CalculateWorkspace(project)
            AnalyzeWorkspace(project)
            smoke_detail = "QS_ROUNDTRIP PASS"
            if os.environ.get("QUANTUM_STUDIO_PACKAGED_SCF_SMOKE") == "1":
                from backend.execution import ExecutionStore, LocalExecutionManager, LocalToolConfiguration
                from backend.pseudopotentials.models import sha256
                from frontend.calculations.catalog import CALCULATIONS
                from frontend.services.calculation_service import CalculationService
                from frontend.services.result_service import ResultService
                from frontend.core import Atom, Structure
                engine_root = _Path(os.environ["QUANTUM_STUDIO_RC_ENGINE_ROOT"])
                pseudo = _Path(os.environ["QUANTUM_STUDIO_RC_SI_PSEUDO"])
                structure = Structure([Atom("Si", 0.0, 0.0, 0.0), Atom("Si", 1.3575, 1.3575, 1.3575)], [[5.43, 0.0, 0.0], [0.0, 5.43, 0.0], [0.0, 0.0, 5.43]], "Si RC Smoke")
                project.set_structure(structure)
                parameters = {"xc_functional": "pbe", "ecutwfc": 12.0, "ecutrho": 48.0, "conv_thr": 1.0e-6, "electron_maxstep": 50, "kpoints": [1, 1, 1], "pseudopotentials": {"Si": {"element": "Si", "filename": pseudo.name, "source": str(pseudo), "sha256": sha256(pseudo), "pseudo_type": "USPP", "xc_functional": "pbe"}}}
                service = CalculationService(CALCULATIONS)
                prepared = service.create_request(project, ["scf"], parameters, name="Si RC Engine Smoke")
                project.add_calculation(prepared.backend_request)
                workflow_parent = _Path(os.environ.get("QUANTUM_STUDIO_PACKAGED_SMOKE_DATA", _Path.home())) / "Quantum Studio RC Engine Smoke"
                generated = service.generate_engine_inputs(prepared, workflow_parent)
                workflow = service.execution_workflow(prepared, generated)
                pw_candidates = (
                    engine_root / "bin" / "pw.x",
                    engine_root / "PW" / "src" / "pw.x",
                )
                pw_path = next((candidate for candidate in pw_candidates if candidate.is_file()), pw_candidates[0])
                tools = LocalToolConfiguration(tool_paths={"pw.x": str(pw_path)}, qe_version="7.6", cpu_cores=1, omp_threads=1)
                manager = LocalExecutionManager(tools)
                errors = manager.preflight(workflow)
                if errors:
                    raise RuntimeError("Packaged SCF preflight failed: " + "\n".join(errors))
                store = ExecutionStore(generated)
                record = store.create(workflow)
                record = manager.execute(workflow, record=record, store=store)
                if record.state.value != "COMPLETED":
                    raise RuntimeError(f"Packaged SCF execution failed: {record.state.value}")
                parsed = ResultService().parse(generated, record.execution_id)
                if parsed["errors"] or not parsed["parsed"]:
                    raise RuntimeError(f"Packaged SCF parse failed: {parsed['errors']}")
                project.register_execution_root(prepared.backend_request.id, generated)
                project_path = smoke_root / "Si-RC-Smoke.qs"
                project.save(project_path)
                restored = Project.load(project_path)
                if not restored.execution_roots():
                    raise RuntimeError("Packaged SCF project persistence failed")
                smoke_detail = f"QS_ROUNDTRIP PASS SCF execution={record.execution_id} result={parsed['parsed'][0]}"
            print(f"PACKAGED_SMOKE: {build_identity()} ProjectHub Builder Calculate Analyze {smoke_detail}", flush=True)
            app.quit()
        QTimer.singleShot(0, packaged_smoke)

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":
    main()
