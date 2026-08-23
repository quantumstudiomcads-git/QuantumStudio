"""Thin Device Builder integration over frozen public Builder interface builders."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

import numpy as np

from frontend.builder.build.heterostructure import create_heterostructure
from frontend.builder.build.moire import create_moire_structure
from frontend.core import Structure, StructureIO
from frontend.device_builder.assembly import detect_inter_region_collisions, fit_device_cell
from frontend.device_builder.model import DeviceInterface, InterfaceMode


DEFAULT_MAX_INTERFACE_ATOMS = 100_000


@dataclass(frozen=True)
class InterfaceMatchResult:
    interface: DeviceInterface
    source_structure_a: Structure
    source_structure_b: Structure


def _validate_match_inputs(region_a, region_b, *, mode, requested_twist_deg, max_strain, gap, max_index, atom_count_limit):
    if region_a is None or region_b is None:
        raise ValueError("Both interface regions must exist.")
    if region_a.id == region_b.id:
        raise ValueError("Interface regions must be different.")
    if not isinstance(region_a.source_structure, Structure) or not isinstance(region_b.source_structure, Structure):
        raise ValueError("Interface regions require valid native source Structures.")
    if not region_a.source_structure.atoms or not region_b.source_structure.atoms:
        raise ValueError("Interface regions must both contain atoms.")
    mode = InterfaceMode(mode)
    requested_twist_deg = float(requested_twist_deg)
    max_strain = float(max_strain)
    gap = float(gap)
    max_index = int(max_index)
    atom_count_limit = int(atom_count_limit)
    if not isfinite(requested_twist_deg):
        raise ValueError("Requested twist must be finite.")
    if mode is InterfaceMode.ALIGNED and abs(requested_twist_deg) > 1e-12:
        raise ValueError("Aligned interfaces require zero requested twist.")
    if not isfinite(max_strain) or max_strain < 0.0:
        raise ValueError("Interface max strain must be finite and non-negative.")
    if not isfinite(gap) or gap < 0.0:
        raise ValueError("Interface gap must be finite and non-negative.")
    if max_index < 1:
        raise ValueError("Interface max_index must be at least 1.")
    if atom_count_limit < 1:
        raise ValueError("Interface atom-count limit must be positive.")
    estimated_upper_bound = (len(region_a.source_structure.atoms) + len(region_b.source_structure.atoms)) * max_index**2
    if estimated_upper_bound > atom_count_limit:
        raise ValueError(
            f"Interface search may create up to {estimated_upper_bound} atoms, exceeding the "
            f"configured safety limit of {atom_count_limit}."
        )
    # Exercise the canonical ASE boundary before entering the frozen builder operation.
    return mode, requested_twist_deg, max_strain, gap, max_index, StructureIO.to_ase(region_a.source_structure), StructureIO.to_ase(region_b.source_structure)


def _builder_metadata(result, mode, requested_twist_deg, gap, max_index, strain_mode):
    prefix = "moire" if mode is InterfaceMode.TWISTED else "heterostructure"
    info = result.info
    return {
        "matrix_a": info.get(f"{prefix}_matrix_A", info.get("heterostructure_matrix_bottom")),
        "matrix_b": info.get(f"{prefix}_matrix_B", info.get("heterostructure_matrix_top")),
        "determinant_a": int(info.get(f"{prefix}_det_A", info.get("heterostructure_det_A", 1))),
        "determinant_b": int(info.get(f"{prefix}_det_B", info.get("heterostructure_det_B", 1))),
        "principal_strains_a": list(info.get(f"{prefix}_principal_strains_A", info.get("heterostructure_principal_strain_A", []))),
        "principal_strains_b": list(info.get(f"{prefix}_principal_strains_B", info.get("heterostructure_principal_strain_B", []))),
        "max_principal_strain": float(info.get(f"{prefix}_max_principal_strain", info.get("heterostructure_max_principal_strain", 0.0))),
        "cartesian_residual": float(info.get(f"{prefix}_cartesian_residual", info.get("heterostructure_cartesian_residual", 0.0))),
        "residual_rotation_deg": float(info.get(f"{prefix}_residual_rotation_deg", info.get("heterostructure_residual_rotation_deg", 0.0))),
        "requested_twist_deg": float(requested_twist_deg),
        "gap": float(gap),
        "strain_mode": str(strain_mode),
        "max_index": int(max_index),
        "estimated_atom_count": int(info.get(f"{prefix}_estimated_atom_count", info.get("heterostructure_estimated_atom_count", len(result)))),
        "final_atom_count": int(len(result)),
    }


def prepare_interface_match(
    region_a,
    region_b,
    *,
    mode=InterfaceMode.ALIGNED,
    requested_twist_deg=0.0,
    max_strain=0.05,
    strain_mode="balanced",
    gap=3.0,
    max_index=3,
    atom_count_limit=DEFAULT_MAX_INTERFACE_ATOMS,
):
    """Compute matched Region source Structures using frozen public Builder APIs.

    This function is widget-free and does not mutate a Device or either Region.
    The shared Builder assembly is deliberately used as the scientific source of
    truth, then split back into the known A/B atom blocks to retain region IDs.
    """
    mode, twist, max_strain, gap, max_index, atoms_a, atoms_b = _validate_match_inputs(
        region_a, region_b, mode=mode, requested_twist_deg=requested_twist_deg,
        max_strain=max_strain, gap=gap, max_index=max_index, atom_count_limit=atom_count_limit,
    )
    normalized_mode = str(strain_mode).strip().lower()
    if normalized_mode not in {"balanced", "bottom", "top"}:
        raise ValueError("Interface strain mode must be balanced, bottom, or top.")
    if mode is InterfaceMode.ALIGNED:
        result = create_heterostructure(
            atoms_a, atoms_b, interlayer_distance=gap, max_index=max_index,
            max_strain=max_strain, strain_mode=normalized_mode, twist_angle=0.0,
            vacuum=0.0, center=True,
        )
    else:
        result = create_moire_structure(
            atoms_a, atoms_b, twist_angle=twist, max_index=max_index,
            max_strain=max_strain, interlayer_distance=gap, vacuum=0.0,
            strain_mode=normalized_mode,
        )
    diagnostics = _builder_metadata(result, mode, twist, gap, max_index, normalized_mode)
    if diagnostics["final_atom_count"] > int(atom_count_limit):
        raise ValueError(
            f"Matched interface contains {diagnostics['final_atom_count']} atoms, exceeding the "
            f"configured safety limit of {atom_count_limit}."
        )
    count_a = diagnostics["determinant_a"] * len(atoms_a)
    count_b = diagnostics["determinant_b"] * len(atoms_b)
    if count_a + count_b != len(result):
        raise RuntimeError("Builder interface result cannot be safely partitioned into Region A and B.")
    layer_a = result[:count_a].copy()
    layer_b = result[count_a:count_a + count_b].copy()
    for layer in (layer_a, layer_b):
        layer.set_cell(result.cell, scale_atoms=False)
        layer.pbc = result.pbc
    native_a = StructureIO.from_ase(layer_a, name=region_a.source_structure.name)
    native_b = StructureIO.from_ase(layer_b, name=region_b.source_structure.name)
    interface = DeviceInterface(
        region_a_id=region_a.id, region_b_id=region_b.id, mode=mode,
        requested_twist_deg=twist, max_strain=max_strain, strain_mode=normalized_mode,
        gap=gap, max_index=max_index, diagnostics=diagnostics,
    )
    return InterfaceMatchResult(interface=interface, source_structure_a=native_a, source_structure_b=native_b)


def apply_interface_match(device, match_result, *, fit_cell_after_match=False):
    """Commit a computed interface result to a Device while preserving region identity."""
    if not isinstance(match_result, InterfaceMatchResult):
        raise TypeError("Expected an InterfaceMatchResult.")
    interface = match_result.interface
    region_a = device.get_region(interface.region_a_id)
    region_b = device.get_region(interface.region_b_id)
    if region_a is None or region_b is None:
        raise ValueError("Interface regions no longer exist in this Device.")
    region_a.source_structure = match_result.source_structure_a.copy()
    region_b.source_structure = match_result.source_structure_b.copy()
    # The frozen Builder assembly has already established common in-plane cells,
    # physical twist, and Z gap. Existing placement transforms must not apply a
    # second rotation or offset to these replacement source structures.
    region_a.translation = (0.0, 0.0, 0.0)
    region_a.rotation = (0.0, 0.0, 0.0)
    region_b.translation = (0.0, 0.0, 0.0)
    region_b.rotation = (0.0, 0.0, 0.0)
    device.replace_interface(interface)
    if fit_cell_after_match:
        fit_device_cell(device, device.padding)
    collisions = detect_inter_region_collisions(device)
    interface.diagnostics["post_match_collision_count"] = len(collisions)
    return interface
