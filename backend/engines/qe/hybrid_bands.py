"""Verified direct-EXX hybrid band-path support for QE ADDITIONAL_K_POINTS."""
from __future__ import annotations
from typing import Mapping, Sequence
from .models import InvalidQEParameterError

def _mesh(value, periodic):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise InvalidQEParameterError("Hybrid EXX q mesh requires exactly three integers.")
    mesh = tuple(int(item) for item in value)
    if any(item < 1 for item in mesh) or tuple(value) != mesh:
        raise InvalidQEParameterError("Hybrid EXX q mesh values must be positive integers.")
    if isinstance(periodic, Sequence) and len(periodic) == 3:
        for axis, enabled in enumerate(periodic):
            if not enabled and mesh[axis] != 1:
                raise InvalidQEParameterError("Hybrid EXX q mesh must be 1 along a non-periodic axis.")
    return mesh

def interpolate_band_path(path):
    if not isinstance(path, list) or len(path) < 2:
        raise InvalidQEParameterError("Hybrid bands require an explicit ordered path with at least two points.")
    points=[]
    for item in path:
        if not isinstance(item, Mapping) or not isinstance(item.get("coordinates"), (list, tuple)) or len(item["coordinates"]) != 3:
            raise InvalidQEParameterError("Hybrid band-path points require three reciprocal fractional coordinates.")
        count=int(item.get("points", 0))
        if count < 1: raise InvalidQEParameterError("Hybrid band-path interpolation counts must be positive.")
        points.append((str(item.get("label", "")), tuple(float(x) for x in item["coordinates"]), count))
    visible=[]
    for index, (_, start, _) in enumerate(points[:-1]):
        _, end, count=points[index+1]
        for step in range(count):
            fraction=step/count
            visible.append(tuple(start[axis] + fraction*(end[axis]-start[axis]) for axis in range(3)))
    visible.append(points[-1][1])
    return tuple(visible)

def exx_support_points(visible, mesh):
    """Mirror QE Modules/additional_kpoints.f90: visible k + i/nqx1,j/nqx2,k/nqx3."""
    return tuple(tuple(point[axis] + shift[axis] for axis in range(3)) for shift in ((i/mesh[0], j/mesh[1], k/mesh[2]) for i in range(mesh[0]) for j in range(mesh[1]) for k in range(mesh[2])) for point in visible)

def hybrid_band_contract(path, exx_q_mesh, periodic):
    mesh=_mesh(exx_q_mesh, periodic)
    visible=interpolate_band_path(path)
    return {"method":"direct_exx_additional_k_points", "visible_points":visible, "exx_support_points":exx_support_points(visible, mesh), "exx_q_mesh":mesh}

def additional_k_points_card(contract):
    rows=[" ".join(format(value, ".12g") for value in point)+" 0.0" for point in contract["visible_points"]]
    return "ADDITIONAL_K_POINTS crystal\n"+str(len(rows))+"\n"+"\n".join(rows)
