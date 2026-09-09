from types import SimpleNamespace
import unittest
import tempfile
from pathlib import Path

from backend.execution.engine_family import EngineFamilyError, require_coherent_e5_family, resolve_epw_family


class EngineFamilyDiscoveryTests(unittest.TestCase):
    def family_root(self):
        root = Path(tempfile.mkdtemp()) / "engines" / "epw" / "epw-6.1"
        for relative in ("PW/src/pw.x", "PHonon/PH/ph.x", "PHonon/PH/q2r.x", "PHonon/PH/matdyn.x", "PP/src/epsilon.x", "PP/src/pw2wannier90.x", "wannier90/bin/wannier90.x", "EPW/src/epw.x"):
            path = root / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b"fixture"); path.chmod(0o755)
        return root.parent.parent

    def test_existing_shared_epw_family_is_resolved(self):
        family = resolve_epw_family(explicit_root=self.family_root())
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
            explicit_root=self.family_root(),
            environment={"QUANTUM_STUDIO_ENGINE_ROOT": "/does/not/exist"},
        )
        self.assertTrue(family.tools["ph"].as_posix().endswith("PHonon/PH/ph.x"))
