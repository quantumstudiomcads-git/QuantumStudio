import json
import sys
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
    def fake_iscc(self, command, **kwargs):
        script=Path(command[1]); text=script.read_text(encoding="utf-8-sig")
        self.assertNotIn("recursesubdirs",text.casefold())
        self.assertFalse(any("*" in line or "?" in line for line in text.splitlines() if line.startswith("Source:")))
        output_line=next(line for line in text.splitlines() if line.startswith("OutputDir="))
        compiled=Path(output_line.split("=",1)[1]); compiled.mkdir(parents=True,exist_ok=True)
        (compiled/"QuantumStudio-0.2.0-Setup.exe").write_bytes(b"synthetic installer")
        return __import__("subprocess").CompletedProcess(command,0,"","")

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

    def test_inno_script_uses_one_explicit_source_per_inventory_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"bundle"; marker,inputs=make_bundle(root)
            special=root/"assets"/"space Ω; O'Brien.svg"; special.write_text("asset",encoding="utf-8")
            (root/PAYLOAD_INVENTORY).unlink()
            generate_payload_inventory(root,marker,generated_at="2026-01-01T00:00:00+00:00")
            script=build_windows_installer.installer_script(app_bundle=root,output=Path("C:/installer"),version="0.2.0")
            source_lines=[line for line in script.splitlines() if line.startswith("Source:")]
            inventory=json.loads((root/PAYLOAD_INVENTORY).read_bytes())
            self.assertEqual(len(source_lines),len(inventory["files"]))
            self.assertFalse(any("*" in line or "?" in line for line in source_lines))
            self.assertNotIn("recursesubdirs",script.casefold())
            self.assertTrue(any("space Ω; O'Brien.svg" in line for line in source_lines))
            self.assertIn('DestDir: "{app}\\assets"',next(line for line in source_lines if "space Ω" in line))

    def test_main_compiles_only_allowlisted_snapshot_and_cleans_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); bundle=root/"bundle"; make_bundle(bundle); output=root/"installer"
            with patch.object(build_windows_installer.sys,"platform","win32"), \
                 patch.object(build_windows_installer.shutil,"which",return_value="ISCC.exe"), \
                 patch.object(build_windows_installer.subprocess,"run",side_effect=self.fake_iscc) as run:
                result=build_windows_installer.main(["--app-bundle",str(bundle),"--output",str(output)])
            self.assertEqual(result,0); run.assert_called_once()
            self.assertTrue((output/"QuantumStudio-0.2.0-Setup.exe").is_file())
            self.assertFalse(list(output.glob(".qs-installer-stage-*")))
            self.assertFalse((bundle/"operator-cache.bin").exists())

    def test_unrecorded_sqlite_is_rejected_before_snapshot_or_iscc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); bundle=root/"bundle"; make_bundle(bundle); output=root/"installer"
            (bundle/"operator-cache.bin").write_bytes(b"SQLite format 3\x00"+b"x"*80)
            with patch.object(build_windows_installer.sys,"platform","win32"), \
                 patch.object(build_windows_installer.shutil,"which",return_value="ISCC.exe"), \
                 patch.object(build_windows_installer.subprocess,"run") as run:
                result=build_windows_installer.main(["--app-bundle",str(bundle),"--output",str(output)])
            self.assertEqual(result,2); run.assert_not_called()
            self.assertFalse((output/"QuantumStudio.iss").exists())
            self.assertFalse((output/"QuantumStudio-0.2.0-Setup.exe").exists())
            self.assertFalse(list(output.glob(".qs-installer-stage-*")))

    def test_inventoried_sqlite_is_rejected_before_snapshot_or_iscc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); bundle=root/"bundle"; marker,_inputs=make_bundle(bundle); output=root/"installer"
            (bundle/PAYLOAD_INVENTORY).unlink()
            (bundle/"operator-cache.bin").write_bytes(b"SQLite format 3\x00"+b"x"*80)
            generate_payload_inventory(bundle,marker,generated_at="2026-01-01T00:00:00+00:00")
            with patch.object(build_windows_installer.sys,"platform","win32"), \
                 patch.object(build_windows_installer.shutil,"which",return_value="ISCC.exe"), \
                 patch.object(build_windows_installer.subprocess,"run") as run:
                result=build_windows_installer.main(["--app-bundle",str(bundle),"--output",str(output)])
            self.assertEqual(result,2); run.assert_not_called()
            self.assertFalse((output/"QuantumStudio.iss").exists())
            self.assertFalse(list(output.glob(".qs-installer-stage-*")))

    def test_original_mutation_after_snapshot_does_not_change_compilation_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); bundle=root/"bundle"; make_bundle(bundle); output=root/"installer"
            copier=build_windows_installer._copy_payload_snapshot
            def copy_then_mutate(source,snapshot,verified):
                copier(source,snapshot,verified)
                (source/"QuantumStudio.exe").write_bytes(b"modified after snapshot")
                (source/"new-after-snapshot.bin").write_bytes(b"extra")
            def fake(command,**kwargs):
                script=Path(command[1]); text=script.read_text(encoding="utf-8-sig")
                line=next(item for item in text.splitlines() if item.startswith("Source:") and "QuantumStudio.exe" in item)
                self.assertIn("/payload/QuantumStudio.exe",line)
                self.assertNotIn("new-after-snapshot",text)
                out=Path(next(item for item in text.splitlines() if item.startswith("OutputDir=")).split("=",1)[1])
                (out/"QuantumStudio-0.2.0-Setup.exe").write_bytes(b"synthetic installer")
                return __import__("subprocess").CompletedProcess(command,0,"","")
            with patch.object(build_windows_installer.sys,"platform","win32"), \
                 patch.object(build_windows_installer.shutil,"which",return_value="ISCC.exe"), \
                 patch.object(build_windows_installer,"_copy_payload_snapshot",side_effect=copy_then_mutate), \
                 patch.object(build_windows_installer.subprocess,"run",side_effect=fake):
                result=build_windows_installer.main(["--app-bundle",str(bundle),"--output",str(output)])
            self.assertEqual(result,0)

    def test_original_replacement_before_copy_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); bundle=root/"bundle"; make_bundle(bundle); output=root/"installer"
            copier=build_windows_installer._copy_payload_snapshot
            def mutate_before_copy(source,snapshot,verified):
                (source/"QuantumStudio.exe").write_bytes(b"changed after original validation")
                return copier(source,snapshot,verified)
            with patch.object(build_windows_installer.sys,"platform","win32"), \
                 patch.object(build_windows_installer.shutil,"which",return_value="ISCC.exe"), \
                 patch.object(build_windows_installer,"_copy_payload_snapshot",side_effect=mutate_before_copy), \
                 patch.object(build_windows_installer.subprocess,"run") as run:
                result=build_windows_installer.main(["--app-bundle",str(bundle),"--output",str(output)])
            self.assertEqual(result,2); run.assert_not_called()
            self.assertFalse(list(output.glob(".qs-installer-stage-*")))

    def test_snapshot_addition_after_audit_cannot_enter_explicit_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); bundle=root/"bundle"; make_bundle(bundle); output=root/"installer"
            def fake(command,**kwargs):
                script=Path(command[1]); text=script.read_text(encoding="utf-8-sig")
                snapshot=script.parent/"payload"; injected=snapshot/"operator-cache.bin"
                try: injected.write_bytes(b"SQLite format 3\x00"+b"x"*80)
                except OSError: pass  # directory handles may deny new entries on Windows.
                sources=[line for line in text.splitlines() if line.startswith("Source:")]
                self.assertFalse(any("operator-cache.bin" in line for line in sources))
                self.assertTrue(all("/payload/" in line for line in sources))
                compiled=Path(next(line for line in text.splitlines() if line.startswith("OutputDir=")).split("=",1)[1])
                (compiled/"QuantumStudio-0.2.0-Setup.exe").write_bytes(b"synthetic installer")
                return __import__("subprocess").CompletedProcess(command,0,"","")
            with patch.object(build_windows_installer.sys,"platform","win32"), \
                 patch.object(build_windows_installer.shutil,"which",return_value="ISCC.exe"), \
                 patch.object(build_windows_installer.subprocess,"run",side_effect=fake):
                result=build_windows_installer.main(["--app-bundle",str(bundle),"--output",str(output)])
            self.assertEqual(result,0)

    def test_windows_snapshot_locks_allow_reads_and_deny_writes_and_deletes(self):
        if not sys.platform.startswith("win"): self.skipTest("Windows share-mode locking requires Windows")
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); bundle=root/"bundle"; marker,inputs=make_bundle(bundle)
            audit,verified=build_windows_installer._validate_installer_bundle(bundle)
            snapshot=root/"snapshot"; snapshot.mkdir(); build_windows_installer._copy_payload_snapshot(bundle,snapshot,verified)
            _audit,snap_verified=build_windows_installer._validate_installer_bundle(snapshot)
            iss=root/"test.iss"; iss.write_text("[Setup]\n",encoding="utf-8")
            locks=build_windows_installer._lock_snapshot(snapshot,snap_verified["inventory"]["files"],iss)
            try:
                self.assertTrue((snapshot/"QuantumStudio.exe").read_bytes())
                with self.assertRaises(OSError): (snapshot/"QuantumStudio.exe").write_bytes(b"replace")
                with self.assertRaises(OSError): (snapshot/"QuantumStudio.exe").unlink()
                with self.assertRaises(OSError): iss.write_text("changed",encoding="utf-8")
                with self.assertRaises(OSError): iss.rename(root/"renamed.iss")
            finally: locks.close()
            (snapshot/"QuantumStudio.exe").write_bytes(b"after close")
            self.assertEqual((snapshot/"QuantumStudio.exe").read_bytes(),b"after close")

    def test_partial_lock_failure_releases_prior_handles_and_aborts(self):
        if not sys.platform.startswith("win"): self.skipTest("Windows share-mode locking requires Windows")
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); bundle=root/"bundle"; make_bundle(bundle); output=root/"installer"
            real_cls=build_windows_installer._WindowsReadLocks; instances=[]; count=0
            real_init=real_cls.__init__; real_add=real_cls.add
            def init(instance): real_init(instance); instances.append(instance)
            def add(instance,path,*,directory=False):
                nonlocal count
                count+=1
                if count==3: raise OSError("controlled lock failure")
                return real_add(instance,path,directory=directory)
            with patch.object(build_windows_installer.sys,"platform","win32"), \
                 patch.object(build_windows_installer.shutil,"which",return_value="ISCC.exe"), \
                 patch.object(build_windows_installer._WindowsReadLocks,"__init__",init), \
                 patch.object(build_windows_installer._WindowsReadLocks,"add",add), \
                 patch.object(build_windows_installer.subprocess,"run") as run:
                result=build_windows_installer.main(["--app-bundle",str(bundle),"--output",str(output)])
            self.assertEqual(result,2); run.assert_not_called()
            self.assertEqual(len(instances),1); self.assertEqual(instances[0].handles,[])
            self.assertFalse(list(output.glob(".qs-installer-stage-*")))

    def test_alternate_data_stream_is_not_copied_or_referenced(self):
        if not sys.platform.startswith("win"): self.skipTest("NTFS alternate streams require Windows")
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); bundle=root/"bundle"; make_bundle(bundle); output=root/"installer"
            original_exe=bundle/"QuantumStudio.exe"
            try:
                with open(str(original_exe)+":audit_stream","wb") as stream: stream.write(b"operator stream")
            except OSError: self.skipTest("alternate streams unavailable on this filesystem")
            def fake(command,**kwargs):
                iss=Path(command[1]); text=iss.read_text(encoding="utf-8-sig")
                self.assertNotIn(":audit_stream",text)
                snapshot_exe=iss.parent/"payload"/"QuantumStudio.exe"
                self.assertFalse(Path(str(snapshot_exe)+":audit_stream").exists())
                compiled=Path(next(line for line in text.splitlines() if line.startswith("OutputDir=")).split("=",1)[1])
                (compiled/"QuantumStudio-0.2.0-Setup.exe").write_bytes(b"synthetic installer")
                return __import__("subprocess").CompletedProcess(command,0,"","")
            with patch.object(build_windows_installer.sys,"platform","win32"), \
                 patch.object(build_windows_installer.shutil,"which",return_value="ISCC.exe"), \
                 patch.object(build_windows_installer.subprocess,"run",side_effect=fake):
                result=build_windows_installer.main(["--app-bundle",str(bundle),"--output",str(output)])
            self.assertEqual(result,0)

    def test_failed_iscc_cleans_stage_without_publishing_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); bundle=root/"bundle"; make_bundle(bundle); output=root/"installer"
            def fail(command,**kwargs):
                return __import__("subprocess").CompletedProcess(command,1,"","controlled failure")
            with patch.object(build_windows_installer.sys,"platform","win32"), \
                 patch.object(build_windows_installer.shutil,"which",return_value="ISCC.exe"), \
                 patch.object(build_windows_installer.subprocess,"run",side_effect=fail):
                result=build_windows_installer.main(["--app-bundle",str(bundle),"--output",str(output)])
            self.assertEqual(result,2)
            self.assertFalse((output/"QuantumStudio.iss").exists())
            self.assertFalse((output/"QuantumStudio-0.2.0-Setup.exe").exists())
            self.assertFalse(list(output.glob(".qs-installer-stage-*")))

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
            original = build_windows_installer._validate_installer_bundle
            def validate(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 3: raise ValueError("PAYLOAD_INTEGRITY_MISMATCH")
                return original(*args, **kwargs)
            with patch.object(build_windows_installer.sys, "platform", "win32"), \
                 patch.object(build_windows_installer.shutil, "which", return_value="ISCC.exe"), \
                 patch.object(build_windows_installer, "_validate_installer_bundle", side_effect=validate), \
                 patch.object(build_windows_installer.subprocess, "run") as run:
                result = build_windows_installer.main(["--app-bundle", str(bundle), "--output", str(output)])
            self.assertEqual(result, 2); self.assertFalse((output / "QuantumStudio.iss").exists())
            self.assertEqual(list(output.iterdir()), []); run.assert_not_called()

    def test_change_after_iss_publication_removes_script_before_iscc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); bundle = root / "bundle"; make_bundle(bundle); output = root / "installer"
            calls = 0
            original = build_windows_installer._validate_installer_bundle
            def validate(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 3: raise ValueError("PAYLOAD_INTEGRITY_MISMATCH")
                return original(*args, **kwargs)
            with patch.object(build_windows_installer.sys, "platform", "win32"), \
                 patch.object(build_windows_installer.shutil, "which", return_value="ISCC.exe"), \
                 patch.object(build_windows_installer, "_validate_installer_bundle", side_effect=validate), \
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
