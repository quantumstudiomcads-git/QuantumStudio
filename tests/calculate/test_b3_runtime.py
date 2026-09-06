import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from backend.runtime import PRODUCT_NAME, VERSION, build_identity, runtime_paths
from backend.runtime.engine_pack import validate_engine_pack


class B3RuntimeTests(unittest.TestCase):
    def test_identity_is_single_and_checkout_independent(self):
        identity = build_identity()
        self.assertEqual(identity["product"], PRODUCT_NAME)
        self.assertEqual(identity["version"], VERSION)
        self.assertTrue(identity["python"])

    def test_runtime_paths_are_isolated_and_user_writable(self):
        with tempfile.TemporaryDirectory() as home:
            paths = runtime_paths(home=home, environ={})
            self.assertNotEqual(paths.data, Path.cwd())
            paths.ensure_user_dirs()
            self.assertTrue(paths.logs.is_dir())
            self.assertTrue(paths.pseudos.is_dir())

    def test_environment_overrides_are_respected(self):
        with tempfile.TemporaryDirectory() as root:
            paths = runtime_paths(home="/not-used", environ={"QUANTUM_STUDIO_DATA_ROOT": root, "QUANTUM_STUDIO_WORKFLOW_ROOT": root + "/wf"})
            self.assertEqual(paths.data, Path(root))
            self.assertEqual(paths.workflows, Path(root) / "wf")

    def test_engine_pack_manifest_hash_and_relocation(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            for root in (Path(first), Path(second)):
                binary = root / "bin" / "pw.x"
                binary.parent.mkdir(parents=True)
                binary.write_bytes(b"fake-engine")
                digest = hashlib.sha256(binary.read_bytes()).hexdigest()
                (root / "engine-pack.json").write_text(json.dumps({"schema_version": "1", "engine_pack_version": "test", "platform": "linux", "architecture": "x86_64", "engines": [{"family": "qe", "executable": "pw.x", "relative_path": "bin/pw.x", "sha256": digest}]}))
            self.assertTrue(validate_engine_pack(first, platform_name="linux", architecture="x86_64").valid)
            self.assertTrue(validate_engine_pack(second, platform_name="linux", architecture="x86_64").valid)

    def test_engine_pack_hash_mismatch_and_missing_pack_are_safe(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "engine-pack.json").write_text(json.dumps({"schema_version": "1", "engine_pack_version": "test", "platform": "linux", "architecture": "x86_64", "engines": [{"executable": "pw.x", "relative_path": "bin/pw.x", "sha256": "bad"}]}))
            self.assertFalse(validate_engine_pack(root, platform_name="linux", architecture="x86_64").valid)
            self.assertFalse(validate_engine_pack(Path(root) / "missing", platform_name="linux", architecture="x86_64").valid)

    def test_desktop_metadata_has_no_developer_path_and_qs_association(self):
        desktop = Path("launcher/quantum-studio.desktop").read_text()
        self.assertIn("Name=Quantum Studio", desktop)
        self.assertIn("*.qs", Path("launcher/quantum-studio-project.xml").read_text())
        self.assertNotIn("/home/", desktop)
