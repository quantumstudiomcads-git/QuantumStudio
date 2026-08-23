"""Vertical two-region Device template."""

from __future__ import annotations

from math import isfinite

from frontend.device_builder.assembly import align_region_centers, place_region
from frontend.device_builder.model import Device, DeviceRegion, InterfaceMode, RegionRole

from .base import DeviceTemplate, TemplateBuildResult, finalize_template_device, finite_vector, nonnegative_finite, require_structure


class VerticalStackTemplate(DeviceTemplate):
    id = "vertical_stack"
    name = "Vertical Stack"
    description = "Two atomistic regions stacked along Z with an optional commensurate interface match."
    required_inputs = ("bottom_structure", "top_structure", "gap")

    def validate(self, **parameters) -> None:
        require_structure(parameters.get("bottom_structure"), "Bottom structure")
        require_structure(parameters.get("top_structure"), "Top structure")
        nonnegative_finite(parameters.get("gap", 3.0), "Gap")
        finite_vector(parameters.get("padding", (5.0, 5.0, 5.0)), "Padding", nonnegative=True)
        if bool(parameters.get("interface_matching", False)):
            # Import only when the explicit scientific interface feature is requested.
            # The ordinary template-domain package stays Qt-free at import time.
            from frontend.device_builder.interface import apply_interface_match, prepare_interface_match

            twist = float(parameters.get("twist_angle_deg", 0.0))
            max_strain = nonnegative_finite(parameters.get("max_strain", 0.05), "Maximum strain")
            max_index = int(parameters.get("max_index", 3))
            if not isfinite(twist):
                raise ValueError("Twist angle must be finite.")
            if max_index < 1:
                raise ValueError("Maximum index must be at least 1.")
            if str(parameters.get("strain_mode", "balanced")).lower() not in {"balanced", "bottom", "top"}:
                raise ValueError("Strain mode must be balanced, bottom, or top.")
            _ = max_strain

    def build(self, **parameters) -> TemplateBuildResult:
        self.validate(**parameters)
        bottom = parameters["bottom_structure"]
        top = parameters["top_structure"]
        gap = float(parameters.get("gap", 3.0))
        padding = finite_vector(parameters.get("padding", (5.0, 5.0, 5.0)), "Padding", nonnegative=True)
        device = Device(name=str(parameters.get("name", self.name)), padding=padding)
        region_bottom = device.add_region(DeviceRegion(bottom.copy(), name=str(parameters.get("bottom_name", "Bottom")), role=RegionRole.ACTIVE_LAYER))
        region_top = device.add_region(DeviceRegion(top.copy(), name=str(parameters.get("top_name", "Top")), role=RegionRole.ACTIVE_LAYER))
        interface_diagnostics = None
        if bool(parameters.get("interface_matching", False)):
            # Import only when the explicit scientific interface feature is requested.
            # The ordinary template-domain package stays Qt-free at import time.
            from frontend.device_builder.interface import apply_interface_match, prepare_interface_match

            twist = float(parameters.get("twist_angle_deg", 0.0))
            mode = InterfaceMode.ALIGNED if abs(twist) <= 1.0e-12 else InterfaceMode.TWISTED
            match = prepare_interface_match(
                region_bottom, region_top, mode=mode, requested_twist_deg=twist,
                max_strain=float(parameters.get("max_strain", 0.05)),
                strain_mode=str(parameters.get("strain_mode", "balanced")).lower(),
                gap=gap, max_index=int(parameters.get("max_index", 3)),
            )
            interface = apply_interface_match(device, match, fit_cell_after_match=False)
            interface_diagnostics = dict(interface.diagnostics)
        else:
            align_region_centers(region_top, region_bottom, "XY")
            place_region(region_top, region_bottom, "above", gap)
        result = finalize_template_device(
            device, self,
            parameters={
                "gap": gap, "interface_matching": bool(parameters.get("interface_matching", False)),
                "twist_angle_deg": float(parameters.get("twist_angle_deg", 0.0)),
                "max_strain": float(parameters.get("max_strain", 0.05)),
                "max_index": int(parameters.get("max_index", 3)),
                "strain_mode": str(parameters.get("strain_mode", "balanced")).lower(),
                "padding": list(padding),
            },
            padding=padding,
        )
        return TemplateBuildResult(
            device=result.device, warnings=result.warnings, atom_count=result.atom_count,
            collisions=result.collisions, interface_diagnostics=interface_diagnostics,
        )
