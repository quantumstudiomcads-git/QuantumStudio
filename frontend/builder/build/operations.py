"""
Quantum Studio
Structure Operations

Central structure manipulation backend.

All operations work primarily with ASE Atoms objects.

Implemented operations
----------------------
- supercell
- slab
- vacuum
- strain
- nanotube
- heterostructure
- layered structures
- moire / twisted bilayers
- lattice matching
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

import math
import numpy as np

from ase import Atoms
from ase.build import make_supercell


# ================================================================
# Basic helpers
# ================================================================

def _as_atoms(structure) -> Atoms:
    """
    Convert supported Quantum Studio structure representations
    into an independent ASE Atoms object.

    Accepted inputs:
        1. ASE Atoms
        2. Objects containing ASE Atoms in `.atoms`
        3. Objects containing ASE Atoms in `.ase_atoms`
        4. Native Quantum Studio Structure objects containing
           custom atoms with:
               element, x, y, z
    """

    # --------------------------------------------------------
    # Already ASE
    # --------------------------------------------------------

    if isinstance(structure, Atoms):
        return structure.copy()

    # --------------------------------------------------------
    # Objects wrapping ASE Atoms
    # --------------------------------------------------------

    if hasattr(structure, "atoms"):

        atoms = getattr(
            structure,
            "atoms",
        )

        if isinstance(atoms, Atoms):
            return atoms.copy()

        # ----------------------------------------------------
        # Native Quantum Studio Structure
        #
        # frontend.structure.Structure stores custom Atom
        # objects rather than ASE Atom objects.
        # ----------------------------------------------------

        if isinstance(atoms, (list, tuple)):

            if all(
                hasattr(atom, "element")
                and hasattr(atom, "x")
                and hasattr(atom, "y")
                and hasattr(atom, "z")
                for atom in atoms
            ):

                symbols = [
                    atom.element
                    for atom in atoms
                ]

                positions = [
                    [
                        atom.x,
                        atom.y,
                        atom.z,
                    ]
                    for atom in atoms
                ]

                cell = getattr(
                    structure,
                    "cell",
                    None,
                )

                periodic = getattr(
                    structure,
                    "periodic",
                    [True, True, True],
                )

                return Atoms(
                    symbols=symbols,
                    positions=positions,
                    cell=cell,
                    pbc=periodic,
                )

    # --------------------------------------------------------
    # Explicit ASE wrapper
    # --------------------------------------------------------

    if hasattr(structure, "ase_atoms"):

        atoms = getattr(
            structure,
            "ase_atoms",
        )

        if isinstance(atoms, Atoms):
            return atoms.copy()

    raise TypeError(
        "Expected ASE Atoms or a native Quantum Studio "
        "Structure containing atoms with element/x/y/z."
    )


def _read_structure(path) -> Atoms:
    """
    Read common crystal formats through ASE.
    """

    from ase.io import read

    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"Structure file does not exist:\n{path}"
        )

    atoms = read(
        str(path)
    )

    if not isinstance(atoms, Atoms):
        raise TypeError(
            f"Could not read {path} as an ASE structure."
        )

    return atoms


def _coerce_atoms(structure) -> Atoms:
    """
    Accept either a path or an ASE/Quantum Studio structure.
    """

    if isinstance(structure, (str, Path)):
        return _read_structure(structure)

    return _as_atoms(structure)


def _cell_matrix(atoms: Atoms) -> np.ndarray:

    return np.asarray(
        atoms.cell.array,
        dtype=float,
    )


def _inplane_cell(atoms: Atoms) -> np.ndarray:

    cell = _cell_matrix(atoms)

    return cell[
        :2,
        :2,
    ]


def _inplane_vectors(atoms: Atoms) -> np.ndarray:

    cell = _cell_matrix(atoms)

    return cell[
        :2,
        :2,
    ]


def _rotation_matrix_z(
    angle_deg: float,
) -> np.ndarray:

    theta = np.deg2rad(
        angle_deg
    )

    c = np.cos(theta)
    s = np.sin(theta)

    return np.array(
        [
            [c, -s, 0.0],
            [s, c, 0.0],
            [0.0, 0.0, 1.0],
        ]
    )


def _rotate_atoms_z(
    atoms: Atoms,
    angle_deg: float,
) -> Atoms:

    result = atoms.copy()

    rotation = _rotation_matrix_z(
        angle_deg
    )

    positions = (
        result.get_positions()
        @ rotation.T
    )

    result.set_positions(
        positions
    )

    # Rotate the cell vectors too.
    cell = (
        result.cell.array
        @ rotation.T
    )

    result.set_cell(
        cell,
        scale_atoms=False,
    )

    return result


def _minimum_image_xy_distance(
    atoms: Atoms,
    i: int,
    j: int,
) -> float:

    positions = atoms.get_positions()

    delta = (
        positions[i]
        - positions[j]
    )

    cell = atoms.cell.array

    try:

        fractional = (
            np.linalg.solve(
                cell.T,
                delta,
            )
        )

        fractional[:2] -= np.round(
            fractional[:2]
        )

        delta = (
            fractional
            @ cell
        )

    except np.linalg.LinAlgError:

        pass

    return float(
        np.linalg.norm(
            delta
        )
    )


# ================================================================
# Supercell
# ================================================================

def create_supercell(
    structure,
    nx: int = 1,
    ny: int = 1,
    nz: int = 1,
) -> Atoms:

    atoms = _coerce_atoms(
        structure
    )

    nx = int(nx)
    ny = int(ny)
    nz = int(nz)

    if nx < 1 or ny < 1 or nz < 1:
        raise ValueError(
            "Supercell dimensions must be positive integers."
        )

    return atoms.repeat(
        (
            nx,
            ny,
            nz,
        )
    )


# ================================================================
# Slab
# ================================================================

def create_slab(
    structure,
    repetitions=(1, 1, 1),
    vacuum: float = 10.0,
    axis: int = 2,
) -> Atoms:

    atoms = _coerce_atoms(
        structure
    )

    atoms = atoms.repeat(
        repetitions
    )

    axis = int(axis)

    if axis not in (0, 1, 2):
        raise ValueError(
            "Slab axis must be 0, 1 or 2."
        )

    positions = (
        atoms.get_positions()
    )

    minimum = positions[
        :,
        axis,
    ].min()

    maximum = positions[
        :,
        axis,
    ].max()

    thickness = (
        maximum
        - minimum
    )

    cell = atoms.cell.array.copy()

    vector = cell[
        axis
    ]

    length = np.linalg.norm(
        vector
    )

    if length <= 0:
        raise ValueError(
            "The selected cell vector has zero length."
        )

    new_length = (
        thickness
        + float(vacuum)
    )

    vector = (
        vector / length
    ) * new_length

    cell[
        axis
    ] = vector

    atoms.set_cell(
        cell,
        scale_atoms=False,
    )

    positions = (
        atoms.get_positions()
    )

    center = (
        positions[
            :,
            axis,
        ].min()
        + positions[
            :,
            axis,
        ].max()
    ) / 2.0

    target = (
        new_length / 2.0
    )

    positions[
        :,
        axis,
    ] += (
        target
        - center
    )

    atoms.set_positions(
        positions
    )

    atoms.wrap()

    return atoms


# ================================================================
# Vacuum
# ================================================================

def add_vacuum(
    structure,
    vacuum: float = 10.0,
    axis: int = 2,
) -> Atoms:

    atoms = _coerce_atoms(
        structure
    )

    axis = int(axis)

    if axis not in (0, 1, 2):
        raise ValueError(
            "Vacuum axis must be 0, 1 or 2."
        )

    cell = atoms.cell.array.copy()

    vector = cell[
        axis
    ]

    length = np.linalg.norm(
        vector
    )

    if length <= 0:
        raise ValueError(
            "Selected cell vector has zero length."
        )

    cell[
        axis
    ] = (
        vector
        / length
        * (
            length
            + float(vacuum)
        )
    )

    atoms.set_cell(
        cell,
        scale_atoms=False,
    )

    atoms.center(
        axis=axis
    )

    return atoms


# ================================================================
# Strain
# ================================================================

def apply_strain(
    structure,
    strain_x: float = 0.0,
    strain_y: float = 0.0,
    strain_z: float = 0.0,
    scale_atoms: bool = True,
) -> Atoms:

    atoms = _coerce_atoms(
        structure
    )

    factors = np.array(
        [
            1.0 + float(strain_x),
            1.0 + float(strain_y),
            1.0 + float(strain_z),
        ]
    )

    if np.any(
        factors <= 0
    ):
        raise ValueError(
            "Strain produces a non-positive lattice scale."
        )

    cell = (
        atoms.cell.array
        * factors[:, None]
    )

    atoms.set_cell(
        cell,
        scale_atoms=scale_atoms,
    )

    return atoms


# ================================================================
# Nanotube
# ================================================================

def create_nanotube(
    structure,
    radius: float = 10.0,
    axis: int = 2,
) -> Atoms:
    """
    Generic cylindrical wrapping operation.

    This is intended primarily for 2D sheets.
    """

    atoms = _coerce_atoms(
        structure
    )

    radius = float(radius)

    if radius <= 0:
        raise ValueError(
            "Nanotube radius must be positive."
        )

    positions = (
        atoms.get_positions()
    )

    # Assume the input sheet lies in XY.
    x = positions[:, 0]
    y = positions[:, 1]

    x0 = (
        x.min()
        + x.max()
    ) / 2.0

    width = (
        x.max()
        - x.min()
    )

    if width <= 0:
        raise ValueError(
            "Cannot wrap a structure with zero width."
        )

    theta = (
        x - x0
    ) / width * (
        2.0 * np.pi
    )

    new_positions = (
        positions.copy()
    )

    new_positions[:, 0] = (
        radius
        * np.cos(theta)
    )

    new_positions[:, 1] = (
        radius
        * np.sin(theta)
    )

    atoms.set_positions(
        new_positions
    )

    # Approximate circumference as periodic direction.
    cell = atoms.cell.array.copy()

    cell[0] = np.array(
        [
            2.0 * np.pi * radius,
            0.0,
            0.0,
        ]
    )

    atoms.set_cell(
        cell,
        scale_atoms=False,
    )

    return atoms


# ================================================================
# Layered structure
# ================================================================

def create_layered_structure(
    layers: Sequence,
    interlayer_distance: float = 3.4,
    stacking: str = "AA",
) -> Atoms:
    """
    Stack several structures along z.

    Each layer may be:
        ASE Atoms
        Quantum Studio structure
        filename
    """

    if not layers:
        raise ValueError(
            "At least one layer is required."
        )

    layer_atoms = [
        _coerce_atoms(layer)
        for layer in layers
    ]

    result = None

    current_z = 0.0

    for index, layer in enumerate(
        layer_atoms
    ):

        layer = layer.copy()

        layer.center(
            axis=2
        )

        positions = (
            layer.get_positions()
        )

        zmin = positions[
            :,
            2,
        ].min()

        zmax = positions[
            :,
            2,
        ].max()

        thickness = (
            zmax
            - zmin
        )

        shift = (
            current_z
            - zmin
        )

        # Basic stacking variants.
        if stacking.upper() == "AB":
            if index % 2 == 1:
                cell = layer.cell.array

                shift_xy = (
                    0.5 * cell[0]
                    + 0.5 * cell[1]
                )

                layer.translate(
                    shift_xy
                )

        layer.translate(
            (
                0.0,
                0.0,
                shift,
            )
        )

        if result is None:

            result = layer.copy()

        else:

            result += layer

        current_z += (
            thickness
            + float(interlayer_distance)
        )

    result.center(
        axis=2
    )

    return result


# ================================================================
# 2D lattice matching
# ================================================================

@dataclass
class LatticeMatch:

    matrix_a: np.ndarray
    matrix_b: np.ndarray
    angle_deg: float
    mismatch: float
    strain_a: float
    strain_b: float
    score: float
    # Additive diagnostics: the original fields above remain the public
    # compatibility contract consumed by the existing Build-tab code.
    principal_strains_a: Optional[np.ndarray] = None
    principal_strains_b: Optional[np.ndarray] = None
    max_principal_strain: float = 0.0
    cartesian_residual: float = 0.0
    residual_rotation_deg: float = 0.0
    target_cell_2d: Optional[np.ndarray] = None
    determinant_a: int = 1
    determinant_b: int = 1
    estimated_atom_count: int = 0


@dataclass(frozen=True)
class _CachedHnfCandidate:

    matrix: np.ndarray
    determinant: int
    cell: np.ndarray
    area: float
    lengths: np.ndarray
    internal_angle_deg: float
    metric: np.ndarray
    aspect_ratio: float


@dataclass
class _LatticeMatchSearchStatistics:

    hnf_candidates: int = 0
    local_integer_candidates: int = 0
    unique_matrix_pairs: int = 0
    prefilter_survivors: int = 0
    full_diagnostic_evaluations: int = 0


@dataclass(frozen=True)
class _PolarStrainDiagnostics:

    rotation_matrix: np.ndarray
    rotation_deg: float
    stretch_tensor: np.ndarray
    principal_stretches: np.ndarray
    principal_strains: np.ndarray
    max_abs_strain: float


@dataclass(frozen=True)
class _CartesianMatchDiagnostics:

    cell_a: np.ndarray
    cell_b: np.ndarray
    cartesian_residual: float
    metric_residual: float
    area_a: float
    area_b: float
    atom_multiplier_a: int
    atom_multiplier_b: int
    atom_count: int
    deformation_a_to_b: np.ndarray
    deformation_b_to_a: np.ndarray
    strain_a_to_b: _PolarStrainDiagnostics
    strain_b_to_a: _PolarStrainDiagnostics
    residual_rotation_deg: float


def _validate_planar_2d_lattice(
    lattice: np.ndarray,
    *,
    name: str,
) -> np.ndarray:
    """Validate and return a finite, nonsingular Cartesian 2D basis."""

    result = np.asarray(
        lattice,
        dtype=float,
    )

    if result.shape != (2, 2):

        raise ValueError(
            f"{name} must have shape (2, 2)."
        )

    if not np.all(np.isfinite(result)):

        raise ValueError(
            f"{name} must contain only finite values."
        )

    determinant = float(
        np.linalg.det(result)
    )

    if abs(determinant) <= 1e-12:

        raise ValueError(
            f"{name} is singular."
        )

    return result.copy()


def _extract_planar_2d_cell(
    atoms: Atoms,
    *,
    z_tolerance: float = 1e-10,
) -> np.ndarray:
    """Extract a validated XY row-vector basis from an ASE cell."""

    cell = np.asarray(
        atoms.cell.array,
        dtype=float,
    )

    if cell.shape != (3, 3):

        raise ValueError(
            "ASE cells must have shape (3, 3)."
        )

    if not np.all(np.isfinite(cell)):

        raise ValueError(
            "ASE cell must contain only finite values."
        )

    if not np.allclose(
        cell[:2, 2],
        0.0,
        atol=float(z_tolerance),
        rtol=0.0,
    ):

        raise ValueError(
            "Only planar XY lattices are supported; the first two "
            "cell vectors have non-negligible Z components."
        )

    return _validate_planar_2d_lattice(
        cell[:2, :2],
        name="Projected in-plane lattice",
    )


def _enumerate_row_hnf_2d(
    max_determinant: int,
) -> list[np.ndarray]:
    """Enumerate canonical positive-determinant row-HNF matrices."""

    max_determinant = int(max_determinant)

    if max_determinant < 1:

        raise ValueError(
            "max_determinant must be at least 1."
        )

    matrices = []

    for determinant in range(
        1,
        max_determinant + 1,
    ):

        for a in range(
            1,
            determinant + 1,
        ):

            if determinant % a != 0:
                continue

            d = determinant // a

            for b in range(d):

                matrices.append(
                    np.array(
                        [
                            [a, b],
                            [0, d],
                        ],
                        dtype=int,
                    )
                )

    return matrices


def _nearest_integer_stable(
    value: float,
) -> int:
    """Round to nearest integer, resolving exact half ties toward zero."""

    floor_value = math.floor(value)
    fraction = value - floor_value

    if abs(fraction - 0.5) <= 1e-12:
        return int(math.trunc(value))

    return int(math.floor(value + 0.5))


def _reduce_2d_row_basis(
    basis: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Deterministically Gauss-reduce a row-vector 2D lattice basis."""

    original = _validate_planar_2d_lattice(
        basis,
        name="2D lattice basis",
    )

    reduced = original.copy()
    transform = np.eye(
        2,
        dtype=int,
    )
    tolerance = 1e-12

    for _ in range(100):

        length_0 = float(
            np.dot(reduced[0], reduced[0])
        )
        length_1 = float(
            np.dot(reduced[1], reduced[1])
        )

        if length_1 + tolerance < length_0:

            update = np.array(
                [
                    [0, 1],
                    [-1, 0],
                ],
                dtype=int,
            )

            reduced = update @ reduced
            transform = update @ transform
            continue

        coefficient = _nearest_integer_stable(
            float(
                np.dot(reduced[0], reduced[1])
                / length_0
            )
        )

        if coefficient == 0:
            break

        update = np.array(
            [
                [1, 0],
                [-coefficient, 1],
            ],
            dtype=int,
        )

        reduced = update @ reduced
        transform = update @ transform

    else:

        raise RuntimeError(
            "2D basis reduction did not converge."
        )

    for component in reduced[0]:

        if abs(component) <= tolerance:
            continue

        if component < 0.0:

            update = -np.eye(
                2,
                dtype=int,
            )

            reduced = update @ reduced
            transform = update @ transform

        break

    return reduced, transform


def _validate_integer_supercell_matrix(
    matrix: np.ndarray,
    *,
    name: str,
) -> tuple[np.ndarray, int]:
    """Validate a positive-determinant 2D integer row transform."""

    values = np.asarray(matrix)

    if values.shape != (2, 2):

        raise ValueError(
            f"{name} must have shape (2, 2)."
        )

    if not np.all(np.isfinite(values)):

        raise ValueError(
            f"{name} must contain only finite values."
        )

    rounded = np.rint(values)

    if not np.array_equal(values, rounded):

        raise ValueError(
            f"{name} must contain integer values."
        )

    result = rounded.astype(
        int,
        copy=False,
    )

    determinant = int(
        result[0, 0] * result[1, 1]
        - result[0, 1] * result[1, 0]
    )

    if determinant <= 0:

        raise ValueError(
            f"{name} must have positive determinant."
        )

    return result.copy(), determinant


def _rotation_matrix_2d(
    angle_deg: float,
) -> np.ndarray:
    """Return the Cartesian column-vector rotation matrix about +Z."""

    theta = np.deg2rad(
        float(angle_deg)
    )
    cosine = np.cos(theta)
    sine = np.sin(theta)

    return np.array(
        [
            [cosine, -sine],
            [sine, cosine],
        ]
    )


def _rotate_planar_lattice(
    lattice: np.ndarray,
    angle_deg: float,
) -> np.ndarray:
    """Rotate a row-vector lattice in Cartesian XY coordinates."""

    basis = _validate_planar_2d_lattice(
        lattice,
        name="Planar lattice",
    )

    return basis @ _rotation_matrix_2d(
        angle_deg
    ).T


def _cartesian_supercell_2d(
    lattice: np.ndarray,
    matrix: np.ndarray,
) -> tuple[np.ndarray, int]:
    """Build a Cartesian row-vector supercell from an integer transform."""

    basis = _validate_planar_2d_lattice(
        lattice,
        name="Planar lattice",
    )
    transform, determinant = _validate_integer_supercell_matrix(
        matrix,
        name="Supercell transformation",
    )

    return transform @ basis, determinant


def _deformation_gradient_2d(
    source: np.ndarray,
    target: np.ndarray,
) -> np.ndarray:
    """Return F satisfying source @ F.T == target for row-vector cells."""

    source_basis = _validate_planar_2d_lattice(
        source,
        name="Source lattice",
    )
    target_basis = _validate_planar_2d_lattice(
        target,
        name="Target lattice",
    )

    return np.linalg.solve(
        source_basis,
        target_basis,
    ).T


def _polar_strain_diagnostics(
    deformation: np.ndarray,
) -> _PolarStrainDiagnostics:
    """Separate a proper in-plane rotation from the stretch tensor."""

    F = np.asarray(
        deformation,
        dtype=float,
    )

    if F.shape != (2, 2):

        raise ValueError(
            "Deformation gradient must have shape (2, 2)."
        )

    if not np.all(np.isfinite(F)):

        raise ValueError(
            "Deformation gradient must contain only finite values."
        )

    if np.linalg.det(F) <= 0.0:

        raise ValueError(
            "Deformation gradient must preserve orientation."
        )

    left, singular_values, right_t = np.linalg.svd(F)
    rotation = left @ right_t

    if np.linalg.det(rotation) <= 0.0:

        raise ValueError(
            "Polar decomposition produced an improper rotation."
        )

    stretch = (
        right_t.T
        @ np.diag(singular_values)
        @ right_t
    )
    principal_stretches = np.linalg.eigvalsh(
        stretch
    )
    principal_strains = principal_stretches - 1.0
    rotation_deg = float(
        np.rad2deg(
            np.arctan2(
                rotation[1, 0],
                rotation[0, 0],
            )
        )
    )

    return _PolarStrainDiagnostics(
        rotation_matrix=rotation,
        rotation_deg=rotation_deg,
        stretch_tensor=stretch,
        principal_stretches=principal_stretches,
        principal_strains=principal_strains,
        max_abs_strain=float(
            np.max(np.abs(principal_strains))
        ),
    )


def _cartesian_match_diagnostics(
    lattice_a: np.ndarray,
    lattice_b: np.ndarray,
    matrix_a: np.ndarray,
    matrix_b: np.ndarray,
    *,
    rotation_deg: float = 0.0,
    atoms_a: int = 1,
    atoms_b: int = 1,
) -> _CartesianMatchDiagnostics:
    """Diagnose a candidate using Cartesian cells, not metric equality."""

    atoms_a = int(atoms_a)
    atoms_b = int(atoms_b)

    if atoms_a < 1 or atoms_b < 1:

        raise ValueError(
            "atoms_a and atoms_b must be positive integers."
        )

    cell_a, determinant_a = _cartesian_supercell_2d(
        lattice_a,
        matrix_a,
    )
    rotated_b = _rotate_planar_lattice(
        lattice_b,
        rotation_deg,
    )
    cell_b, determinant_b = _cartesian_supercell_2d(
        rotated_b,
        matrix_b,
    )

    scale = max(
        float(np.linalg.norm(cell_a)),
        float(np.linalg.norm(cell_b)),
        1e-12,
    )
    cartesian_residual = float(
        np.linalg.norm(cell_a - cell_b) / scale
    )
    metric_a = _cell_metric(cell_a)
    metric_b = _cell_metric(cell_b)
    metric_residual = _metric_error(
        metric_a,
        metric_b,
    )
    deformation_a_to_b = _deformation_gradient_2d(
        cell_a,
        cell_b,
    )
    deformation_b_to_a = _deformation_gradient_2d(
        cell_b,
        cell_a,
    )
    strain_a_to_b = _polar_strain_diagnostics(
        deformation_a_to_b,
    )
    strain_b_to_a = _polar_strain_diagnostics(
        deformation_b_to_a,
    )

    return _CartesianMatchDiagnostics(
        cell_a=cell_a,
        cell_b=cell_b,
        cartesian_residual=cartesian_residual,
        metric_residual=metric_residual,
        area_a=abs(float(np.linalg.det(cell_a))),
        area_b=abs(float(np.linalg.det(cell_b))),
        atom_multiplier_a=determinant_a,
        atom_multiplier_b=determinant_b,
        atom_count=(
            atoms_a * determinant_a
            + atoms_b * determinant_b
        ),
        deformation_a_to_b=deformation_a_to_b,
        deformation_b_to_a=deformation_b_to_a,
        strain_a_to_b=strain_a_to_b,
        strain_b_to_a=strain_b_to_a,
        residual_rotation_deg=strain_a_to_b.rotation_deg,
    )


def _candidate_rank_key(
    diagnostics: _CartesianMatchDiagnostics,
    matrix_a: np.ndarray,
    matrix_b: np.ndarray,
) -> tuple:
    """Return a stable ranking tuple for otherwise feasible candidates."""

    transform_a, determinant_a = _validate_integer_supercell_matrix(
        matrix_a,
        name="Matrix A",
    )
    transform_b, determinant_b = _validate_integer_supercell_matrix(
        matrix_b,
        name="Matrix B",
    )

    return (
        round(
            max(
                diagnostics.strain_a_to_b.max_abs_strain,
                diagnostics.strain_b_to_a.max_abs_strain,
            ),
            14,
        ),
        round(diagnostics.cartesian_residual, 14),
        round(abs(diagnostics.residual_rotation_deg), 12),
        diagnostics.atom_count,
        round(max(diagnostics.area_a, diagnostics.area_b), 12),
        determinant_a,
        determinant_b,
        tuple(transform_a.flatten()),
        tuple(transform_b.flatten()),
    )


def _supercell_2d_matrix(
    atoms: Atoms,
    matrix2x2: np.ndarray,
) -> np.ndarray:
    """
    Convert a 2x2 in-plane supercell matrix to a 3x3 ASE matrix.
    """

    matrix2x2 = np.asarray(
        matrix2x2,
        dtype=int,
    )

    P = np.eye(
        3,
        dtype=int,
    )

    P[
        :2,
        :2
    ] = matrix2x2

    return P


def _lattice_from_2d_matrix(
    atoms: Atoms,
    matrix2x2: np.ndarray,
) -> np.ndarray:

    cell = atoms.cell.array

    # ASE uses row vectors.
    return (
        matrix2x2
        @ cell[:2, :]
    )


def _cell_metric(
    vectors: np.ndarray,
) -> np.ndarray:

    return (
        vectors
        @ vectors.T
    )


def _metric_error(
    A: np.ndarray,
    B: np.ndarray,
) -> float:

    scale = max(
        np.linalg.norm(A),
        np.linalg.norm(B),
        1e-12,
    )

    return float(
        np.linalg.norm(
            A - B
        )
        / scale
    )


def _integer_det_2d(
    matrix: np.ndarray,
) -> int:
    """Return the exact determinant of a 2-by-2 integer matrix."""

    values = np.asarray(matrix, dtype=int)

    if values.shape != (2, 2):
        raise ValueError("Integer matrix must have shape (2, 2).")

    return int(
        values[0, 0] * values[1, 1]
        - values[0, 1] * values[1, 0]
    )


def _cached_2d_candidate(
    lattice: np.ndarray,
    matrix: np.ndarray,
    cache: dict[tuple[int, int, int, int], _CachedHnfCandidate],
) -> _CachedHnfCandidate:
    """Build and cache immutable geometric invariants for one matrix."""

    transform, determinant = _validate_integer_supercell_matrix(
        matrix,
        name="Supercell transformation",
    )
    key = tuple(int(value) for value in transform.flatten())
    cached = cache.get(key)

    if cached is not None:
        return cached

    cell = transform @ lattice
    lengths = np.linalg.norm(cell, axis=1)

    if (
        not np.all(np.isfinite(cell))
        or not np.all(np.isfinite(lengths))
        or np.any(lengths <= 1e-12)
    ):
        raise ValueError("Candidate supercell is non-finite or degenerate.")

    cosine = np.clip(
        float(np.dot(cell[0], cell[1]) / (lengths[0] * lengths[1])),
        -1.0,
        1.0,
    )
    angle = float(np.rad2deg(np.arccos(cosine)))
    area = abs(float(np.linalg.det(cell)))

    if not np.isfinite(area) or area <= 1e-12:
        raise ValueError("Candidate supercell is degenerate.")

    cached = _CachedHnfCandidate(
        matrix=transform,
        determinant=determinant,
        cell=cell,
        area=area,
        lengths=lengths,
        internal_angle_deg=angle,
        metric=_cell_metric(cell),
        aspect_ratio=float(max(lengths) / min(lengths)),
    )
    cache[key] = cached
    return cached


def _candidate_passes_prefilters(
    candidate_a: _CachedHnfCandidate,
    candidate_b: _CachedHnfCandidate,
    *,
    max_strain: float,
) -> bool:
    """Reject geometrically implausible candidates before polar diagnostics."""

    safe_strain = max(float(max_strain), 0.0)
    relative_limit = (1.0 + safe_strain) / max(1.0 - safe_strain, 1e-12)

    area_ratio = max(candidate_a.area, candidate_b.area) / min(
        candidate_a.area,
        candidate_b.area,
    )
    if area_ratio > 1.01 * relative_limit**2:
        return False

    lengths_a = np.sort(candidate_a.lengths)
    lengths_b = np.sort(candidate_b.lengths)
    length_ratios = np.maximum(lengths_a / lengths_b, lengths_b / lengths_a)
    if np.any(length_ratios > 1.005 * relative_limit):
        return False

    aspect_ratio = max(
        candidate_a.aspect_ratio / candidate_b.aspect_ratio,
        candidate_b.aspect_ratio / candidate_a.aspect_ratio,
    )
    if aspect_ratio > 1.01 * relative_limit**2:
        return False

    metric_error = _metric_error(candidate_a.metric, candidate_b.metric)
    return metric_error <= max(1e-8, 3.0 * safe_strain + 0.005)


def _sqrt_symmetric_positive_2d(
    matrix: np.ndarray,
) -> np.ndarray:
    """Return the positive square root of a symmetric positive 2D tensor."""

    symmetric = 0.5 * (np.asarray(matrix, dtype=float) + np.asarray(matrix, dtype=float).T)
    eigenvalues, eigenvectors = np.linalg.eigh(symmetric)

    if np.any(eigenvalues <= 0.0) or not np.all(np.isfinite(eigenvalues)):
        raise ValueError("Stretch tensor must be positive definite.")

    return eigenvectors @ np.diag(np.sqrt(eigenvalues)) @ eigenvectors.T


def _target_and_strain_diagnostics(
    cell_a: np.ndarray,
    cell_b: np.ndarray,
    *,
    strain_mode: str,
    residual_rotation_limit_deg: float,
) -> tuple[np.ndarray, _PolarStrainDiagnostics, _PolarStrainDiagnostics, float]:
    """Build a physical common cell and independently diagnose both layers."""

    mode = str(strain_mode).strip().lower()
    relative = _polar_strain_diagnostics(
        _deformation_gradient_2d(cell_a, cell_b),
    )
    residual_rotation = abs(float(relative.rotation_deg))

    if residual_rotation > float(residual_rotation_limit_deg):
        raise ValueError(
            "Candidate requires a hidden rigid rotation of "
            f"{residual_rotation:.6f} degrees."
        )

    if mode == "bottom":
        target = cell_b.copy()
    elif mode == "top":
        target = cell_a.copy()
    elif mode == "balanced":
        sqrt_stretch = _sqrt_symmetric_positive_2d(relative.stretch_tensor)
        # Row-vector convention: target = cell_a @ F_a.T.  The positive
        # stretch tensor is symmetric, so sqrt(U).T is written explicitly.
        target = cell_a @ sqrt_stretch.T
    else:
        raise ValueError("strain_mode must be 'balanced', 'bottom' or 'top'.")

    strain_a = _polar_strain_diagnostics(
        _deformation_gradient_2d(cell_a, target),
    )
    strain_b = _polar_strain_diagnostics(
        _deformation_gradient_2d(cell_b, target),
    )

    return target, strain_a, strain_b, residual_rotation


def _candidate_rank_key(
    diagnostics: _CartesianMatchDiagnostics,
    matrix_a: np.ndarray,
    matrix_b: np.ndarray,
    *,
    max_principal_strain: Optional[float] = None,
    residual_rotation_deg: Optional[float] = None,
    physical_area: Optional[float] = None,
) -> tuple:
    """Return a stable lexicographic key for feasible Cartesian matches."""

    transform_a, determinant_a = _validate_integer_supercell_matrix(
        matrix_a,
        name="Matrix A",
    )
    transform_b, determinant_b = _validate_integer_supercell_matrix(
        matrix_b,
        name="Matrix B",
    )

    if max_principal_strain is None:
        max_principal_strain = max(
            diagnostics.strain_a_to_b.max_abs_strain,
            diagnostics.strain_b_to_a.max_abs_strain,
        )
    if residual_rotation_deg is None:
        residual_rotation_deg = diagnostics.residual_rotation_deg
    if physical_area is None:
        physical_area = max(diagnostics.area_a, diagnostics.area_b)

    identity = np.eye(2, dtype=int)
    identity_a = np.array_equal(transform_a, identity)
    identity_b = np.array_equal(transform_b, identity)
    identity_penalty = 0 if identity_a and identity_b else 1 if identity_a or identity_b else 2

    return (
        round(float(max_principal_strain), 12),
        round(abs(float(residual_rotation_deg)), 10),
        round(float(diagnostics.cartesian_residual), 12),
        int(diagnostics.atom_count),
        int(determinant_a + determinant_b),
        round(float(physical_area), 10),
        identity_penalty,
        tuple(int(value) for value in transform_a.flatten()),
        tuple(int(value) for value in transform_b.flatten()),
    )


def _find_best_2d_match_with_statistics(
    structure_a,
    structure_b,
    max_index: int = 6,
    max_strain: float = 0.05,
    target_angle_deg: float = 0.0,
    *,
    strain_mode: str = "balanced",
    residual_rotation_limit_deg: float = 0.05,
) -> tuple[LatticeMatch, _LatticeMatchSearchStatistics]:
    """Find a deterministic orientation-aware 2D match without pair products."""

    if int(max_index) < 1:
        raise ValueError("max_index must be at least 1.")
    if float(max_strain) < 0.0:
        raise ValueError("max_strain must be non-negative.")

    A_atoms = _coerce_atoms(structure_a)
    B_atoms = _coerce_atoms(structure_b)
    lattice_a = _extract_planar_2d_cell(A_atoms)
    lattice_b = _rotate_planar_lattice(
        _extract_planar_2d_cell(B_atoms),
        float(target_angle_deg),
    )

    if np.linalg.det(lattice_a) <= 0.0:
        raise ValueError("Layer A has a left-handed projected in-plane lattice.")
    if np.linalg.det(lattice_b) <= 0.0:
        raise ValueError("Layer B has a left-handed projected in-plane lattice.")

    mode = str(strain_mode).strip().lower()
    if mode not in {"balanced", "bottom", "top"}:
        raise ValueError("strain_mode must be 'balanced', 'bottom' or 'top'.")

    determinant_cap = int(max_index) ** 2
    hnfs = _enumerate_row_hnf_2d(determinant_cap)
    statistics = _LatticeMatchSearchStatistics(hnf_candidates=len(hnfs))

    # A zero-strain, zero-residual primitive identity match is globally optimal
    # under the documented rank order.  Resolve it before local enumeration so
    # the common same-lattice GUI path never pays for a larger search budget.
    identity = np.eye(2, dtype=int)
    identity_diagnostics = _cartesian_match_diagnostics(
        lattice_a,
        lattice_b,
        identity,
        identity,
        atoms_a=len(A_atoms),
        atoms_b=len(B_atoms),
    )
    try:
        identity_target, identity_strain_a, identity_strain_b, identity_rotation = (
            _target_and_strain_diagnostics(
                identity_diagnostics.cell_a,
                identity_diagnostics.cell_b,
                strain_mode=mode,
                residual_rotation_limit_deg=residual_rotation_limit_deg,
            )
        )
    except ValueError:
        identity_target = None
    else:
        identity_max_strain = max(
            identity_strain_a.max_abs_strain,
            identity_strain_b.max_abs_strain,
        )
        if (
            identity_diagnostics.cartesian_residual <= 1e-12
            and identity_rotation <= 1e-12
            and identity_max_strain <= 1e-12
        ):
            statistics.unique_matrix_pairs = 1
            statistics.prefilter_survivors = 1
            statistics.full_diagnostic_evaluations = 1
            return LatticeMatch(
                matrix_a=identity.copy(),
                matrix_b=identity.copy(),
                angle_deg=float(target_angle_deg),
                mismatch=0.0,
                strain_a=0.0,
                strain_b=0.0,
                score=float(0.002 * identity_diagnostics.atom_count),
                principal_strains_a=identity_strain_a.principal_strains.copy(),
                principal_strains_b=identity_strain_b.principal_strains.copy(),
                max_principal_strain=0.0,
                cartesian_residual=0.0,
                residual_rotation_deg=0.0,
                target_cell_2d=identity_target.copy(),
                determinant_a=1,
                determinant_b=1,
                estimated_atom_count=int(identity_diagnostics.atom_count),
            ), statistics

    cache_a: dict[tuple[int, int, int, int], _CachedHnfCandidate] = {}
    cache_b: dict[tuple[int, int, int, int], _CachedHnfCandidate] = {}
    hnf_a = [_cached_2d_candidate(lattice_a, matrix, cache_a) for matrix in hnfs]
    hnf_b = [_cached_2d_candidate(lattice_b, matrix, cache_b) for matrix in hnfs]
    inverse_a = np.linalg.inv(lattice_a)
    inverse_b = np.linalg.inv(lattice_b)
    pairs: dict[tuple[int, ...], tuple[np.ndarray, np.ndarray]] = {}

    # The 3^4 permitted local perturbations are fixed.  Vectorizing their
    # determinant screen retains the exact bounded neighbourhood while keeping
    # the GUI-path loop small and allocation-light.
    local_deltas = (
        np.indices((3, 3, 3, 3), dtype=int)
        .reshape(4, -1)
        .T.reshape(-1, 2, 2)
        - 1
    )

    def collect_pairs(
        sources: list[_CachedHnfCandidate],
        inverse_other: np.ndarray,
        *,
        source_is_a: bool,
    ) -> None:
        for source in sources:
            inferred = source.cell @ inverse_other
            rounded = np.array(
                [[_nearest_integer_stable(value) for value in row] for row in inferred],
                dtype=int,
            )
            others = rounded[np.newaxis, :, :] + local_deltas
            determinants = (
                others[:, 0, 0] * others[:, 1, 1]
                - others[:, 0, 1] * others[:, 1, 0]
            )
            statistics.local_integer_candidates += len(others)
            valid = others[(determinants > 0) & (determinants <= determinant_cap)]
            for other in valid:
                if source_is_a:
                    matrix_a, matrix_b = source.matrix, other
                else:
                    matrix_a, matrix_b = other, source.matrix
                key = tuple(int(value) for value in matrix_a.flatten()) + tuple(
                    int(value) for value in matrix_b.flatten()
                )
                pairs.setdefault(key, (matrix_a.copy(), matrix_b.copy()))

    collect_pairs(hnf_a, inverse_b, source_is_a=True)
    collect_pairs(hnf_b, inverse_a, source_is_a=False)
    statistics.unique_matrix_pairs = len(pairs)

    best: Optional[tuple[tuple, LatticeMatch]] = None
    for matrix_a, matrix_b in pairs.values():
        try:
            candidate_a = _cached_2d_candidate(lattice_a, matrix_a, cache_a)
            candidate_b = _cached_2d_candidate(lattice_b, matrix_b, cache_b)
        except ValueError:
            continue

        if not _candidate_passes_prefilters(
            candidate_a,
            candidate_b,
            max_strain=float(max_strain),
        ):
            continue
        statistics.prefilter_survivors += 1
        statistics.full_diagnostic_evaluations += 1

        diagnostics = _cartesian_match_diagnostics(
            lattice_a,
            lattice_b,
            matrix_a,
            matrix_b,
            atoms_a=len(A_atoms),
            atoms_b=len(B_atoms),
        )

        try:
            target, strain_a, strain_b, residual_rotation = _target_and_strain_diagnostics(
                diagnostics.cell_a,
                diagnostics.cell_b,
                strain_mode=mode,
                residual_rotation_limit_deg=residual_rotation_limit_deg,
            )
        except ValueError:
            continue

        max_principal = max(strain_a.max_abs_strain, strain_b.max_abs_strain)
        if max_principal > float(max_strain) + 1e-12:
            continue

        rank = _candidate_rank_key(
            diagnostics,
            matrix_a,
            matrix_b,
            max_principal_strain=max_principal,
            residual_rotation_deg=residual_rotation,
            physical_area=max(diagnostics.area_a, diagnostics.area_b),
        )
        score = float(
            max_principal
            + abs(residual_rotation) / 180.0
            + diagnostics.cartesian_residual
            + 0.002 * diagnostics.atom_count
        )
        match = LatticeMatch(
            matrix_a=np.asarray(matrix_a, dtype=int).copy(),
            matrix_b=np.asarray(matrix_b, dtype=int).copy(),
            angle_deg=float(target_angle_deg),
            mismatch=float(diagnostics.cartesian_residual),
            strain_a=float(strain_a.max_abs_strain),
            strain_b=float(strain_b.max_abs_strain),
            score=score,
            principal_strains_a=strain_a.principal_strains.copy(),
            principal_strains_b=strain_b.principal_strains.copy(),
            max_principal_strain=float(max_principal),
            cartesian_residual=float(diagnostics.cartesian_residual),
            residual_rotation_deg=float(residual_rotation),
            target_cell_2d=target.copy(),
            determinant_a=candidate_a.determinant,
            determinant_b=candidate_b.determinant,
            estimated_atom_count=int(diagnostics.atom_count),
        )

        if best is None or rank < best[0]:
            best = (rank, match)

    if best is None:
        raise RuntimeError(
            "No commensurate orientation-preserving 2D lattice match was found "
            f"within max_index={max_index} and max_strain={max_strain:.3f}."
        )

    return best[1], statistics


def find_best_2d_match(
    structure_a,
    structure_b,
    max_index: int = 6,
    max_strain: float = 0.05,
    target_angle_deg: float = 0.0,
) -> LatticeMatch:
    """Return the best balanced-strain orientation-aware 2D lattice match.

    Inputs are Cartesian row-vector planar lattices.  ``target_angle_deg``
    rotates B as ``B @ R(theta).T`` before candidate generation.
    """

    match, _statistics = _find_best_2d_match_with_statistics(
        structure_a,
        structure_b,
        max_index=max_index,
        max_strain=max_strain,
        target_angle_deg=target_angle_deg,
        strain_mode="balanced",
    )
    return match


# ================================================================
# Apply 2D supercell
# ================================================================

def _make_2d_supercell(
    atoms: Atoms,
    matrix2x2: np.ndarray,
) -> Atoms:

    P = _supercell_2d_matrix(
        atoms,
        matrix2x2,
    )

    return make_supercell(
        atoms,
        P,
    )


# ================================================================
# Apply in-plane strain
# ================================================================

def _apply_2d_lattice_target(
    atoms: Atoms,
    target_cell_xy: np.ndarray,
) -> Atoms:

    result = atoms.copy()

    old_cell = (
        result.cell.array.copy()
    )

    target_cell_xy = np.asarray(
        target_cell_xy,
        dtype=float,
    )

    if target_cell_xy.shape != (2, 3):

        raise ValueError(
            "target_cell_xy must contain two full Cartesian "
            "in-plane lattice vectors with shape (2, 3)."
        )

    if not np.all(np.isfinite(target_cell_xy)):

        raise ValueError(
            "target_cell_xy must contain only finite values."
        )

    xy_tolerance = 1e-10

    if not np.allclose(
        target_cell_xy[:, 2],
        0.0,
        atol=xy_tolerance,
        rtol=0.0,
    ):

        raise ValueError(
            "target_cell_xy must be planar in XY; its in-plane "
            "lattice vectors have non-negligible Z components."
        )

    if not np.allclose(
        old_cell[:2, 2],
        0.0,
        atol=xy_tolerance,
        rtol=0.0,
    ):

        raise ValueError(
            "The existing in-plane lattice vectors must be planar "
            "in XY; non-negligible Z components were found."
        )

    old_xy = old_cell[
        :2,
        :2,
    ]

    new_xy = target_cell_xy[
        :2,
        :2,
    ]

    old_determinant = np.linalg.det(old_xy)

    if not np.isfinite(old_determinant) or abs(old_determinant) <= 1e-12:

        raise ValueError(
            "The existing projected 2D lattice is singular and "
            "cannot be deformed."
        )

    target_determinant = np.linalg.det(new_xy)

    if not np.isfinite(target_determinant) or abs(target_determinant) <= 1e-12:

        raise ValueError(
            "The target projected 2D lattice is singular and "
            "cannot be applied."
        )

    # Transformation F satisfying:
    #
    #     old_xy @ F.T = new_xy
    #
    F2 = np.linalg.solve(
        old_xy,
        new_xy,
    ).T

    F = np.eye(
        3
    )

    F[
        :2,
        :2
    ] = F2

    positions = (
        result.get_positions()
        @ F.T
    )

    cell = (
        old_cell
        @ F.T
    )

    result.set_cell(
        cell,
        scale_atoms=False,
    )

    result.set_positions(
        positions
    )

    return result


# ================================================================
# Heterostructure
# ================================================================

def _create_commensurate_bilayer(
    structure_a,
    structure_b,
    interlayer_distance: float = 3.4,
    max_index: int = 6,
    max_strain: float = 0.05,
    strain_mode: str = "balanced",
    twist_angle: float = 0.0,
    vacuum: float = 15.0,
    center: bool = True,
    *,
    residual_rotation_limit_deg: float = 0.05,
) -> tuple[Atoms, LatticeMatch, _LatticeMatchSearchStatistics]:
    """
    Construct a commensurate two-layer heterostructure.

    Parameters
    ----------
    structure_a
        Bottom layer.

    structure_b
        Top layer.

    interlayer_distance
        Vertical separation between the outermost atomic planes.

    max_index
        Maximum integer supercell search index.

    max_strain
        Maximum allowed absolute in-plane strain.

    strain_mode
        balanced
        bottom
        top

    twist_angle
        Rotation of layer B around z before matching.

    vacuum
        Vacuum added along z.

    Returns
    -------
    ASE Atoms
    """

    A = _coerce_atoms(
        structure_a
    )

    B = _coerce_atoms(
        structure_b
    )

    if (
        len(A) == 0
        or len(B) == 0
    ):

        raise ValueError(
            "Both heterostructure layers must contain atoms."
        )

    # ------------------------------------------------------------
    # Validate requested in-plane strain distribution and find a
    # commensurate Cartesian target.  The matcher applies B_theta to its
    # lattice calculation; atoms are rotated exactly once below.
    # ------------------------------------------------------------

    mode = str(strain_mode).strip().lower()
    if mode not in {"balanced", "bottom", "top"}:
        raise ValueError("strain_mode must be 'balanced', 'bottom' or 'top'.")

    match, _search_statistics = _find_best_2d_match_with_statistics(
        A,
        B,
        max_index=max_index,
        max_strain=max_strain,
        target_angle_deg=twist_angle,
        strain_mode=mode,
        residual_rotation_limit_deg=residual_rotation_limit_deg,
    )

    # ------------------------------------------------------------
    # Apply the physical requested rotation exactly once, after the matcher
    # has used the same B_theta lattice convention for its Cartesian target.
    # ------------------------------------------------------------

    if abs(float(twist_angle)) > 1e-12:
        B = _rotate_atoms_z(B, float(twist_angle))

    # ------------------------------------------------------------
    # Build matched supercells and apply only the selected in-plane
    # deformation.  _apply_2d_lattice_target keeps their Z coordinates and
    # third cell vectors unchanged.
    # ------------------------------------------------------------

    A = _make_2d_supercell(A, match.matrix_a)
    B = _make_2d_supercell(B, match.matrix_b)

    if match.target_cell_2d is None:
        raise RuntimeError("The lattice matcher did not provide a common 2D target.")

    target_xy = np.column_stack((match.target_cell_2d, np.zeros(2)))
    A = _apply_2d_lattice_target(A, target_xy)
    B = _apply_2d_lattice_target(B, target_xy)

    if not np.allclose(A.cell.array[:2, :2], match.target_cell_2d, atol=1e-9):
        raise RuntimeError("Bottom-layer deformation did not reach the selected target cell.")
    if not np.allclose(B.cell.array[:2, :2], match.target_cell_2d, atol=1e-9):
        raise RuntimeError("Top-layer deformation did not reach the selected target cell.")

    # ------------------------------------------------------------
    # Position each layer around z = 0.
    # ------------------------------------------------------------

    A_positions = (
        A.get_positions()
    )

    B_positions = (
        B.get_positions()
    )

    A_min = A_positions[
        :,
        2,
    ].min()

    A_max = A_positions[
        :,
        2,
    ].max()

    B_min = B_positions[
        :,
        2,
    ].min()

    B_max = B_positions[
        :,
        2,
    ].max()

    A_height = (
        A_max
        - A_min
    )

    B_height = (
        B_max
        - B_min
    )

    # Bottom layer starts at zero.
    A.translate(
        (
            0.0,
            0.0,
            -A_min,
        )
    )

    A_top = (
        A_height
    )

    # Top layer starts after interlayer gap.
    B.translate(
        (
            0.0,
            0.0,
            A_top
            + float(interlayer_distance)
            - B_min,
        )
    )

    # ------------------------------------------------------------
    # Combine.
    # ------------------------------------------------------------

    result = A + B

    # ------------------------------------------------------------
    # Set common cell.
    # ------------------------------------------------------------

    cell = result.cell.array.copy()

    xy_a = A.cell.array[
        0
    ]

    xy_b = A.cell.array[
        1
    ]

    total_height = (
        A_height
        + float(interlayer_distance)
        + B_height
        + 2.0 * float(vacuum)
    )

    cell[0] = xy_a
    cell[1] = xy_b

    cell[2] = np.array(
        [
            0.0,
            0.0,
            total_height,
        ]
    )

    result.set_cell(
        cell,
        scale_atoms=False,
    )
    result.pbc = (True, True, False)

    # Shift structure into cell.
    positions = (
        result.get_positions()
    )

    positions[
        :,
        2,
    ] += float(vacuum)

    result.set_positions(
        positions
    )

    result.wrap()

    if center:

        result.center(
            axis=2
        )

    # ------------------------------------------------------------
    # Metadata.
    # ------------------------------------------------------------

    result.info[
        "quantum_studio_operation"
    ] = "heterostructure"

    result.info[
        "heterostructure_layer_count"
    ] = 2

    result.info[
        "heterostructure_twist_angle"
    ] = float(
        twist_angle
    )

    result.info[
        "heterostructure_interlayer_distance"
    ] = float(
        interlayer_distance
    )

    result.info[
        "heterostructure_mismatch"
    ] = float(
        match.mismatch
    )

    result.info[
        "heterostructure_strain_bottom"
    ] = float(
        match.strain_a
    )

    result.info[
        "heterostructure_strain_top"
    ] = float(
        match.strain_b
    )

    result.info[
        "heterostructure_matrix_bottom"
    ] = (
        match.matrix_a.tolist()
    )

    result.info[
        "heterostructure_matrix_top"
    ] = (
        match.matrix_b.tolist()
    )


    result.info["heterostructure_strain_mode"] = mode
    result.info["heterostructure_vacuum"] = float(vacuum)
    result.info["heterostructure_det_A"] = int(match.determinant_a)
    result.info["heterostructure_det_B"] = int(match.determinant_b)
    result.info["heterostructure_requested_orientation"] = float(twist_angle)
    result.info["heterostructure_principal_strain_A"] = (
        match.principal_strains_a.tolist()
        if match.principal_strains_a is not None else []
    )
    result.info["heterostructure_principal_strain_B"] = (
        match.principal_strains_b.tolist()
        if match.principal_strains_b is not None else []
    )
    result.info["heterostructure_max_principal_strain"] = float(match.max_principal_strain)
    result.info["heterostructure_cartesian_residual"] = float(match.cartesian_residual)
    result.info["heterostructure_residual_rotation_deg"] = float(match.residual_rotation_deg)
    result.info["heterostructure_estimated_atom_count"] = int(match.estimated_atom_count)
    result.info["heterostructure_final_atom_count"] = int(len(result))

    return result, match, _search_statistics


def create_heterostructure(
    structure_a,
    structure_b,
    interlayer_distance: float = 3.4,
    max_index: int = 6,
    max_strain: float = 0.05,
    strain_mode: str = "balanced",
    twist_angle: float = 0.0,
    vacuum: float = 15.0,
    center: bool = True,
) -> Atoms:
    """Construct a commensurate two-layer heterostructure."""

    result, _match, _statistics = _create_commensurate_bilayer(
        structure_a,
        structure_b,
        interlayer_distance=interlayer_distance,
        max_index=max_index,
        max_strain=max_strain,
        strain_mode=strain_mode,
        twist_angle=twist_angle,
        vacuum=vacuum,
        center=center,
        residual_rotation_limit_deg=0.05,
    )
    return result


# ================================================================
# Moiré / twisted bilayer
# ================================================================

def create_moire_structure(
    structure_a,
    structure_b,
    twist_angle: float = 0.0,
    max_index: int = 8,
    max_strain: float = 0.01,
    interlayer_distance: float = 3.4,
    vacuum: float = 15.0,
    strain_mode: str = "balanced",
) -> Atoms:
    """Construct a commensurate Moiré bilayer using the shared HNF matcher.

    ``twist_angle`` is the physical rotation of layer B.  The matcher uses
    ``B_theta = B @ R(theta).T`` and this routine then rotates B's atoms and
    cell exactly once before applying the accepted in-plane strain target.
    """

    angle = float(twist_angle)
    determinant_cap = int(max_index) ** 2
    result, match, statistics = _create_commensurate_bilayer(
        structure_a,
        structure_b,
        interlayer_distance=interlayer_distance,
        max_index=max_index,
        max_strain=max_strain,
        strain_mode=strain_mode,
        twist_angle=angle,
        vacuum=vacuum,
        center=True,
        residual_rotation_limit_deg=0.01,
    )

    # The helper rejects a candidate before assembly when this condition is
    # violated.  Keep the explicit guard as a durable scientific invariant.
    if abs(float(match.residual_rotation_deg)) > 0.01 + 1e-12:
        raise RuntimeError(
            "Moiré matching would require a hidden rotational correction "
            "greater than 0.01 degrees."
        )

    result.info["quantum_studio_operation"] = "moire"
    # Preserve the legacy field and add explicit diagnostic names.
    result.info["moire_twist_angle"] = angle
    result.info["moire_requested_twist_deg"] = angle
    result.info["moire_achieved_twist_deg"] = angle
    result.info["moire_residual_rotation_deg"] = float(match.residual_rotation_deg)
    result.info["moire_matrix_A"] = match.matrix_a.tolist()
    result.info["moire_matrix_B"] = match.matrix_b.tolist()
    result.info["moire_det_A"] = int(match.determinant_a)
    result.info["moire_det_B"] = int(match.determinant_b)
    result.info["moire_principal_strains_A"] = (
        match.principal_strains_a.tolist()
        if match.principal_strains_a is not None else []
    )
    result.info["moire_principal_strains_B"] = (
        match.principal_strains_b.tolist()
        if match.principal_strains_b is not None else []
    )
    result.info["moire_max_principal_strain"] = float(match.max_principal_strain)
    result.info["moire_cartesian_residual"] = float(match.cartesian_residual)
    result.info["moire_strain_mode"] = str(strain_mode).strip().lower()
    result.info["moire_interlayer_distance"] = float(interlayer_distance)
    result.info["moire_vacuum"] = float(vacuum)
    result.info["moire_final_atom_count"] = int(len(result))
    result.info["moire_determinant_cap"] = determinant_cap
    result.info["moire_hnf_candidates"] = int(statistics.hnf_candidates)
    result.info["moire_local_integer_candidates"] = int(statistics.local_integer_candidates)
    result.info["moire_prefilter_survivors"] = int(statistics.prefilter_survivors)
    result.info["moire_full_diagnostic_evaluations"] = int(
        statistics.full_diagnostic_evaluations
    )

    return result


# ================================================================
# Layer builder aliases
# ================================================================

def create_multilayer_structure(
    layers,
    interlayer_distance=3.4,
    stacking="AA",
) -> Atoms:

    return create_layered_structure(
        layers,
        interlayer_distance=interlayer_distance,
        stacking=stacking,
    )


# ================================================================
# Compatibility aliases
# ================================================================

make_supercell_structure = create_supercell
make_slab = create_slab
make_heterostructure = create_heterostructure
make_moire = create_moire_structure
make_layered_structure = create_layered_structure


# ================================================================
# High-level facade
# ================================================================

class StructureOperations:

    @staticmethod
    def supercell(
        structure,
        nx=1,
        ny=1,
        nz=1,
    ):

        return create_supercell(
            structure,
            nx,
            ny,
            nz,
        )

    @staticmethod
    def slab(
        structure,
        repetitions=(1, 1, 1),
        vacuum=10.0,
        axis=2,
    ):

        return create_slab(
            structure,
            repetitions,
            vacuum,
            axis,
        )

    @staticmethod
    def vacuum(
        structure,
        vacuum=10.0,
        axis=2,
    ):

        return add_vacuum(
            structure,
            vacuum,
            axis,
        )

    @staticmethod
    def strain(
        structure,
        strain_x=0.0,
        strain_y=0.0,
        strain_z=0.0,
        scale_atoms=True,
    ):

        return apply_strain(
            structure,
            strain_x,
            strain_y,
            strain_z,
            scale_atoms,
        )

    @staticmethod
    def nanotube(
        structure,
        radius=10.0,
        axis=2,
    ):

        return create_nanotube(
            structure,
            radius,
            axis,
        )

    @staticmethod
    def heterostructure(
        structure_a,
        structure_b,
        **kwargs,
    ):

        return create_heterostructure(
            structure_a,
            structure_b,
            **kwargs,
        )

    @staticmethod
    def moire(
        structure_a,
        structure_b,
        **kwargs,
    ):

        return create_moire_structure(
            structure_a,
            structure_b,
            **kwargs,
        )

    @staticmethod
    def layered(
        layers,
        **kwargs,
    ):

        return create_layered_structure(
            layers,
            **kwargs,
        )
