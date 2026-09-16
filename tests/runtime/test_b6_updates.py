import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.release import ReleaseVersion, ReleaseVersionError
from backend.runtime.paths import RuntimePaths
from backend.update.client import UpdateClient
from backend.update.models import UpdateErrorCode, UpdateState
from backend.update.signing import UpdateSigner, UpdateVerifier
from backend.update.transport import FileUpdateSource, HttpsUpdateSource


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def artifact(path, *, platform, artifact_type="installer", engine=False):
    return {"filename": path.name, "url": f"beta/{path.name}", "size": path.stat().st_size, "sha256": digest(path),
            "artifact_type": artifact_type, "platform": platform, "architecture": "x86_64",
            **({"version": "2026.09.1", "minimum_runtime_schema": 1, "maximum_runtime_schema": 1} if engine else {})}


class B6UpdateTests(unittest.TestCase):
    def setUp(self):
        self.private = Ed25519PrivateKey.generate()
        self.signer = UpdateSigner(self.private, kid="test-2026")
        self.verifier = UpdateVerifier({"test-2026": self.signer.public_key_bytes()})

    def write_manifest(self, root, *, version="0.2.1-beta.1", tamper=False):
        channel = root / "beta"; channel.mkdir(parents=True)
        windows = channel / "QuantumStudio-Windows.exe"; linux = channel / "QuantumStudio-Linux.AppImage"; engine = channel / "EnginePack.tar.zst"
        windows.write_bytes(b"windows N+1"); linux.write_bytes(b"linux N+1"); engine.write_bytes(b"shared linux engine pack")
        records = {"windows-x86_64": artifact(windows, platform="windows-x86_64"), "linux-x86_64": artifact(linux, platform="linux-x86_64", artifact_type="appimage")}
        for record in records.values(): record.update(self.signer.sign_envelope(record))
        engine_record = artifact(engine, platform="linux-x86_64", artifact_type="engine-pack", engine=True); engine_record.update(self.signer.sign_envelope(engine_record))
        payload = {"schema_version": 1, "channel": "beta", "version": version, "published_at": "2026-09-16T00:00:00Z",
                   "minimum_supported_version": "0.2.0", "mandatory": False, "release_notes_url": "https://updates.example.test/notes",
                   "release_notes_summary": "Test update", "platforms": records, "engine_pack": engine_record}
        payload.update(self.signer.sign_envelope(payload))
        if tamper: payload["version"] = "9.9.9-beta.1"
        (channel / "release-manifest.json").write_text(json.dumps(payload), encoding="utf-8")
        return payload

    def client(self, root, platform="windows-x86_64", **kwargs):
        paths = RuntimePaths(root / "config", root / "data", root / "cache", root / "workflows", root / "logs", root / "pseudos", root / "engines")
        return UpdateClient(FileUpdateSource(root), self.verifier, current_version="0.2.0", platform=platform, channel="beta", paths=paths, **kwargs)

    def test_version_order_and_channel_rules(self):
        self.assertLess(ReleaseVersion.parse("0.2.1-beta.1"), ReleaseVersion.parse("0.2.1"))
        self.assertLess(ReleaseVersion.parse("0.2.1-beta.1"), ReleaseVersion.parse("0.2.1-beta.2"))
        with self.assertRaises(ReleaseVersionError): ReleaseVersion.parse("0.2")
        with self.assertRaises(ReleaseVersionError): ReleaseVersion.validate_channel("0.2.1-beta.1", "stable")

    def test_platform_selection_shared_engine_and_atomic_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.write_manifest(root)
            win = self.client(root); linux = self.client(root, "linux-x86_64")
            checked, linux_checked = win.check(), linux.check()
            self.assertTrue(checked.available); self.assertEqual(checked.app_artifact.platform, "windows-x86_64")
            self.assertEqual(linux_checked.app_artifact.platform, "linux-x86_64")
            self.assertEqual(checked.engine_pack.version, linux_checked.engine_pack.version)
            staged = win.stage_application(checked)
            self.assertTrue(staged.path.is_file()); self.assertFalse(staged.path.with_name(staged.path.name + ".partial").exists())
            self.assertEqual(json.loads(win.state_path.read_text())["state"], UpdateState.READY_TO_INSTALL.value)

    def test_invalid_signature_checksum_and_downgrade_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.write_manifest(root, tamper=True)
            result = self.client(root).check()
            self.assertEqual(result.state, UpdateState.FAILED); self.assertEqual(result.error.code, UpdateErrorCode.SIGNATURE_INVALID)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.write_manifest(root, version="0.1.9-beta.1")
            self.assertEqual(self.client(root).check().state, UpdateState.UP_TO_DATE)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); data = self.write_manifest(root); data["platforms"]["windows-x86_64"]["sha256"] = "0" * 64
            for record in data["platforms"].values(): record.update(self.signer.sign_envelope(record))
            data.update(self.signer.sign_envelope(data)); (root / "beta" / "release-manifest.json").write_text(json.dumps(data))
            result = self.client(root).check()
            with self.assertRaisesRegex(Exception, "checksum"):
                self.client(root).stage_application(result)

    def test_https_source_rejects_non_https_production_endpoint(self):
        with self.assertRaises(ValueError): HttpsUpdateSource("http://localhost/releases")

    def test_engine_update_can_be_selected_without_desktop_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.write_manifest(root, version="0.2.0")
            result = self.client(root, current_engine_pack_version="2026.08.9").check()
            self.assertTrue(result.available)
            self.assertIsNone(result.app_artifact)
            self.assertEqual(result.engine_pack.version, "2026.09.1")
            staged = self.client(root, current_engine_pack_version="2026.08.9").stage_engine_pack(result)
            self.assertTrue(staged.path.is_file())

    def test_wrong_platform_and_schema_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); data = self.write_manifest(root); data["schema_version"] = 2; data.update(self.signer.sign_envelope(data))
            (root / "beta" / "release-manifest.json").write_text(json.dumps(data))
            result = self.client(root).check(); self.assertEqual(result.error.code, UpdateErrorCode.UNSUPPORTED_SCHEMA)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.write_manifest(root)
            result = self.client(root, platform="linux-aarch64").check(); self.assertEqual(result.error.code, UpdateErrorCode.UNSUPPORTED_PLATFORM)
