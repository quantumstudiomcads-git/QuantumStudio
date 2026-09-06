"""Independent-particle optical workflow expansion."""
from __future__ import annotations

import hashlib
import json

from backend.compiler.execution_plan import PlannedTask
from backend.engines.qe.models import InvalidQEParameterError
from backend.engines.qe.optical import OpticalSettings


def _signature(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()[:16]


def expand_optical(request, tasks, parameters):
    """Replace public optical intents with one dense NSCF and epsilon.x task."""
    requested = set(request.selected_calculations)
    if not requested & {"dielectric", "absorption", "refractive_index", "extinction_coefficient", "reflectivity", "energy_loss", "optical_conductivity"}:
        return tasks
    scf = next((task for task in tasks if task.calculation_id == "scf"), None)
    dielectric = next((task for task in tasks if task.calculation_id == "dielectric"), None)
    if scf is None or dielectric is None:
        raise InvalidQEParameterError("Optical Properties require the shared SCF and dielectric workflow nodes.")
    settings = OpticalSettings.from_parameters(parameters.get("dielectric", {}))
    nscf_values = dict(scf.parameters)
    from backend.optical.models import CarrierRegime, Dimensionality, OpticalCalculationSpecification, OpticalWorkflowRouter, SystemCharacterization
    optical_values = dict(parameters.get("dielectric", {}))
    optical_values.setdefault("optical_k_mesh", settings.optical_k_mesh)
    optical_values.setdefault("optical_nbnd", settings.optical_nbnd)
    optical_values.setdefault("energy_points", settings.number_of_points)
    optical_values.setdefault("requested_tensor_components", settings.requested_directions)
    spec = OpticalCalculationSpecification.from_dict(optical_values)
    system = SystemCharacterization(
        dimensionality=Dimensionality(str(optical_values.get("dimensionality", "BULK_3D"))),
        carrier_regime=CarrierRegime(str(optical_values.get("carrier_regime", "SEMICONDUCTOR"))),
        spin_polarized=bool(nscf_values.get("spin", False)), soc=bool(nscf_values.get("soc", False)),
        noncollinear=bool(nscf_values.get("noncollinear", False)),
        dft_plus_u=bool(nscf_values.get("hubbard_terms")),
        hybrid_functional=str(nscf_values.get("functional", "pbe")).lower() not in {"pbe", "pbesol", "pz", "lda"},
        occupations=str(nscf_values.get("occupations", "fixed")),
    )
    optical_route = OpticalWorkflowRouter().route(spec, system)
    nscf_values.update({
        "kpoints": {"mode": "automatic", "mesh": list(settings.optical_k_mesh), "shifts": [0, 0, 0]},
        "optical_full_grid": list(settings.optical_k_mesh),
        "nosym": True, "noinv": True,
        "nbnd": settings.optical_nbnd,
        "wf_collect": True,
    })
    signature = _signature({"purpose": "optical_dense_nscf", "scf": scf.parameter_signature, "parameters": nscf_values})
    nscf = PlannedTask(
        id=f"{request.id}:qe_pw_nscf_optical:{signature}", calculation_id="qe_pw_nscf_optical",
        semantic_task_type="qe_pw_nscf", engine_id="quantum_espresso", tool_id="pw.x",
        parameter_signature=signature, depends_on_task_ids=(scf.id,), parameters=nscf_values,
        structure_reference="request_snapshot", artifact_inputs=("qe_save", "qe_charge_density"),
        artifact_outputs=("QE_OPTICAL_ELECTRONIC_STATE",),
        metadata={"purpose": "optical_dense_nscf", "optical_settings": settings.to_metadata(), "parent_scf_task_id": scf.id, "optical_route": optical_route},
    )
    epsilon_signature = _signature({"purpose": "epsilon", "nscf": nscf.parameter_signature, "settings": settings.to_metadata()})
    declared = [
        {"logical_name": "QE_EPSILON_REAL", "relative_path": "epsr_{qe_prefix}.dat", "artifact_type": "FILE", "required": True, "materialization_policy": "COPY"},
        {"logical_name": "QE_EPSILON_IMAGINARY", "relative_path": "epsi_{qe_prefix}.dat", "artifact_type": "FILE", "required": True, "materialization_policy": "COPY"},
    ]
    epsilon = PlannedTask(
        id=f"{request.id}:qe_epsilon:{epsilon_signature}", calculation_id="qe_epsilon", semantic_task_type="qe_epsilon",
        engine_id="quantum_espresso", tool_id="epsilon.x", parameter_signature=epsilon_signature,
        depends_on_task_ids=(nscf.id,), parameters={"optical": settings.to_metadata()},
        structure_reference="request_snapshot", artifact_inputs=("QE_OPTICAL_ELECTRONIC_STATE",),
        artifact_outputs=("QE_COMPLEX_DIELECTRIC",),
        metadata={"purpose": "independent_particle_optical", "optical_settings": settings.to_metadata(), "artifact_declarations": declared,
                  "response_scope": "Independent-particle RPA dielectric response (QE epsilon.x dipole approximation).", "optical_route": optical_route},
    )
    return [task for task in tasks if task.calculation_id not in {"dielectric", "absorption", "refractive_index", "extinction_coefficient", "reflectivity", "energy_loss", "optical_conductivity"}] + [nscf, epsilon]
