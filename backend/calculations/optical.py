"""Public Optical Properties calculation definitions."""
from backend.calculations.definition import CalculationDefinition
from backend.calculations.registry import registry

_OPTICAL_PARAMETERS = (
    "energy_min_eV", "energy_max_eV", "number_of_points",
    "interband_broadening_eV", "intraband_broadening_eV",
    "optical_k_mesh", "optical_nbnd", "smeartype", "polarization_directions", "response_model", "carrier_regime", "dimensionality", "band_window_policy",
)

registry.register(CalculationDefinition(
    id="dielectric", name="Complex Dielectric Function", category="Optical Properties",
    description="Independent-particle complex dielectric tensor from one dense electronic state and QE epsilon.x.",
    requires=("scf",), workflow="optical.independent_particle", engine="quantum_espresso",
    tags=("optical", "dielectric", "independent-particle"), parameters=_OPTICAL_PARAMETERS,
    metadata={"derived_capabilities": ("absorption", "refractive_index", "reflectivity", "energy_loss", "optical_conductivity"),
              "scope": "Independent-particle RPA dielectric response; no excitons, BSE, GW, or local-field corrections."},
))
registry.register(CalculationDefinition(
    id="absorption", name="Optical Properties", category="Optical Properties",
    description="Complex dielectric response and derived n, kappa, absorption, normal-incidence reflectivity, and loss function.",
    requires=("dielectric",), workflow="optical.independent_particle", engine="quantum_espresso",
    tags=("optical", "absorption", "refractive-index", "reflectivity", "loss"), parameters=_OPTICAL_PARAMETERS,
))
