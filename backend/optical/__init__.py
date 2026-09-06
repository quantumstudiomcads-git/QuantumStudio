"""Qt-free optical workflow contracts and scientific routing."""

from .grid import OpticalGridError, full_bz_grid, validate_full_bz_grid
from .models import (
    BandWindowPolicy,
    CarrierRegime,
    Dimensionality,
    OpticalCalculationSpecification,
    OpticalCapabilityMatrix,
    OpticalRoute,
    OpticalWorkflowRouter,
    ResponseModel,
    SystemCharacterization,
)
from .coverage import OpticalBandCoverage, assess_band_coverage
from .convergence import OpticalConvergencePolicy, compare_optical_spectra
from .derived import optical_conductivity, dimensionality_warning
from .bundle import OpticalResultBundle

__all__ = [
    "BandWindowPolicy", "CarrierRegime", "Dimensionality",
    "OpticalCalculationSpecification", "OpticalCapabilityMatrix",
    "OpticalRoute", "OpticalWorkflowRouter", "ResponseModel",
    "SystemCharacterization", "OpticalBandCoverage", "assess_band_coverage",
    "OpticalConvergencePolicy", "compare_optical_spectra", "OpticalGridError",
    "full_bz_grid", "validate_full_bz_grid", "optical_conductivity", "dimensionality_warning", "OpticalResultBundle",
]
