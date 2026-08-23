"""Surface plus adsorbate Device template."""

from __future__ import annotations

from frontend.device_builder.assembly import align_region_centers, place_region, translate_region
from frontend.device_builder.model import Device, DeviceRegion, RegionRole

from .base import DeviceTemplate, TemplateBuildResult, finalize_template_device, finite_vector, nonnegative_finite, require_structure


class SurfaceAdsorbateTemplate(DeviceTemplate):
    id = "surface_adsorbate"
    name = "Surface + Adsorbate"
    description = "A substrate and independently transformed adsorbate with controlled placement."
    required_inputs = ("substrate_structure", "adsorbate_structure", "separation")

    def validate(self, **parameters) -> None:
        require_structure(parameters.get("substrate_structure"), "Substrate structure")
        require_structure(parameters.get("adsorbate_structure"), "Adsorbate structure")
        nonnegative_finite(parameters.get("separation", 3.0), "Vertical separation")
        finite_vector(parameters.get("padding", (5.0, 5.0, 8.0)), "Padding", nonnegative=True)
        finite_vector(parameters.get("rotation", (0.0, 0.0, 0.0)), "Adsorbate rotation")
        finite_vector((parameters.get("offset_x", 0.0), parameters.get("offset_y", 0.0), 0.0), "Lateral offset")

    def build(self, **parameters) -> TemplateBuildResult:
        self.validate(**parameters)
        padding = finite_vector(parameters.get("padding", (5.0, 5.0, 8.0)), "Padding", nonnegative=True)
        rotation = finite_vector(parameters.get("rotation", (0.0, 0.0, 0.0)), "Adsorbate rotation")
        offset_x = float(parameters.get("offset_x", 0.0))
        offset_y = float(parameters.get("offset_y", 0.0))
        separation = float(parameters.get("separation", 3.0))
        device = Device(name=str(parameters.get("name", self.name)), padding=padding)
        substrate = device.add_region(DeviceRegion(parameters["substrate_structure"].copy(), name="Substrate", role=RegionRole.SUBSTRATE))
        adsorbate = device.add_region(DeviceRegion(
            parameters["adsorbate_structure"].copy(), name="Adsorbate", role=RegionRole.ADSORBATE, rotation=rotation,
        ))
        # Deterministic order: rotated adsorbate, XY centers, requested lateral offset, then Z gap.
        align_region_centers(adsorbate, substrate, "XY")
        translate_region(adsorbate, (offset_x, offset_y, 0.0))
        place_region(adsorbate, substrate, "above", separation)
        return finalize_template_device(
            device, self,
            parameters={"separation": separation, "offset_x": offset_x, "offset_y": offset_y,
                        "rotation": list(rotation), "padding": list(padding)},
            padding=padding,
        )
