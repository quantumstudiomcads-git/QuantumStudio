"""Deterministic, structured Quantum ESPRESSO input serialization."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import isfinite
from typing import Any

from ase.data import atomic_masses, atomic_numbers

from backend.engines.qe.models import InvalidQEParameterError, MissingPseudopotentialError
from backend.dft.functionals import resolve
from backend.engines.qe.hybrid_bands import additional_k_points_card


def format_number(value: int | float) -> str:
    """Stable, sufficiently precise decimal formatting for QE numeric input."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidQEParameterError(f"QE numeric value must be an int or float, got {type(value).__name__}.")
    if not isfinite(float(value)):
        raise InvalidQEParameterError("QE numeric values must be finite.")
    return str(value) if isinstance(value, int) else format(value, ".12g")


_NUMERIC_NAMELIST_KEYS = frozenset({
    "ecutwfc", "ecutrho", "conv_thr", "degauss", "nbnd", "electron_maxstep",
    "mixing_beta", "exx_fraction", "screening_parameter", "nqx1", "nqx2", "nqx3",
    "tot_magnetization", "emin", "emax", "deltae", "forc_conv_thr",
    "press_conv_thr", "iverbosity", "max_seconds", "nq1", "nq2", "nq3", "kpoint",
    "kband", "spin_component", "plot_num", "iflag", "output_format", "nk1", "nk2", "nk3", "nw", "wmin", "wmax", "intersmear", "intrasmear",
})


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
        if value is None:
            continue
        normalized_key = str(key).strip().lower()
        if isinstance(value, str) and not value.strip():
            if normalized_key in _NUMERIC_NAMELIST_KEYS:
                raise InvalidQEParameterError(f"{key} requires an integer or float value.")
            continue
        if normalized_key in _NUMERIC_NAMELIST_KEYS:
            if isinstance(value, str) and value.strip().lower() in {"none", "null"}:
                raise InvalidQEParameterError(f"{key} requires an integer or float value.")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise InvalidQEParameterError(f"{key} requires an integer or float value.")
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


def _band_path_card(path: object) -> str:
    if not isinstance(path, list) or len(path) < 2:
        raise InvalidQEParameterError("Band structure requires an explicit ordered band path.")
    rows = []
    for index, point in enumerate(path):
        if not isinstance(point, Mapping) or not isinstance(point.get("coordinates"), (list, tuple)) or len(point["coordinates"]) != 3:
            raise InvalidQEParameterError("Band path points require three fractional coordinates.")
        count = 1 if index == len(path) - 1 else int(point.get("points", 0))
        if count < 1:
            raise InvalidQEParameterError("Band path interpolation counts must be positive.")
        rows.append(" ".join(format_number(float(value)) for value in point["coordinates"]) + f" {count}")
    return "K_POINTS crystal_b\n" + str(len(rows)) + "\n" + "\n".join(rows)

def k_points_card(parameters: Mapping[str, Any], periodic: object) -> str:
    """Resolve exactly one primary QE K_POINTS card, with explicit band paths taking precedence."""
    if parameters.get("optical_full_grid") is not None:
        from backend.optical.grid import full_bz_grid
        points = full_bz_grid(parameters["optical_full_grid"]); weight = 1.0 / len(points); rows = ["K_POINTS crystal", str(len(points))]; rows.extend(f"{x:.12f} {y:.12f} {z:.12f} {weight:.12f}" for x, y, z in points); return "\n".join(rows)
    if parameters.get("epw_full_grid") is not None:
        from backend.engines.epw.grid import qe_full_grid_card
        from backend.optical.grid import full_bz_grid
        return qe_full_grid_card(parameters["epw_full_grid"])
    if parameters.get("band_path") is not None:
        return _band_path_card(parameters["band_path"])
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


def electronic_method(parameters: Mapping[str, Any]) -> str:
    """Resolve one unambiguous QE electronic method, preserving legacy booleans."""
    raw = str(parameters.get("spin_treatment", "")).strip().upper().replace(" ", "_")
    aliases = {"NONSPIN": "SCALAR_NONSPIN", "NON_SPIN": "SCALAR_NONSPIN", "SCALAR": "SCALAR_NONSPIN", "COLLINEAR": "COLLINEAR_SPIN", "SPIN": "COLLINEAR_SPIN", "NONCOLLINEAR": "NONCOLLINEAR", "SOC": "SOC"}
    legacy_spin = bool(parameters.get("spin", False))
    legacy_soc = bool(parameters.get("soc", False))
    legacy_noncolin = bool(parameters.get("noncolin", False))
    method = aliases.get(raw, raw) if raw else ("SOC" if legacy_soc else "NONCOLLINEAR" if legacy_noncolin else "COLLINEAR_SPIN" if legacy_spin else "SCALAR_NONSPIN")
    if method == "SCALAR_NONSPIN" and (legacy_spin or legacy_soc or legacy_noncolin):
        method = "SOC" if legacy_soc else "NONCOLLINEAR" if legacy_noncolin else "COLLINEAR_SPIN"
    if method not in {"SCALAR_NONSPIN", "COLLINEAR_SPIN", "NONCOLLINEAR", "SOC"}:
        raise InvalidQEParameterError("Spin treatment must be Non-spin, Collinear, Noncollinear, or SOC.")
    if method == "COLLINEAR_SPIN" and (legacy_soc or legacy_noncolin):
        raise InvalidQEParameterError("Collinear spin cannot be combined with noncolin or lspinorb/SOC.")
    if method == "SCALAR_NONSPIN" and (legacy_spin or legacy_soc or legacy_noncolin):
        raise InvalidQEParameterError("Scalar non-spin treatment contradicts requested spin flags.")
    if method in {"NONCOLLINEAR", "SOC"} and legacy_spin:
        raise InvalidQEParameterError("nspin=2 collinear spin cannot be combined with noncollinear or SOC treatment.")
    return method

def method_metadata(parameters: Mapping[str, Any]) -> dict[str, Any]:
    method = electronic_method(parameters)
    terms = parameters.get("hubbard_terms", [])
    return {"functional": resolve(parameters.get("xc_functional", parameters.get("functional", "pbe"))).id, "spin_treatment": method, "soc": method == "SOC", "noncollinear": method in {"NONCOLLINEAR", "SOC"}, "dft_plus_u": bool(terms), "hubbard_terms": list(terms) if isinstance(terms, list) else [], "hubbard_projector": parameters.get("hubbard_projector") if terms else None, "qe_hubbard_syntax": "HUBBARD_CARD_QE_7_6" if terms else None}

def occupation_values(parameters: Mapping[str, Any]) -> dict[str, Any]:
    """Return only occupation controls applicable to the current QE run."""
    raw = parameters.get("occupations")
    occupation = str(raw).strip().lower() if raw is not None else ""
    if occupation in {"", "fixed", "tetrahedra", "tetrahedra_opt"}:
        return {"occupations": raw} if raw not in (None, "") else {}
    if occupation != "smearing":
        raise InvalidQEParameterError(f"Unsupported QE occupations mode: {raw!r}.")
    smearing = parameters.get("smearing")
    if not isinstance(smearing, str) or not smearing.strip():
        raise InvalidQEParameterError("Smearing method requires a valid QE enum value.")
    degauss = parameters.get("degauss")
    if isinstance(degauss, bool) or not isinstance(degauss, (int, float)):
        raise InvalidQEParameterError("Smearing width requires a numeric value.")
    if not isfinite(float(degauss)) or float(degauss) <= 0:
        raise InvalidQEParameterError("Smearing width must be finite and positive.")
    return {"occupations": "smearing", "smearing": smearing.strip(), "degauss": float(degauss)}

def _species_order(structure: Mapping[str, Any]) -> list[str]:
    order=[]
    for atom in structure.get("atoms", []):
        if isinstance(atom, Mapping):
            label=str(atom.get("element", "")).strip()
            if label and label not in order: order.append(label)
    return order

def _magnetization_values(parameters: Mapping[str, Any], structure: Mapping[str, Any], method: str) -> dict[str, Any]:
    # Starting magnetization is a collinear-spin initialization only. Ignore
    # stale scalar/noncollinear values rather than validating or serializing
    # them as QE nspin=2 inputs.
    initial=parameters.get("starting_magnetization", {})
    if method != "COLLINEAR_SPIN":
        if "tot_magnetization" in parameters and parameters.get("tot_magnetization") is not None:
            raise InvalidQEParameterError("tot_magnetization is only supported for collinear spin in E3.")
        return {}
    if initial is None: initial={}
    if not isinstance(initial, Mapping): raise InvalidQEParameterError("starting_magnetization must map atomic species to dimensionless QE values.")
    species=_species_order(structure); values={}
    for label,value in initial.items():
        if str(label) not in species: raise InvalidQEParameterError(f"Starting magnetization species is absent from structure: {label}.")
        try: numeric=float(value)
        except (TypeError,ValueError) as error: raise InvalidQEParameterError(f"Starting magnetization for {label} must be numeric.") from error
        if not isfinite(numeric): raise InvalidQEParameterError(f"Starting magnetization for {label} must be finite.")
        values[f"starting_magnetization({species.index(str(label))+1})"]=numeric
    total=parameters.get("tot_magnetization")
    if total is not None:
        if method != "COLLINEAR_SPIN": raise InvalidQEParameterError("tot_magnetization is only supported for collinear spin in E3.")
        if values: raise InvalidQEParameterError("Do not combine tot_magnetization with starting_magnetization.")
        try: total=float(total)
        except (TypeError,ValueError) as error: raise InvalidQEParameterError("tot_magnetization must be numeric.") from error
        if not isfinite(total): raise InvalidQEParameterError("tot_magnetization must be finite.")
        values["tot_magnetization"]=total
    return values

def hubbard_card(parameters: Mapping[str, Any], structure: Mapping[str, Any]) -> str | None:
    terms=parameters.get("hubbard_terms", [])
    if terms in (None,[]): return None
    if not isinstance(terms, list): raise InvalidQEParameterError("hubbard_terms must be a list of structured Hubbard U terms.")
    projector=str(parameters.get("hubbard_projector", "ortho-atomic")).strip().lower()
    if projector not in {"atomic", "ortho-atomic", "norm-atomic", "pseudo"}: raise InvalidQEParameterError("Unsupported QE 7.6 Hubbard projector type.")
    species=set(_species_order(structure)); seen=set(); lines=[f"HUBBARD ({projector})"]
    for term in terms:
        if not isinstance(term, Mapping): raise InvalidQEParameterError("Each Hubbard term must be a species/manifold/U mapping.")
        label=str(term.get("species", "")).strip(); manifold=str(term.get("manifold", "")).strip().lower()
        if label not in species: raise InvalidQEParameterError(f"Hubbard species is absent from structure: {label}.")
        if not __import__("re").fullmatch(r"[1-7][spdf]", manifold): raise InvalidQEParameterError(f"Invalid Hubbard manifold for {label}: {manifold!r}.")
        try: value=float(term.get("u_eV"))
        except (TypeError,ValueError) as error: raise InvalidQEParameterError(f"Hubbard U for {label}-{manifold} must be numeric eV.") from error
        if not isfinite(value) or value < 0: raise InvalidQEParameterError(f"Hubbard U for {label}-{manifold} must be finite and non-negative eV.")
        identity=(label,manifold)
        if identity in seen: raise InvalidQEParameterError(f"Duplicate Hubbard U term for {label}-{manifold}.")
        seen.add(identity); lines.append(f"U {label}-{manifold} {format_number(value)}")
    return "\n".join(lines)

def pw_input(calculation_id: str, parameters: Mapping[str, Any], structure: Mapping[str, Any], context, pseudopotentials: Mapping[str, object]) -> str:
    """Build a valid C4 pw.x input for SCF, relax, or vc-relax."""
    qe_calculation = {"scf": "scf", "nscf": "nscf", "qe_pw_nscf": ("bands" if parameters.get("epw_full_grid") is not None else "nscf"), "relax": "relax", "vc_relax": "vc-relax"}[calculation_id]
    functional = resolve(parameters.get("xc_functional", parameters.get("functional", "pbe")))
    atoms = structure.get("atoms", [])
    species_count = len({str(atom.get("element", "")) for atom in atoms if isinstance(atom, Mapping)})
    profile = str(parameters.get("execution_profile", "STANDARD")).strip().upper()
    if profile not in {"STANDARD", "LOW_MEMORY"}:
        raise InvalidQEParameterError("Unknown QE execution profile.")
    control = {"calculation": qe_calculation, "prefix": context.prefix, "outdir": context.outdir, "pseudo_dir": context.pseudo_dir, "wf_collect": parameters.get("wf_collect", True), "disk_io": parameters.get("disk_io")}
    if profile == "LOW_MEMORY":
        control["disk_io"] = "medium"
    method = electronic_method(parameters)
    magnetization = _magnetization_values(parameters, structure, method)
    system = {"ibrav": 0, "nat": len(atoms), "ntyp": species_count, "nbnd": parameters.get("nbnd"), "ecutwfc": parameters.get("ecutwfc"), "ecutrho": parameters.get("ecutrho"), "input_dft": functional.qe_input_dft, "exx_fraction": parameters.get("exx_fraction", functional.exx_fraction) if functional.hybrid else None, "screening_parameter": parameters.get("screening_parameter", functional.screening) if functional.screening is not None else None, "ace": parameters.get("ace", True) if functional.hybrid else None, "nqx1": (parameters.get("exx_q_mesh") or ((parameters.get("kpoints") or {}).get("mesh") if isinstance(parameters.get("kpoints"), Mapping) else parameters.get("kpoints")) or [1,1,1])[0] if functional.hybrid else None, "nqx2": (parameters.get("exx_q_mesh") or ((parameters.get("kpoints") or {}).get("mesh") if isinstance(parameters.get("kpoints"), Mapping) else parameters.get("kpoints")) or [1,1,1])[1] if functional.hybrid else None, "nqx3": (parameters.get("exx_q_mesh") or ((parameters.get("kpoints") or {}).get("mesh") if isinstance(parameters.get("kpoints"), Mapping) else parameters.get("kpoints")) or [1,1,1])[2] if functional.hybrid else None, "exxdiv_treatment": parameters.get("exxdiv_treatment", "gygi-baldereschi") if functional.hybrid else None, "nspin": 2 if method == "COLLINEAR_SPIN" else None, "lspinorb": True if method == "SOC" else None, "noncolin": True if method in {"NONCOLLINEAR", "SOC"} else None, "nosym": bool(parameters.get("nosym", False)), "noinv": bool(parameters.get("noinv", False)), **magnetization, **occupation_values(parameters)}
    electrons = {"conv_thr": parameters.get("conv_thr")}
    if profile == "LOW_MEMORY":
        electrons.update({"diagonalization": "cg", "mixing_ndim": 4})
    elif parameters.get("diagonalization") is not None:
        electrons["diagonalization"] = parameters.get("diagonalization")
    if parameters.get("diago_david_ndim") is not None:
        electrons["diago_david_ndim"] = parameters.get("diago_david_ndim")
    if parameters.get("mixing_ndim") is not None and profile != "LOW_MEMORY":
        electrons["mixing_ndim"] = parameters.get("mixing_ndim")
    if parameters.get("electron_maxstep") is not None:
        electrons["electron_maxstep"] = parameters.get("electron_maxstep")
    sections = [serialize_namelist("CONTROL", control), serialize_namelist("SYSTEM", system), serialize_namelist("ELECTRONS", electrons)]
    if calculation_id in {"relax", "vc_relax"}:
        sections.append(serialize_namelist("IONS", {"forc_conv_thr": parameters.get("force_threshold")}))
    if calculation_id == "vc_relax":
        sections.append(serialize_namelist("CELL", {"press_conv_thr": parameters.get("stress_threshold")}))
    sections.extend((structure_cards(structure, pseudopotentials), k_points_card(parameters, structure.get("periodic"))))
    contract=parameters.get("hybrid_band_contract")
    if contract is not None:
        if not functional.hybrid or calculation_id != "scf": raise InvalidQEParameterError("ADDITIONAL_K_POINTS direct band route requires a hybrid SCF task.")
        sections.append(additional_k_points_card(contract))
    hubbard = hubbard_card(parameters, structure)
    if hubbard is not None: sections.append(hubbard)
    return "\n\n".join(sections) + "\n"


def phonon_input(parameters: Mapping[str, Any], context) -> str:
    if parameters.get("q_point") is not None or parameters.get("gamma_only"):
        q_point = parameters.get("q_point", (0.0, 0.0, 0.0))
        if not isinstance(q_point, (list, tuple)) or len(q_point) != 3 or any(not isfinite(float(item)) for item in q_point):
            raise InvalidQEParameterError("Gamma phonons require three finite q-point components.")
        values = {"prefix": context.prefix, "outdir": context.outdir, "fildyn": parameters.get("fildyn", f"{context.prefix}.dyn"), "tr2_ph": parameters.get("tr2_ph"), "ldisp": False, "verbosity": parameters.get("verbosity", "high")}
        return serialize_namelist("INPUTPH", values) + "\n0.0 0.0 0.0\n"
    qmesh = _vector(parameters.get("qmesh", ()), "phonon qmesh")
    if any(int(item) != item or item < 1 for item in qmesh):
        raise InvalidQEParameterError("Phonon qmesh values must be positive integers.")
    values = {"prefix": context.prefix, "outdir": context.outdir, "fildyn": parameters.get("fildyn", f"{context.prefix}.dyn"), "tr2_ph": parameters.get("tr2_ph"), "ldisp": True, "nq1": int(qmesh[0]), "nq2": int(qmesh[1]), "nq3": int(qmesh[2]), "epsil": bool(parameters.get("epsil", False))}
    if parameters.get("purpose") == "epw": values["fildvscf"] = parameters.get("fildvscf", "dvscf")
    return serialize_namelist("INPUTPH", values) + "\n"

def raman_phonon_input(parameters: Mapping[str, Any], context) -> str:
    """Write the restricted QE 7.6 native Raman Gamma input."""
    q_point = parameters.get("q_point", (0.0, 0.0, 0.0))
    if tuple(float(v) for v in q_point) != (0.0, 0.0, 0.0):
        raise InvalidQEParameterError("Native Raman response is supported only at Gamma.")
    values = {
        "prefix": context.prefix, "outdir": context.outdir,
        "fildyn": parameters.get("fildyn", "raman.dyn"),
        "tr2_ph": parameters.get("tr2_ph"),
        "epsil": bool(parameters.get("epsil", True)),
        "trans": True, "lraman": True,
        "eth_rps": parameters.get("eth_rps", 1.0e-9),
        "eth_ns": parameters.get("eth_ns", 1.0e-12),
        "dek": parameters.get("dek", 1.0e-3),
        "fildrho": parameters.get("fildrho", "drho"),
        "ldisp": False,
    }
    return serialize_namelist("INPUTPH", values) + "\n0.0 0.0 0.0\n"

def polar_phonon_input(parameters: Mapping[str, Any], context) -> str:
    """Write the restricted E3B Gamma electric-response input for QE 7.6."""
    q_point = parameters.get("q_point", (0.0, 0.0, 0.0))
    if not isinstance(q_point, (list, tuple)) or len(q_point) != 3 or any(abs(float(item)) > 1.0e-12 for item in q_point):
        raise InvalidQEParameterError("Polar electric response is supported only at Gamma.")
    values = {"prefix": context.prefix, "outdir": context.outdir, "fildyn": parameters.get("fildyn", "polar_gamma"), "tr2_ph": parameters.get("tr2_ph"), "epsil": True, "zeu": True, "trans": True, "ldisp": False}
    return serialize_namelist("INPUTPH", values) + "\n0.0 0.0 0.0\n"
