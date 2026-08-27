"""Asynchronous Calculate input preparation shared by Generate and Run."""

from __future__ import annotations

import traceback

from PySide6.QtCore import QThread, Signal

from backend.pseudopotentials import PseudoProvisioner, ProvisionError


def _assignment(record):
    return {
        "filename": record.filename,
        "source": record.path,
        "sha256": record.sha256,
        "library_id": record.library_id,
        "library_version": record.library_version,
        "xc_functional": record.xc_functional,
        "pseudo_type": record.pseudo_type.value,
        "relativistic": record.relativity.value,
        "recommended_ecutwfc_ry": record.recommended_ecutwfc_ry,
        "recommended_ecutrho_ry": record.recommended_ecutrho_ry,
    }


class CalculationPreparationWorker(QThread):
    """Prepare one immutable request without touching Project or Qt widgets."""

    progress = Signal(str)

    def __init__(self, service, prepared_request, output_root, provisioner=None, parent=None, repair_workflow_root=None):
        super().__init__(parent)
        self.service = service
        self.prepared_request = prepared_request
        self.output_root = str(output_root)
        self.provisioner = provisioner or PseudoProvisioner()
        self.repair_workflow_root = str(repair_workflow_root) if repair_workflow_root else None
        self.result = None
        self.error = None

    def run(self):
        try:
            prepared = self.prepared_request
            parameters = dict(prepared.backend_request.parameters)
            if parameters.get("pseudopotential_mode") != "manual" and not parameters.get("pseudopotentials"):
                self.progress.emit("Checking pseudopotentials…")
                species = tuple(dict.fromkeys(
                    str(atom.get("element"))
                    for atom in prepared.backend_request.structure.get("atoms", ())
                    if atom.get("element")
                ))
                policy = parameters.get("pseudopotential_mode", "auto")
                results = self.provisioner.provision_set(
                    species, parameters.get("xc_functional", "pbe"),
                    bool(parameters.get("soc", False)), policy,
                )
                parameters["pseudopotentials"] = {
                    result.record.element: _assignment(result.record) for result in results
                }
                updated = prepared.backend_request.copy_with(parameters=parameters)
                prepared = self.service.prepare_persisted_request(updated)
                self.progress.emit("Pseudopotentials ready.")
            self.progress.emit("Compiling calculation…")
            plan = self.service.compile_request(prepared)
            if self.repair_workflow_root:
                self.progress.emit("Validating workflow pseudopotentials…")
                location = self.service.materialize_existing_qe_workflow(self.repair_workflow_root)
            else:
                self.progress.emit("Generating QE inputs…")
                location = self.service.generate_engine_inputs(prepared, self.output_root)
            self.result = (prepared, plan, str(location))
        except Exception as error:
            if isinstance(error, ProvisionError) and "untrusted download location" in str(error):
                message = "The pseudopotential provider returned an untrusted download location."
            elif isinstance(error, ProvisionError):
                message = str(error)
            else:
                message = str(error) or type(error).__name__
            self.error = (message, traceback.format_exc())
