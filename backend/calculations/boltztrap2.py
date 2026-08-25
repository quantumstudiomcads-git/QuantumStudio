"""Public BTP2 transport intents; executable stages stay private to C5C."""
from backend.calculations.definition import CalculationDefinition
from backend.calculations.registry import registry

_SETTINGS = (
    "transport_k_mesh", "num_bands", "temperatures", "chemical_potentials",
    "chemical_potential_range", "carrier_concentrations", "carrier_concentration_range",
    "interpolation", "relaxation_time_model", "relaxation_time", "effective_thickness",
    "spin", "soc",
)

for _id, _name, _description in (
    ("boltztrap_bands", "Boltzmann Band Interpolation", "Interpolate electronic bands for transport calculations."),
    ("electrical_conductivity", "Electrical Conductivity", "Calculate temperature-dependent electrical conductivity."),
    ("seebeck", "Seebeck Coefficient", "Calculate thermoelectric Seebeck coefficient."),
    ("thermal_conductivity_electronic", "Electronic Thermal Conductivity", "Calculate electronic thermal conductivity."),
    ("power_factor", "Thermoelectric Power Factor", "Calculate thermoelectric power factor."),
    ("carrier_concentration", "Carrier Concentration", "Calculate carrier concentration versus chemical potential and temperature."),
):
    registry.register(CalculationDefinition(
        id=_id, name=_name, category="Boltzmann Transport", description=_description,
        requires=("scf",), workflow="boltztrap2.transport", engine="boltztrap2",
        tags=("boltztrap2", "transport"), parameters=_SETTINGS,
    ))
