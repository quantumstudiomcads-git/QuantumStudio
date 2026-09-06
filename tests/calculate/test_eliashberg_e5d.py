import unittest
import numpy as np

from backend.results.eliashberg import (
    allen_dynes_factors, allen_dynes_tc, cumulative_lambda, is_converged,
    lambda_integral, mcmillan_tc, omega_2, omega_log, relative_change,
    transition_temperature, MuStarAssumption,
)


class EliashbergE5DTests(unittest.TestCase):
    def setUp(self):
        self.w = np.array([0.0, 1.0, 2.0, 3.0])
        self.a = np.array([0.0, 1.0, 1.0, 1.0])

    def test_spectral_integrals_and_cumulative(self):
        self.assertAlmostEqual(lambda_integral(self.w, self.a), 3.333333333333333)
        self.assertTrue(np.all(np.diff(cumulative_lambda(self.w, self.a)) >= 0))
        self.assertGreater(omega_log(self.w, self.a), 0.0)
        self.assertGreater(omega_2(self.w, self.a), 0.0)

    def test_consecutive_relative_convergence(self):
        self.assertAlmostEqual(relative_change(1.0, 1.01), 0.01/1.01)
        self.assertTrue(is_converged(1.0, 1.01, 0.01))
        self.assertFalse(is_converged(1.0, 1.02, 0.01))

    def test_mcmillan_and_allen_dynes_are_distinct_methods(self):
        args = (1.0, 20.0, 25.0, 0.10)
        self.assertGreater(mcmillan_tc(args[0], args[1], args[3]), 0.0)
        f1, f2 = allen_dynes_factors(*args)
        self.assertGreaterEqual(f1, 1.0)
        self.assertGreaterEqual(f2, 1.0)
        self.assertGreater(allen_dynes_tc(*args), 0.0)

    def test_mu_star_provenance_and_transition(self):
        self.assertEqual(MuStarAssumption().source, "USER/MODEL_ASSUMPTION")
        tc, bracket = transition_temperature([1, 2, 3], [0.8, 1.2, 1.3])
        self.assertAlmostEqual(tc, 1.5)
        self.assertEqual(bracket, (1.0, 2.0))


if __name__ == "__main__":
    unittest.main()
