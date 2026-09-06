from types import SimpleNamespace
import unittest

from backend.execution.engine_family import EngineFamilyError, require_coherent_e5_family, resolve_epw_family


class EngineFamilyDiscoveryTests(unittest.TestCase):
    def test_existing_shared_epw_family_is_resolved(self):
        family = resolve_epw_family(explicit_root="/home/bhargava-kalapatapu/QuantumStudio/v0.1/software/engines")
        self.assertEqual(family.family, "QE_EP6")
        self.assertEqual(family.epw_version, "6.1")
        self.assertTrue(family.tools["epw"].as_posix().endswith("EPW/src/epw.x"))
        require_coherent_e5_family(family)
        self.assertEqual(len(family.manifest()["tools"]), 8)

    def test_incompatible_family_is_rejected(self):
        with self.assertRaises(EngineFamilyError):
            require_coherent_e5_family(SimpleNamespace(family="QE", qe_version="7.4.1", epw_version=""))

    def test_explicit_family_precedes_invalid_environment_root(self):
        family = resolve_epw_family(
            explicit_root="/home/bhargava-kalapatapu/QuantumStudio/v0.1/software/engines",
            environment={"QUANTUM_STUDIO_ENGINE_ROOT": "/does/not/exist"},
        )
        self.assertTrue(family.tools["ph"].as_posix().endswith("PHonon/PH/ph.x"))
