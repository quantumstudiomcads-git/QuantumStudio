"""Deterministic, structured Quantum ESPRESSO input serialization."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import isfinite
from typing import Any

from ase.data import atomic_masses, atomic_numbers

from backend.engines.qe.models import InvalidQEParameterError, MissingPseudopotentialError


def format_number(value: int | float) -> str:
    """Stable, sufficiently precise decimal formatting for QE numeric input."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidQEParameterError(f"QE numeric value must be an int or float, got {type(value).__name__}.")
    if not isfinite(float(value)):
        raise InvalidQEParameterError("QE numeric values must be finite.")
    return str(value) if isinstance(value, int) else format(value, ".12g")


def format_value(value: Any) -> str:
    if value is None:
        raise InvalidQEParameterError("Unset QE namelist values must be omitted, not serialized.")
    if isinstance(value, bool):
        return ".true." if value else ".false."
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    if isinstance(value, (int, float)):
        return format_number(value)
    raise InvalidQEParameterError(f"Unsupported QE namelist value type: {type(value).__name__}.")


def serialize_namelist(name: str, values: Mapping[str, Any]) -> str:
    """Serialize a QE Fortran namelist with stable lexical key order."""
    if not isinstance(name, str) or not name:
        raise InvalidQEParameterError("QE namelist name must be non-empty.")
    lines = [f"&{name.upper()}"]
    for key in sorted(values):
        value = values[key]
        if value is not None:
            lines.append(f"  {key} = {format_value(value)}")
    lines.append("/")
    return "\n".join(lines)


def _vector(value: object, label: str) -> tuple[float, float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        raise InvalidQEParameterError(f"{label} must contain exactly three numeric values.")
    result = tuple(float(item) for item in value)
    if not all(isfinite(item) for item in result):
        raise InvalidQEParameterError(f"{label} must contain only finite values.")
    return result


def structure_cards(structure: Mapping[str, Any], pseudopotentials: Mapping[str, object]) -> str:
    """Build ibrav=0 structure cards using native Å Cartesian geometry unchanged."""
    atoms = structure.get("atoms")
    cell = structure.get("cell")
    if not isinstance(atoms, list) or not atoms:
        raise InvalidQEParameterError("QE input requires a non-empty request structure snapshot.")
    if not isinstance(cell, Sequence) or len(cell) != 3:
        raise InvalidQEParameterError("QE input requires a 3x3 request cell.")

    species: list[str] = []
    positions: list[tuple[str, float, float, float]] = []
    for atom in atoms:
        if not isinstance(atom, Mapping):
            raise InvalidQEParameterError("Structure atom records must be mappings.")
        element = str(atom.get("element", "")).strip()
        if element not in atomic_numbers:
            raise InvalidQEParameterError(f"Unknown element in request structure: {element!r}.")
        if element not in species:
            species.append(element)
        try:
            x, y, z = (float(atom[key]) for key in ("x", "y", "z"))
        except (KeyError, TypeError, ValueError) as error:
            raise InvalidQEParameterError(f"Atom {element!r} has invalid Cartesian coordinates.") from error
        if not all(isfinite(value) for value in (x, y, z)):
            raise InvalidQEParameterError(f"Atom {element!r} has non-finite Cartesian coordinates.")
        positions.append((element, x, y, z))

    lines = ["ATOMIC_SPECIES"]
    for element in species:
        selection = pseudopotentials.get(element)
        if selection is None:
            raise MissingPseudopotentialError(f"Missing pseudopotential assignment for element {element!r}.")
        filename = getattr(selection, "filename", None)
        if not isinstance(filename, str) or not filename.strip():
            raise MissingPseudopotentialError(f"Pseudopotential filename for element {element!r} is empty.")
        lines.append(f"{element} {format_number(float(atomic_masses[atomic_numbers[element]]))} {filename}")

    lines.extend(("", "CELL_PARAMETERS angstrom"))
    for index, vector in enumerate(cell, start=1):
        lines.append(" ".join(format_number(value) for value in _vector(vector, f"cell vector {index}")))
    lines.extend(("", "ATOMIC_POSITIONS angstrom"))
    for element, x, y, z in positions:
        lines.append(f"{element} {format_number(x)} {format_number(y)} {format_number(z)}")
    return "\n".join(lines)


def k_points_card(parameters: Mapping[str, Any], periodic: object) -> str:
    """Serialize the deliberately small C4 gamma/automatic k-point model."""
    value = parameters.get("kpoints", parameters.get("dense_kpoints"))
    if value is None:
        return "K_POINTS gamma"
    if isinstance(value, Mapping):
        mode = str(value.get("mode", "automatic")).lower()
        if mode == "gamma":
            return "K_POINTS gamma"
        if mode != "automatic":
            raise InvalidQEParameterError(f"Unsupported C4 K_POINTS mode: {mode!r}.")
        mesh = value.get("mesh")
        shifts = value.get("shifts", (0, 0, 0))
    else:
        mesh, shifts = value, (0, 0, 0)
    mesh_values = _vector(mesh, "K_POINTS mesh")
    shift_values = _vector(shifts, "K_POINTS shifts")
    if any(int(item) != item or item < 1 for item in mesh_values):
        raise InvalidQEParameterError("K_POINTS mesh values must be positive integers.")
    if any(int(item) != item or item not in (0, 1) for item in shift_values):
        raise InvalidQEParameterError("K_POINTS shifts must be 0 or 1.")
    if isinstance(periodic, Sequence) and len(periodic) == 3:
        for axis, enabled in enumerate(periodic):
            if not bool(enabled) and int(mesh_values[axis]) != 1:
                raise InvalidQEParameterError(
                    "Automatic K_POINTS mesh is incompatible with non-periodic axis "
                    f"{axis}; use 1 explicitly or choose gamma."
                )
    numbers = tuple(int(item) for item in mesh_values + shift_values)
    return "K_POINTS automatic\n" + " ".join(str(item) for item in numbers)


def pw_input(calculation_id: str, parameters: Mapping[str, Any], structure: Mapping[str, Any], context, pseudopotentials: Mapping[str, object]) -> str:
    """Build a valid C4 pw.x input for SCF, relax, or vc-relax."""
    qe_calculation = {"scf": "scf", "nscf": "nscf", "qe_pw_nscf": "nscf", "relax": "relax", "vc_relax": "vc-relax"}[calculation_id]
    atoms = structure.get("atoms", [])
    species_count = len({str(atom.get("element", "")) for atom in atoms if isinstance(atom, Mapping)})
    control = {"calculation": qe_calculation, "prefix": context.prefix, "outdir": context.outdir, "pseudo_dir": context.pseudo_dir}
    system = {"ibrav": 0, "nat": len(atoms), "ntyp": species_count, "nbnd": parameters.get("nbnd"), "ecutwfc": parameters.get("ecutwfc"), "ecutrho": parameters.get("ecutrho"), "input_dft": parameters.get("functional"), "nspin": 2 if parameters.get("spin") else None, "lspinorb": True if parameters.get("soc") else None, "noncolin": True if parameters.get("soc") else None, "occupations": parameters.get("occupations"), "smearing": parameters.get("smearing"), "degauss": parameters.get("degauss")}
    electrons = {"conv_thr": parameters.get("conv_thr")}
    sections = [serialize_namelist("CONTROL", control), serialize_namelist("SYSTEM", system), serialize_namelist("ELECTRONS", electrons)]
    if calculation_id in {"relax", "vc_relax"}:
        sections.append(serialize_namelist("IONS", {"forc_conv_thr": parameters.get("force_threshold")}))
    if calculation_id == "vc_relax":
        sections.append(serialize_namelist("CELL", {"press_conv_thr": parameters.get("stress_threshold")}))
    sections.extend((structure_cards(structure, pseudopotentials), k_points_card(parameters, structure.get("periodic"))))
    return "\n\n".join(sections) + "\n"


def phonon_input(parameters: Mapping[str, Any], context) -> str:
    qmesh = _vector(parameters.get("qmesh", ()), "phonon qmesh")
    if any(int(item) != item or item < 1 for item in qmesh):
        raise InvalidQEParameterError("Phonon qmesh values must be positive integers.")
    values = {"prefix": context.prefix, "outdir": context.outdir, "fildyn": f"{context.prefix}.dyn", "tr2_ph": parameters.get("tr2_ph"), "ldisp": True, "nq1": int(qmesh[0]), "nq2": int(qmesh[1]), "nq3": int(qmesh[2])}
    return serialize_namelist("INPUTPH", values) + "\n"
