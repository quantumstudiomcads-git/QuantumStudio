import unittest
from backend.engines.epw.scdm import SCDMParameterFit, erfc_projectability, SCDMContractError, validate_scdm_contract


class W10SCDMTests(unittest.TestCase):
    def test_erfc_sign_and_derived_parameters(self):
        fit = SCDMParameterFit("projwfc", 10, -1, 2, 10, 2, .01, .99)
        self.assertGreater(erfc_projectability(8, 10, 2), erfc_projectability(12, 10, 2))
        self.assertEqual(fit.mu_scdm_eV, 4.0)
        self.assertEqual(fit.sigma_scdm_eV, 2.0)

    def test_scdm_contract_rejects_mixed_modes(self):
        with self.assertRaises(SCDMContractError):
            validate_scdm_contract(num_wann=9, auto_projections=True, scdm_proj=True, entanglement="erfc", mu_eV=1, sigma_eV=1, manual_projections=True)


    def test_fit_round_trip_and_identity_rejects_changed_provenance(self):
        fit = SCDMParameterFit("projwfc", 3024, -5.59518, 30.58695, 16.90983972, 1.93848604, .113211, .940804)
        restored = SCDMParameterFit.from_dict(fit.to_dict())
        self.assertEqual(restored, fit)
        self.assertEqual(restored.identity, fit.identity)
        changed = SCDMParameterFit("other", 3024, -5.59518, 30.58695, 16.90983972, 1.93848604, .113211, .940804)
        self.assertNotEqual(changed.identity, fit.identity)

    def test_scdm_contract_requires_positive_sigma(self):
        with self.assertRaises(SCDMContractError):
            validate_scdm_contract(num_wann=9, auto_projections=True, scdm_proj=True, entanglement="erfc", mu_eV=1, sigma_eV=0)


if __name__ == "__main__":
    unittest.main()
