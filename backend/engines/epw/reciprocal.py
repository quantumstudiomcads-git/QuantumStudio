"""Reciprocal-basis helpers for EPW/Wannier validation.

Quantum Studio stores direct-cell vectors as rows.  For a direct cell ``A``
the reciprocal rows are ``B = 2*pi*inv(A).T`` and a fractional row vector
maps to Cartesian reciprocal space as ``k_cart = k_frac @ B``.
"""

from __future__ import annotations

import numpy as np


def qe_ibrav2_cell(celldm_bohr: float, bohr_to_angstrom: float = 0.529177210903) -> np.ndarray:
    """Return the QE ``ibrav=2`` primitive cell in Angstrom, as row vectors."""
    p = float(celldm_bohr) * float(bohr_to_angstrom) / 2.0
    return np.array(((-p, 0.0, p), (0.0, p, p), (-p, p, 0.0)), dtype=float)


def reciprocal_basis(cell: np.ndarray) -> np.ndarray:
    """Return reciprocal row vectors in inverse Angstrom."""
    a = np.asarray(cell, dtype=float)
    if a.shape != (3, 3):
        raise ValueError("direct cell must have shape (3, 3)")
    if abs(float(np.linalg.det(a))) < 1.0e-14:
        raise ValueError("direct cell is singular")
    return 2.0 * np.pi * np.linalg.inv(a).T


def fractional_to_cartesian(fractional: np.ndarray, reciprocal: np.ndarray) -> np.ndarray:
    """Map one or more row fractional reciprocal coordinates to Cartesian."""
    q = np.asarray(fractional, dtype=float)
    b = np.asarray(reciprocal, dtype=float)
    if b.shape != (3, 3) or q.shape[-1] != 3:
        raise ValueError("fractional coordinates must end in 3 and reciprocal basis be (3, 3)")
    return q @ b


def basis_transform(source_cell: np.ndarray, target_cell: np.ndarray) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Return ``U`` for ``target_cell = U @ source_cell`` and integer diagnostics."""
    source = np.asarray(source_cell, dtype=float)
    target = np.asarray(target_cell, dtype=float)
    u = target @ np.linalg.inv(source)
    integer = np.rint(u).astype(int)
    return u, integer, float(np.max(np.abs(u - integer))), float(np.linalg.det(integer))


def transform_fractional_coordinates(fractional: np.ndarray, basis_change: np.ndarray) -> np.ndarray:
    """Transform row fractional coordinates under ``A' = U @ A``."""
    return np.asarray(fractional, dtype=float) @ np.asarray(basis_change, dtype=float).T


def cartesian_path_difference(path_a: np.ndarray, basis_a: np.ndarray, path_b: np.ndarray, basis_b: np.ndarray) -> tuple[float, float, float]:
    """Return max/RMS/mean Cartesian differences for two equally sampled paths."""
    a = fractional_to_cartesian(path_a, basis_a)
    b = fractional_to_cartesian(path_b, basis_b)
    if a.shape != b.shape:
        raise ValueError("paths must have identical shapes")
    d = np.linalg.norm(a - b, axis=1)
    return float(np.max(d)), float(np.sqrt(np.mean(d * d))), float(np.mean(d))
