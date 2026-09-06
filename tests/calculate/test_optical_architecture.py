import unittest

import numpy as np

import backend.calculations  # register the public optical intents
from backend.calculations.registry import registry
from backend.compiler.calculation_compiler import CalculationCompiler
from backend.core.calculation_request import CalculationRequest
from backend.optical import (
    BandWindowPolicy, CarrierRegime, Dimensionality, OpticalCalculationSpecification,
    OpticalConvergencePolicy, OpticalWorkflowRouter, SystemCharacterization,
    assess_band_coverage, compare_optical_spectra, full_bz_grid, validate_full_bz_grid,
)
from backend.optical.derived import optical_conductivity


class OpticalArchitectureTests(unittest.TestCase):
    def test_rectangular_grid_is_complete_and_uniform(self):
        points = full_bz_grid((2, 3, 4))
        report = validate_full_bz_grid((2, 3, 4), points)
        self.assertEqual(len(points), 24)
        self.assertTrue(report.valid)

    def test_specification_round_trip_is_qt_free(self):
        spec = OpticalCalculationSpecification(
            dimensionality=Dimensionality.SLAB_2D_SUPERCELL,
            carrier_regime=CarrierRegime.METAL,
            band_window_policy=BandWindowPolicy.EXPLICIT_NBND,
            optical_k_mesh=(4, 5, 6), optical_nbnd=32,
        )
        self.assertEqual(OpticalCalculationSpecification.from_dict(spec.to_dict()), spec)

    def test_router_gates_unverified_metal_and_soc_routes(self):
        router = OpticalWorkflowRouter()
        with self.assertRaisesRegex(ValueError, "metallic"):
            router.route(OpticalCalculationSpecification(carrier_regime=CarrierRegime.METAL), SystemCharacterization(carrier_regime=CarrierRegime.METAL))
        with self.assertRaisesRegex(ValueError, "SOC"):
            router.route(OpticalCalculationSpecification(soc=True), SystemCharacterization(soc=True))

    def test_band_coverage_is_explicit_and_conservative(self):
        result = assess_band_coverage(occupied_band_count=4, nbnd=16, requested_max_energy_eV=15, highest_available_transition_coverage_eV=16, margin_eV=0.5)
        self.assertTrue(result.adequate)
        self.assertEqual(result.unoccupied_band_count, 12)

    def test_derived_optical_quantities_use_one_shared_spectrum(self):
        e = np.array([0.0, 1.0])
        sigma1, sigma2 = optical_conductivity(e, np.array([2.0, 2.0]), np.array([0.0, 1.0]))
        self.assertEqual(sigma1[0], 0.0)
        self.assertTrue(np.all(np.isfinite(sigma2)))

    def test_convergence_metrics_avoid_pointwise_zero_division(self):
        metrics = compare_optical_spectra([0, 1], [0, 1], [0, 1], [0, 1], [0, 1], [0, 1])
        self.assertEqual(metrics["epsilon1_normalized_l2"], 0.0)
        self.assertEqual(metrics["integrated_epsilon2_relative"], 0.0)

    def test_derived_public_intents_share_one_dielectric_definition(self):
        for calculation_id in ("refractive_index", "extinction_coefficient", "reflectivity", "energy_loss", "optical_conductivity"):
            self.assertEqual(registry.get(calculation_id).requires, ("dielectric",))

    def test_selected_derived_intent_compiles_one_optical_engine_pair(self):
        request = CalculationRequest(
            id="optical-derived-test", structure={"atoms": [], "cell": []},
            selected_calculations=["optical_conductivity"], parameters={"pseudopotentials": {}},
        )
        plan = CalculationCompiler(request).compile()
        self.assertEqual([task.calculation_id for task in plan.tasks].count("qe_pw_nscf_optical"), 1)
        self.assertEqual([task.calculation_id for task in plan.tasks].count("qe_epsilon"), 1)

    def test_convergence_policy_is_independent_and_bounded(self):
        policy = OpticalConvergencePolicy(sequences={"K_MESH": ((4, 4, 4), (6, 6, 6))})
        self.assertEqual(policy.to_dict()["max_steps"], 4)
        self.assertIn("NBND", policy.to_dict()["dimensions"])
