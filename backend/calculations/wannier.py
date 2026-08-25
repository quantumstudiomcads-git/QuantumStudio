"""Public Wannierization definition; detailed stages are private workflow tasks."""
from backend.calculations.definition import CalculationDefinition
from backend.calculations.registry import registry

registry.register(CalculationDefinition(
    id="wannierization", name="Wannierization", category="Wannier & Berry Properties",
    description="Construct maximally localized Wannier functions through a QE/Wannier90 workflow.",
    requires=("scf",), workflow="wannier90.wannierization", engine="wannier90",
    tags=("wannier",), parameters=("num_wann", "num_bands", "projections", "mp_grid", "dis_win_min", "dis_win_max", "dis_froz_min", "dis_froz_max", "num_iter", "dis_num_iter", "spinors", "bands_plot", "bands_plot_format"),
))
