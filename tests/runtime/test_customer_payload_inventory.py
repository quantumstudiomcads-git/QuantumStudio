import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import build_windows_installer
from scripts.windows_packaging import (
    INSTALLER_INPUT, PACKAGE_MARKER, PAYLOAD_INVENTORY,
    WindowsBuildError, audit_customer_package_contents,
    generate_payload_inventory, verify_payload_inventory,
)


def make_bundle(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    for relative, content in (
        ("QuantumStudio.exe", b"synthetic executable"),
        ("assets/quantum-studio-v0.1.svg", b"<svg/ >"),
        ("PySide6/qt-plugins/platforms/qwindows.dll", b"synthetic Qt plugin"),
        ("cryptography/hazmat/bindings/_rust.pyd", b"synthetic extension"),
    ):
        path = root / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
    marker = {"schema_version": 1, "product": "Quantum Studio", "version": "0.2.0", "channel": "beta",
        "platform": "windows", "architecture": "x86_64", "commit": "abc1234", "dirty": False,
        "build_timestamp": "2026-01-01T00:00:00+00:00", "python": "3.13.15", "pyside6": "6.9.0",
        "nuitka": "2.7.0", "packaging_format": "nuitka-standalone", "entry_executable": "QuantumStudio.exe",
        "resource_manifest": "assets/quantum-studio-v0.1.svg"}
    (root / PACKAGE_MARKER).write_text(json.dumps(marker), encoding="utf-8")
    inputs = {"schema_version": 1, "product": "Quantum Studio", "version": "0.2.0", "channel": "beta",
        "platform": "windows", "architecture": "x86_64", "gui_bundle": {"path": "QuantumStudio.dist", "entry": "QuantumStudio.exe"},
        "runtime_image": {"status": "PENDING_W7", "descriptor": None},
        "runtime_agent": {"protocol_schema": 1, "status": "included-in-runtime-image"},
        "engine_pack": {"status": "PENDING_LEGAL_AND_W7", "descriptor": None},
        "licenses_notices": {"status": "PENDING_W7", "inputs": []}, "build_manifest": marker}
    (root / INSTALLER_INPUT).write_text(json.dumps(inputs), encoding="utf-8")
    generate_payload_inventory(root, marker, generated_at="2026-01-01T00:00:00+00:00")
    return marker, inputs


class CustomerPayloadInventoryTests(unittest.TestCase):
    def test_valid_inventory_is_canonical_and_excludes_itself(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "bundle"; marker, inputs = make_bundle(root)
            data = (root / PAYLOAD_INVENTORY).read_bytes()
            inventory = json.loads(data)
            self.assertEqual(data, json.dumps(inventory, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())
            paths = [record["path"] for record in inventory["files"]]
            self.assertEqual(paths, sorted(paths))
            self.assertIn(PACKAGE_MARKER, paths); self.assertIn(INSTALLER_INPUT, paths)
            self.assertIn("QuantumStudio.exe", paths); self.assertNotIn(PAYLOAD_INVENTORY, paths)
            self.assertTrue(verify_payload_inventory(root, marker, inputs)["inventory"]["files"])

    def test_inventory_requires_exact_file_set_size_and_hash(self):
        mutations = (
            ("missing", lambda root: (root / PAYLOAD_INVENTORY).unlink()),
            ("extra", lambda root: (root / "extra.bin").write_bytes(b"extra")),
            ("removed", lambda root: (root / "QuantumStudio.exe").unlink()),
            ("renamed", lambda root: (root / "QuantumStudio.exe").rename(root / "renamed.bin")),
            ("same_name_modified", lambda root: (root / "QuantumStudio.exe").write_bytes(b"changed executable")),
            ("size", lambda root: (root / "QuantumStudio.exe").write_bytes(b"x")),
        )
        for label, mutate in mutations:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "bundle"; marker, inputs = make_bundle(root); mutate(root)
                with self.assertRaises(WindowsBuildError): verify_payload_inventory(root, marker, inputs)

    def test_inventory_rejects_unknown_duplicate_nonfinite_and_unsafe_records(self):
        invalid = (
            lambda value: value.update(schema_version=2),
            lambda value: value.update(unexpected=True),
            lambda value: value["files"][0].update(path="../escape"),
            lambda value: value["files"][0].update(path="C:/absolute"),
            lambda value: value["files"][0].update(sha256="A" * 64),
            lambda value: value["files"][0].update(size_bytes=True),
            lambda value: value["files"].append(dict(value["files"][0])),
        )
        for index, mutate in enumerate(invalid):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "bundle"; marker, inputs = make_bundle(root)
                value = json.loads((root / PAYLOAD_INVENTORY).read_bytes()); mutate(value)
                (root / PAYLOAD_INVENTORY).write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaises(WindowsBuildError): verify_payload_inventory(root, marker, inputs)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "bundle"; marker, inputs = make_bundle(root)
            (root / PAYLOAD_INVENTORY).write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
            with self.assertRaises(WindowsBuildError): verify_payload_inventory(root, marker, inputs)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "bundle"; marker, inputs = make_bundle(root)
            (root / PAYLOAD_INVENTORY).write_text('{"schema_version":NaN}', encoding="utf-8")
            with self.assertRaises(WindowsBuildError): verify_payload_inventory(root, marker, inputs)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "bundle"; marker, inputs = make_bundle(root)
            value = json.loads((root / PAYLOAD_INVENTORY).read_bytes())
            value["files"].append({**value["files"][0], "path": value["files"][0]["path"].swapcase()})
            value["files"].sort(key=lambda record: record["path"])
            (root / PAYLOAD_INVENTORY).write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(WindowsBuildError): verify_payload_inventory(root, marker, inputs)

    def test_inventory_rejects_metadata_mismatch_and_reparse_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "bundle"; marker, inputs = make_bundle(root)
            marker["version"] = "9.9.9"; (root / PACKAGE_MARKER).write_text(json.dumps(marker), encoding="utf-8")
            with self.assertRaises((WindowsBuildError, ValueError)):
                from scripts.build_windows_installer import validate_installer_bundle
                validate_installer_bundle(root)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "bundle"; make_bundle(root)
            link = root / "link.bin"
            try: link.symlink_to(root / "QuantumStudio.exe")
            except (OSError, NotImplementedError): self.skipTest("symlink creation unavailable")
            audit = audit_customer_package_contents(root)
            self.assertFalse(audit["valid"])

    def test_build_and_installer_metadata_are_independently_bound(self):
        for name, mutate in (
            ("channel", lambda m, i: m.update(channel="release")),
            ("platform", lambda m, i: m.update(platform="linux")),
            ("architecture", lambda m, i: m.update(architecture="arm64")),
            ("commit", lambda m, i: m.update(commit="def5678")),
            ("dirty provenance", lambda m, i: m.update(dirty=True)),
            ("installer channel", lambda m, i: i.update(channel="release")),
            ("installer profile path", lambda m, i: i["gui_bundle"].update(path="other.dist")),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "bundle"; marker, inputs = make_bundle(root); mutate(marker, inputs)
                (root / PACKAGE_MARKER).write_text(json.dumps(marker), encoding="utf-8")
                (root / INSTALLER_INPUT).write_text(json.dumps(inputs), encoding="utf-8")
                with self.assertRaises(ValueError): build_windows_installer.validate_installer_bundle(root)

    def test_content_classifier_rejects_disguised_sensitive_content(self):
        payloads = {
            "operator-cache.bin": b"SQLite format 3\x00" + b"\x00" * 80,
            "no-extension": b"SQLite format 3\x00" + b"\x00" * 80,
            "wal.dat": bytes.fromhex("377f0682") + b"\x00" * 80,
            "journal.cache": bytes.fromhex("d9d505f920a163d7") + b"\x00" * 80,
            "private.dat": b"-----BEGIN OPENSSH PRIVATE KEY-----\nTEST ONLY\n-----END OPENSSH PRIVATE KEY-----",
            "signing.resource": json.dumps({"format": "quantum-studio-protected-key", "version": 1, "purpose": "licence-signing-ed25519", "protected_data": "AA=="}).encode(),
            "pii.cache": json.dumps({"format": "quantum-studio-key-material", "version": 1, "purpose": "applicant-pii-database-key"}).encode(),
            "applicants.bin": json.dumps({"schema_version": 1, "applications": [{"application_id": "id", "full_name": "Synthetic", "email": "x@example.test", "institution": "Example"}]}).encode(),
            "audit.json.dat": json.dumps({"event_id": "e", "timestamp": "t", "event_type": "x", "operator_id": "o", "affected_ids": [], "details": {}, "previous_hash": "0", "event_hash": "1"}).encode(),
            "receipt.asset": json.dumps({"receipt_schema_version": 1, "licence_id": "x", "licence_file_sha256": "0", "audit_event_id": "e"}).encode(),
            "preissued.config": json.dumps({"signature": "x", "kid": "lic-a", "licence_id": "x", "device_id": "d", "device_public_key_hash": "h", "expires_at": 1}).encode(),
            "bundle.zip": b"PK\x03\x04" + b"synthetic archive with traversal ../outside",
        }
        for name, content in payloads.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); (root / name).write_bytes(content)
                result = audit_customer_package_contents(root)
                self.assertFalse(result["valid"])
                self.assertTrue(result["forbidden"])

    def test_legitimate_json_trust_metadata_and_text_word_do_not_false_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "customer.json").write_text('{"message":"SQLite is a format name"}', encoding="utf-8")
            (root / "licence-public-key.json").write_text('{"kid":"lic-public-1","algorithm":"Ed25519","public_key":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}', encoding="utf-8")
            audit = audit_customer_package_contents(root)
            self.assertTrue(audit["valid"], audit)

    def test_linux_shared_audit_rejects_disguised_content_and_accepts_clean_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "payload.bin").write_bytes(b"SQLite format 3\x00" + b"\x00" * 64)
            self.assertFalse(audit_customer_package_contents(root)["valid"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "QuantumStudio").write_bytes(b"synthetic executable")
            (root / "settings.json").write_text('{"theme":"light"}', encoding="utf-8")
            self.assertTrue(audit_customer_package_contents(root)["valid"])

    def test_large_binary_content_is_probed_without_read_bytes_or_unbounded_json_parse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); target = root / "large.exe"
            with target.open("wb") as stream:
                stream.write(b"MZ"); stream.truncate(32 * 1024 * 1024)
            with patch.object(Path, "read_bytes", side_effect=AssertionError("unbounded read_bytes used")):
                self.assertTrue(audit_customer_package_contents(root)["valid"])

    def test_invalid_installer_bundle_never_publishes_iss_or_invokes_iscc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); bundle = root / "bundle"; make_bundle(bundle)
            (bundle / PAYLOAD_INVENTORY).unlink()
            output = root / "installer"
            with patch.object(build_windows_installer.sys, "platform", "win32"), \
                 patch.object(build_windows_installer.shutil, "which", return_value="ISCC.exe"), \
                 patch.object(build_windows_installer.subprocess, "run") as run:
                result = build_windows_installer.main(["--app-bundle", str(bundle), "--output", str(output)])
            self.assertEqual(result, 2); run.assert_not_called()
            self.assertFalse((output / "QuantumStudio.iss").exists())
            self.assertFalse(list(output.glob("*.exe")) if output.exists() else False)

    def test_change_before_publication_removes_temp_script_and_preserves_existing_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); bundle = root / "bundle"; make_bundle(bundle); output = root / "installer"
            calls = 0
            original = build_windows_installer.validate_installer_bundle
            def validate(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 3: raise ValueError("PAYLOAD_INTEGRITY_MISMATCH")
                return original(*args, **kwargs)
            with patch.object(build_windows_installer.sys, "platform", "win32"), \
                 patch.object(build_windows_installer.shutil, "which", return_value="ISCC.exe"), \
                 patch.object(build_windows_installer, "validate_installer_bundle", side_effect=validate), \
                 patch.object(build_windows_installer.subprocess, "run") as run:
                result = build_windows_installer.main(["--app-bundle", str(bundle), "--output", str(output)])
            self.assertEqual(result, 2); self.assertFalse((output / "QuantumStudio.iss").exists())
            self.assertEqual(list(output.iterdir()), []); run.assert_not_called()

    def test_change_after_iss_publication_removes_script_before_iscc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); bundle = root / "bundle"; make_bundle(bundle); output = root / "installer"
            calls = 0
            original = build_windows_installer.validate_installer_bundle
            def validate(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 4: raise ValueError("PAYLOAD_INTEGRITY_MISMATCH")
                return original(*args, **kwargs)
            with patch.object(build_windows_installer.sys, "platform", "win32"), \
                 patch.object(build_windows_installer.shutil, "which", return_value="ISCC.exe"), \
                 patch.object(build_windows_installer, "validate_installer_bundle", side_effect=validate), \
                 patch.object(build_windows_installer.subprocess, "run") as run:
                result = build_windows_installer.main(["--app-bundle", str(bundle), "--output", str(output)])
            self.assertEqual(result, 2); self.assertFalse((output / "QuantumStudio.iss").exists())
            self.assertEqual(list(output.iterdir()), []); run.assert_not_called()

    def test_existing_iss_or_installer_is_never_overwritten(self):
        for name in ("QuantumStudio.iss", "QuantumStudio-0.2.0-Setup.exe"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); bundle = root / "bundle"; make_bundle(bundle); output = root / "installer"
                output.mkdir(); original = b"pre-existing sentinel"; (output / name).write_bytes(original)
                with patch.object(build_windows_installer.sys, "platform", "win32"), \
                     patch.object(build_windows_installer.shutil, "which", return_value="ISCC.exe"), \
                     patch.object(build_windows_installer.subprocess, "run") as run:
                    result = build_windows_installer.main(["--app-bundle", str(bundle), "--output", str(output)])
                self.assertEqual(result, 2)
                self.assertEqual((output / name).read_bytes(), original)
                run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
