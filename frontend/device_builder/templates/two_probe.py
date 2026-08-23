"""Lateral three-region Device template."""

from __future__ import annotations

from frontend.device_builder.assembly import align_region_centers, place_region
from frontend.device_builder.model import Device, DeviceRegion, RegionRole

from .base import DeviceTemplate, TemplateBuildResult, finalize_template_device, finite_vector, nonnegative_finite, require_structure


def build_lateral_three_region_device(*, name, left_structure, center_structure, right_structure,
                                      left_gap, right_gap, padding, center_role, provenance_template,
                                      provenance_parameters):
    """Compose Stage 2 placement primitives for ordered X-direction regions."""
    device = Device(name=name, transport_direction="X", padding=padding)
    left = device.add_region(DeviceRegion(left_structure.copy(), name="Left", role=RegionRole.ELECTRODE))
    center = device.add_region(DeviceRegion(center_structure.copy(), name="Center", role=center_role))
    right = device.add_region(DeviceRegion(right_structure.copy(), name="Right", role=RegionRole.ELECTRODE))
    align_region_centers(left, center, "YZ")
    place_region(left, center, "left", left_gap)
    align_region_centers(right, center, "YZ")
    place_region(right, center, "right", right_gap)
    return finalize_template_device(device, provenance_template, parameters=provenance_parameters, padding=padding)


class LateralTwoProbeTemplate(DeviceTemplate):
    id = "lateral_two_probe"
    name = "Lateral Two-Probe"
    description = "Left electrode, channel, and right electrode arranged along X."
    required_inputs = ("left_structure", "center_structure", "right_structure", "left_gap", "right_gap")

    def validate(self, **parameters) -> None:
        require_structure(parameters.get("left_structure"), "Left structure")
        require_structure(parameters.get("center_structure"), "Center structure")
        require_structure(parameters.get("right_structure"), "Right structure")
        nonnegative_finite(parameters.get("left_gap", 3.0), "Left gap")
        nonnegative_finite(parameters.get("right_gap", 3.0), "Right gap")
        finite_vector(parameters.get("padding", (5.0, 5.0, 5.0)), "Padding", nonnegative=True)
        if str(parameters.get("transport_direction", "X")).upper() != "X":
            raise ValueError("Lateral Two-Probe currently supports X transport only.")

    def build(self, **parameters) -> TemplateBuildResult:
        self.validate(**parameters)
        padding = finite_vector(parameters.get("padding", (5.0, 5.0, 5.0)), "Padding", nonnegative=True)
        return build_lateral_three_region_device(
            name=str(parameters.get("name", self.name)),
            left_structure=parameters["left_structure"], center_structure=parameters["center_structure"],
            right_structure=parameters["right_structure"],
            left_gap=float(parameters.get("left_gap", 3.0)), right_gap=float(parameters.get("right_gap", 3.0)),
            padding=padding, center_role=RegionRole.CHANNEL, provenance_template=self,
            provenance_parameters={"left_gap": float(parameters.get("left_gap", 3.0)),
                                   "right_gap": float(parameters.get("right_gap", 3.0)),
                                   "transport_direction": "X", "padding": list(padding)},
        )
