"""Metal / barrier / metal tunnel-junction Device template."""

from __future__ import annotations

from frontend.device_builder.model import RegionRole

from .base import DeviceTemplate, TemplateBuildResult, finite_vector, nonnegative_finite, require_structure
from .two_probe import build_lateral_three_region_device


class TunnelJunctionTemplate(DeviceTemplate):
    id = "tunnel_junction"
    name = "Tunnel Junction"
    description = "Two electrodes separated by a semantic dielectric barrier along X."
    required_inputs = ("left_structure", "barrier_structure", "right_structure", "left_gap", "right_gap")

    def validate(self, **parameters) -> None:
        require_structure(parameters.get("left_structure"), "Left electrode structure")
        require_structure(parameters.get("barrier_structure"), "Barrier structure")
        require_structure(parameters.get("right_structure"), "Right electrode structure")
        nonnegative_finite(parameters.get("left_gap", 3.0), "Left interface gap")
        nonnegative_finite(parameters.get("right_gap", 3.0), "Right interface gap")
        finite_vector(parameters.get("padding", (5.0, 5.0, 5.0)), "Padding", nonnegative=True)
        if str(parameters.get("transport_direction", "X")).upper() != "X":
            raise ValueError("Tunnel Junction currently supports X transport only.")

    def build(self, **parameters) -> TemplateBuildResult:
        self.validate(**parameters)
        padding = finite_vector(parameters.get("padding", (5.0, 5.0, 5.0)), "Padding", nonnegative=True)
        result = build_lateral_three_region_device(
            name=str(parameters.get("name", self.name)),
            left_structure=parameters["left_structure"], center_structure=parameters["barrier_structure"],
            right_structure=parameters["right_structure"],
            left_gap=float(parameters.get("left_gap", 3.0)), right_gap=float(parameters.get("right_gap", 3.0)),
            padding=padding, center_role=RegionRole.DIELECTRIC, provenance_template=self,
            provenance_parameters={"left_gap": float(parameters.get("left_gap", 3.0)),
                                   "right_gap": float(parameters.get("right_gap", 3.0)),
                                   "transport_direction": "X", "padding": list(padding)},
        )
        result.device.regions[0].name = "Left Electrode"
        result.device.regions[1].name = "Barrier"
        result.device.regions[2].name = "Right Electrode"
        return result
