import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from backend.update.manifest import parse_manifest
from backend.update.signing import UpdateVerifier, b64url_decode

REPO = Path(__file__).resolve().parents[2]


class B6ReleaseBuilderTests(unittest.TestCase):
    def test_dry_run_generates_two_platform_records_and_ephemeral_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); windows = root / "input.exe"; linux = root / "input.AppImage"; engine = root / "2026.09.1.tar.zst"
            windows.write_bytes(b"windows"); linux.write_bytes(b"linux"); engine.write_bytes(b"engine")
            command = [sys.executable, "scripts/build_release.py", "--dry-run", "--version", "0.2.1-beta.1", "--channel", "beta",
                       "--base-url", "https://updates.example.test/beta/0.2.1-beta.1", "--windows-artifact", str(windows),
                       "--linux-artifact", str(linux), "--engine-pack", str(engine), "--output", str(root / "release")]
            completed = subprocess.run(command, cwd=REPO, capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout); manifest_path = Path(result["manifest"]); manifest = json.loads(manifest_path.read_text())
            parsed = parse_manifest(manifest, UpdateVerifier({"dry-run-ephemeral": b64url_decode(result["public_key"])}))
            self.assertEqual(set(parsed.platforms), {"windows-x86_64", "linux-x86_64"})
            self.assertEqual(parsed.engine_pack.version, "2026.09.1")
            self.assertTrue((manifest_path.parent / "SHA256SUMS").is_file())

    def test_production_build_fails_without_external_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); windows = root / "input.exe"; linux = root / "input.AppImage"; windows.write_bytes(b"windows"); linux.write_bytes(b"linux")
            completed = subprocess.run([sys.executable, "scripts/build_release.py", "--version", "0.2.1-beta.1", "--channel", "beta", "--base-url", "https://updates.example.test", "--windows-artifact", str(windows), "--linux-artifact", str(linux), "--output", str(root / "release")], cwd=REPO, capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, 2); self.assertIn("PRODUCTION_UPDATE_SIGNING_MATERIAL_MISSING", completed.stderr)
