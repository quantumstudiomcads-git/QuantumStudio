"""Public derived optical intents; all deduplicate onto the dielectric DAG."""
from backend.calculations.definition import CalculationDefinition
from backend.calculations.registry import registry

_PARAMETERS = (
    "energy_min_eV", "energy_max_eV", "number_of_points", "interband_broadening_eV",
    "intraband_broadening_eV", "optical_k_mesh", "optical_nbnd", "smeartype",
    "polarization_directions", "response_model", "carrier_regime", "dimensionality",
    "band_window_policy", "requested_derived_properties",
)

for _id, _name in (
    ("refractive_index", "Refractive Index"),
    ("extinction_coefficient", "Extinction Coefficient"),
    ("reflectivity", "Reflectivity"),
    ("energy_loss", "Energy-Loss Function"),
    ("optical_conductivity", "Optical Conductivity"),
):
    registry.register(CalculationDefinition(
        id=_id, name=_name, category="Optical Properties",
        description=f"{_name} derived from one shared complex dielectric workflow.",
        requires=("dielectric",), workflow="optical.independent_particle",
        engine="quantum_espresso", tags=("optical", "derived"), parameters=_PARAMETERS,
        metadata={"derived_from": "dielectric", "execution_deduplication": True},
    ))
