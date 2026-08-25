"""Deterministic Wannier90 .win and pw2wannier90 input writers."""
from __future__ import annotations
from collections.abc import Mapping
from backend.engines.qe.writer import format_number, serialize_namelist
from backend.engines.wannier90.models import WannierInputSettings

def uniform_kpoints(grid):
    return tuple((i / grid[0], j / grid[1], k / grid[2]) for i in range(grid[0]) for j in range(grid[1]) for k in range(grid[2]))

def win_input(settings: WannierInputSettings, structure: Mapping[str, object]) -> str:
    cell, atoms = structure.get("cell"), structure.get("atoms")
    if not isinstance(cell, list) or len(cell) != 3 or not isinstance(atoms, list) or not atoms:
        raise ValueError("Wannier input requires a non-empty request structure with a 3x3 cell.")
    scalars = {"num_bands": settings.num_bands, "num_wann": settings.num_wann, "dis_win_min": settings.dis_win_min, "dis_win_max": settings.dis_win_max, "dis_froz_min": settings.dis_froz_min, "dis_froz_max": settings.dis_froz_max, "num_iter": settings.num_iter, "dis_num_iter": settings.dis_num_iter, "spinors": settings.spinors if settings.spinors else None, "bands_plot": settings.bands_plot if settings.bands_plot else None, "bands_plot_format": settings.bands_plot_format}
    lines = [f"{key} = {str(value).lower() if isinstance(value, bool) else format_number(value) if isinstance(value, (int,float)) else value}" for key, value in sorted(scalars.items()) if value is not None]
    lines.extend(("", "begin unit_cell_cart", "angstrom"))
    lines.extend(" ".join(format_number(float(x)) for x in vector) for vector in cell)
    lines.extend(("end unit_cell_cart", "", "begin atoms_cart", "angstrom"))
    lines.extend(f"{atom['element']} {format_number(float(atom['x']))} {format_number(float(atom['y']))} {format_number(float(atom['z']))}" for atom in atoms)
    lines.extend(("end atoms_cart", "", f"mp_grid = {' '.join(str(item) for item in settings.mp_grid)}", "", "begin projections"))
    lines.extend(settings.projections)
    lines.extend(("end projections", "", "begin kpoints"))
    lines.extend(" ".join(format_number(value) for value in point) for point in uniform_kpoints(settings.mp_grid))
    lines.extend(("end kpoints", ""))
    return "\n".join(lines)

def pw2wannier90_input(prefix: str, outdir: str, seedname: str) -> str:
    return serialize_namelist("INPUTPP", {"prefix": prefix, "outdir": outdir, "seedname": seedname, "write_amn": True, "write_mmn": True}) + "\n"
