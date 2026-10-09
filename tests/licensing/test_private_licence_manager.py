from __future__ import annotations

import base64
import ctypes
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from PySide6.QtWidgets import QApplication, QMessageBox

from backend.licensing.canonical import b64url_decode, b64url_encode
from backend.licensing.models import ImplementationState
from backend.licensing.service import LicensingService
from backend.licensing.verifier import LeaseValidationError, LeaseVerifier, device_identity_from_private_key
from backend.licensing.enforcement import CalculationAuthorizationBoundary
from backend.calculations import registry
from operator_tools.licence_manager.audit import verify_chain
from operator_tools.licence_manager.crypto import DataProtector, ProtectionUnavailable, normalize_applicant_email
from operator_tools.licence_manager.database import Database
from operator_tools.licence_manager.exports import ExportRecoveryError, export_licence, receipt_for
from operator_tools.licence_manager.imports import (ImportRejected, MAX_ACTIVATION_IMPORT_BYTES,
    MAX_APPLICANT_IMPORT_BYTES, import_activation_json, import_applicants_json)
from operator_tools.licence_manager.issuance import (IssuanceRejected, authorize_activation_profile,
    issue_for_request_for_testing, record_expiries, revoke_licence)
from operator_tools.licence_manager.main_window import LicenceManagerWindow
from operator_tools.licence_manager.models import ApplicantStatus, Profile
from operator_tools.licence_manager.policy import derive_profile
from operator_tools.licence_manager.signing import (ProductionAuthority,
    AuthorityState, SigningUnavailable, TestEphemeralAuthority as EphemeralAuthority, record_public_metadata)
from scripts.package_exclusions import customer_package_exclusion_findings
from scripts.windows_packaging import audit_package_contents, build_plan, generate_payload_inventory
from scripts.windows_installer.payload_audit import audit_installer_payload
from scripts.build_windows_installer import validate_installer_bundle
from frontend.calculations.catalog import CALCULATIONS
from frontend.calculations.reconciliation import ExecutionSupport, reconcile_catalog


def _key_material(purpose, raw):
    algorithm = "Ed25519" if purpose == "licence-signing-ed25519" else "AES-256-GCM+HMAC-SHA256"
    material = {"format": "quantum-studio-key-material", "version": 1, "purpose": purpose,
        "algorithm": algorithm, "key_length": 32, "key": base64.urlsafe_b64encode(raw).decode("ascii")}
    if purpose == "applicant-pii-database-key": material["storage_generation_id"] = str(uuid.UUID(int=1))
    return json.dumps(material,
        sort_keys=True, separators=(",", ":")).encode("utf-8")


def _write_protected_key_file(path, purpose, protected=b"test-dpapi-blob"):
    encoded = (b64url_encode(protected) if purpose == "licence-signing-ed25519"
               else base64.urlsafe_b64encode(protected).decode("ascii"))
    path.write_text(json.dumps({"format": "quantum-studio-protected-key", "version": 1,
        "purpose": purpose, "protected_data": encoded},
        sort_keys=True, separators=(",", ":")), encoding="ascii")


@contextmanager
def _mock_dpapi(module, *, unprotected=None, protected=b"test-dpapi-blob", fail_unprotect=False, on_unprotect=None):
    calls = []
    buffers = []
    protected_inputs = []
    def loader(name, **_kwargs):
        if name == "Kernel32":
            api = type("Kernel32", (), {})()
            api.LocalFree = lambda _pointer: None
            return api
        api = type("Crypt32", (), {})()
        def fill(output_arg, value):
            output = output_arg._obj
            buffer = ctypes.create_string_buffer(value)
            buffers.append(buffer)
            output.cbData = len(value)
            output.pbData = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))
        def decrypt(*args):
            calls.append("unprotect")
            if on_unprotect:
                on_unprotect()
            if fail_unprotect:
                return 0
            fill(args[-1], unprotected or b"")
            return 1
        def encrypt(*args):
            source = args[0]._obj
            protected_inputs.append(ctypes.string_at(source.pbData, source.cbData))
            fill(args[-1], protected)
            return 1
        decrypt.argtypes = encrypt.argtypes = None
        api.CryptUnprotectData = decrypt
        api.CryptProtectData = encrypt
        return api
    with patch.object(module.ctypes, "WinDLL", side_effect=loader, create=True):
        yield calls, protected_inputs


class LicenceManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.protector = DataProtector.for_testing(b"T" * 32)
        self.db = Database(self.root / "data", self.protector)
        self.addCleanup(self.db.close)
        self.application_id = str(uuid.uuid4())
        self.applicant = {
            "application_id": self.application_id,
            "full_name": "Ada Beta Fixture", "email": "ada@example.test", "institution": "Example Institute",
            "country": "Example", "academic_role": "Professor", "research_area": "materials",
            "intended_evaluation": "local test only", "operating_system": "windows-x86_64",
            "privacy_consent": "true", "privacy_version": "1", "terms_consent": "true", "terms_version": "1",
            "communications_consent": "false", "submitted_at": "2026-01-01T00:00:00Z", "status": "APPROVED",
            "licence_id": "remote-value-must-be-ignored",
        }
        self.import_applicant()
        self.device_private = Ed25519PrivateKey.generate()
        self.device = device_identity_from_private_key(self.device_private)
        self.request = {
            "schema_version": 1, "request_id": str(uuid.uuid4()), "application_id": self.application_id,
            "product": "Quantum Studio", "application_version": "0.2.0", "platform": "windows-x86_64",
            "device_id": self.device.device_id, "device_public_key": b64url_encode(self.device.public_key),
            "device_public_key_hash": self.device.public_key_hash, "requested_profile": "PROFESSOR_BETA",
            "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }

    def import_applicant(self):
        payload = {"schema_version": 1, "applications": [self.applicant]}
        self.assertEqual(import_applicants_json(json.dumps(payload), self.db), 1)

    def approve(self):
        self.db.transition(self.application_id, ApplicantStatus.UNDER_REVIEW)
        self.db.transition(self.application_id, ApplicantStatus.APPROVED)

    def import_request(self):
        self.approve()
        return import_activation_json(json.dumps(self.request), self.db)

    def authorize(self, profile=Profile.PROFESSOR_BETA):
        return authorize_activation_profile(self.db, self.request["request_id"], profile, confirmed=True)

    def issue_time(self):
        return int(datetime.fromisoformat(self.request["created_at"].replace("Z", "+00:00")).timestamp()) + 1

    def test_database_migration_and_encrypted_pii_round_trip(self):
        self.assertEqual(self.db.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 4)
        self.assertEqual(self.db.applicant_pii(self.application_id)["email"], "ada@example.test")
        raw = self.db.path.read_bytes()
        for secret in ("Ada Beta Fixture", "ada@example.test", "Example Institute", "local test only"):
            self.assertNotIn(secret.encode(), raw)
            self.assertNotIn(secret, str([row[0] for row in self.db.connection.execute("SELECT details FROM audit_events")]))
        self.assertEqual(len(self.db.connection.execute("SELECT email_index FROM applicants").fetchone()[0]), 64)

    def test_v1_database_upgrades_to_v2_profile_authorization_column(self):
        path = self.root / "legacy" / "operator.sqlite3"
        path.parent.mkdir()
        old = sqlite3.connect(path)
        old.executescript("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL); INSERT INTO schema_migrations VALUES(1,'2026-01-01'); CREATE TABLE activation_requests(request_id TEXT PRIMARY KEY, application_id TEXT NOT NULL, request_hash TEXT NOT NULL, request_json TEXT NOT NULL, imported_at TEXT NOT NULL);")
        old.close()
        upgraded = Database(path.parent, self.protector)
        self.addCleanup(upgraded.close)
        columns = {row[1] for row in upgraded.connection.execute("PRAGMA table_info(activation_requests)")}
        self.assertIn("authorized_profile", columns)
        self.assertEqual(upgraded.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 4)

    def test_raw_pii_keys_are_test_only_and_json_duplicate_fields_reject(self):
        with self.assertRaises(ProtectionUnavailable): DataProtector(b"K" * 32)
        with self.assertRaises(ImportRejected): import_applicants_json('{"schema_version":1,"schema_version":1,"applications":[]}', self.db)
        from operator_tools.licence_manager import crypto
        protected_path = self.root / "unsupported.dpapi"
        with patch.object(crypto.sys, "platform", "linux"):
            with self.assertRaises(ProtectionUnavailable): DataProtector.open_existing_windows_keyfile(protected_path)
        self.assertFalse(protected_path.exists())

    def test_no_supported_generic_dpapi_decryption_api_exists(self):
        import inspect
        import operator_tools.licence_manager as package
        import operator_tools.licence_manager.crypto as crypto
        import operator_tools.licence_manager.signing as signing
        self.assertFalse(hasattr(crypto, "dpapi_unprotect"))
        self.assertFalse(hasattr(crypto, "dpapi_protect"))
        self.assertFalse(any("unprotect" in name.casefold() or "decrypt_key" in name.casefold()
                             for name in vars(package) if not name.startswith("_")))
        public_crypto = {name: value for name, value in vars(crypto).items() if not name.startswith("_")}
        self.assertFalse(any(callable(value) and name.lower() in {"unprotect", "decrypt_key", "load_private_key"}
                             for name, value in public_crypto.items()))
        self.assertFalse(any(name in dir(signing._LicenceSigningKeyStore(self.root / "key"))
                             for name in ("load_private_key", "get_private_key", "decrypt_key", "private_key")))
        self.assertNotIn("protected_blob", inspect.signature(crypto.DataProtector.open_existing_windows_keyfile).parameters)
        self.assertFalse(any(name in getattr(package, "__all__", ()) for name in ("dpapi_unprotect", "unprotect_dpapi")))

    def test_purpose_envelopes_reject_cross_domain_before_or_after_dpapi(self):
        import operator_tools.licence_manager.crypto as crypto
        import operator_tools.licence_manager.signing as signing
        pii_path = self.root / "data-key.dpapi"
        _write_protected_key_file(pii_path, "licence-signing-ed25519")
        with patch.object(crypto.sys, "platform", "win32"), _mock_dpapi(crypto) as (calls, _):
            with self.assertRaises(ProtectionUnavailable): DataProtector.open_existing_windows_keyfile(pii_path)
            self.assertEqual(calls, [])
        signing_path = self.root / "signing-key.dpapi"
        _write_protected_key_file(signing_path, "applicant-pii-database-key")
        self.import_request(); self.authorize()
        public = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
        (self.root / "public.json").write_text(json.dumps({"schema_version": 1, "kid": "lic-purpose-test",
            "public_key": b64url_encode(public)}), encoding="utf-8")
        authority = ProductionAuthority(signing_path, self.root / "public.json", database=self.db)
        with patch.object(signing.sys, "platform", "win32"), _mock_dpapi(signing) as (calls, _):
            with self.assertRaises(IssuanceRejected): authority.issue(self.application_id, self.request["request_id"], Profile.PROFESSOR_BETA, confirmed=True)
            self.assertEqual(calls, [])
        key = Ed25519PrivateKey.generate()
        raw = key.private_bytes_raw()
        _write_protected_key_file(signing_path, "licence-signing-ed25519")
        bad_inner = _key_material("applicant-pii-database-key", raw)
        with patch.object(signing.sys, "platform", "win32"), _mock_dpapi(signing, unprotected=bad_inner) as (calls, _):
            with self.assertRaises(IssuanceRejected): authority.issue(self.application_id, self.request["request_id"], Profile.PROFESSOR_BETA, confirmed=True)
            self.assertEqual(calls, ["unprotect"])
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM licences").fetchone()[0], 0)

    def test_purpose_envelopes_reject_unknown_malformed_and_wrong_inner_material(self):
        import operator_tools.licence_manager.crypto as crypto
        path = self.root / "data-key.dpapi"
        for content in (
            {"format": "quantum-studio-protected-key", "version": 2, "purpose": "applicant-pii-database-key", "protected_data": "eA=="},
            {"format": "quantum-studio-protected-key", "version": 1, "purpose": "unknown", "protected_data": "eA=="},
            {"format": "quantum-studio-protected-key", "version": 1, "purpose": "applicant-pii-database-key", "protected_data": "eA==", "extra": True},
            {"format": "quantum-studio-protected-key", "version": 1, "purpose": "applicant-pii-database-key", "protected_data": "%%%"},
        ):
            path.write_text(json.dumps(content), encoding="ascii")
            with patch.object(crypto.sys, "platform", "win32"), _mock_dpapi(crypto) as (calls, _):
                with self.assertRaises(ProtectionUnavailable): DataProtector.open_existing_windows_keyfile(path)
                self.assertEqual(calls, [])
        path.write_bytes(b"{\xff")
        with patch.object(crypto.sys, "platform", "win32"), _mock_dpapi(crypto) as (calls, _):
            with self.assertRaises(ProtectionUnavailable): DataProtector.open_existing_windows_keyfile(path)
            self.assertEqual(calls, [])
        path.write_text('{"format":"quantum-studio-protected-key","version":1,"purpose":"licence-signing-ed25519","purpose":"applicant-pii-database-key","protected_data":"eA=="}', encoding="ascii")
        with patch.object(crypto.sys, "platform", "win32"), _mock_dpapi(crypto) as (calls, _):
            with self.assertRaises(ProtectionUnavailable): DataProtector.open_existing_windows_keyfile(path)
            self.assertEqual(calls, [])
        for raw in (b"short", b"K" * 31):
            path.write_text(json.dumps({"format": "quantum-studio-protected-key", "version": 1,
                "purpose": "applicant-pii-database-key", "protected_data": base64.urlsafe_b64encode(b"mock").decode()}), encoding="ascii")
            with patch.object(crypto.sys, "platform", "win32"), _mock_dpapi(crypto, unprotected=_key_material("licence-signing-ed25519", raw)) as (calls, _):
                with self.assertRaises(ProtectionUnavailable): DataProtector.open_existing_windows_keyfile(path)
                self.assertEqual(calls, ["unprotect"])

    def test_pii_key_loader_accepts_only_its_exact_versioned_material(self):
        import operator_tools.licence_manager.crypto as crypto
        path = self.root / "data-key.dpapi"
        _write_protected_key_file(path, "applicant-pii-database-key")
        raw = b"D" * 32
        with patch.object(crypto.sys, "platform", "win32"), _mock_dpapi(crypto, unprotected=_key_material("applicant-pii-database-key", raw)) as (calls, _):
            protector = DataProtector.open_existing_windows_keyfile(path)
        self.assertEqual(calls, ["unprotect"])
        self.assertIsInstance(protector, DataProtector)
        self.assertNotIn(raw, repr(vars(protector)).encode())
        encrypted = protector.encrypt(b"synthetic applicant", aad=b'{"record_id":"fixture"}')
        self.assertEqual(protector.decrypt(encrypted, aad=b'{"record_id":"fixture"}'), b"synthetic applicant")
        with patch.object(crypto.sys, "platform", "win32"), _mock_dpapi(crypto, unprotected=_key_material("applicant-pii-database-key", b"K" * 31)) as (calls, _):
            with self.assertRaises(ProtectionUnavailable): DataProtector.open_existing_windows_keyfile(path)
            self.assertEqual(calls, ["unprotect"])

    def test_website_import_forces_applied_and_duplicate_is_idempotent(self):
        row = self.db.connection.execute("SELECT status FROM applicants WHERE application_id=?", (self.application_id,)).fetchone()
        self.assertEqual(row[0], "APPLIED")
        self.assertEqual(import_applicants_json(json.dumps({"schema_version": 1, "applications": [self.applicant]}), self.db), 0)
        with self.assertRaises(ImportRejected):
            import_applicants_json(json.dumps({"schema_version": 2, "applications": []}), self.db)
        with self.assertRaises(ImportRejected):
            import_applicants_json(json.dumps({"schema_version": 1, "applications": [{**self.applicant, "administrator": True}]}), self.db)

    def test_transition_graph_and_rejected_action_audit(self):
        self.db.transition(self.application_id, ApplicantStatus.UNDER_REVIEW)
        self.db.transition(self.application_id, ApplicantStatus.APPROVED)
        with self.assertRaises(ValueError): self.db.transition(self.application_id, ApplicantStatus.APPLIED)
        status = self.db.connection.execute("SELECT status FROM applicants WHERE application_id=?", (self.application_id,)).fetchone()[0]
        self.assertEqual(status, "APPROVED")
        self.assertTrue(self.db.connection.execute("SELECT 1 FROM audit_events WHERE event_type='rejected_policy_action'").fetchone())

    def test_activation_request_key_binding_approval_and_duplicate_rules(self):
        with self.assertRaises(ImportRejected): import_activation_json(json.dumps(self.request), self.db)
        self.approve()
        bad = dict(self.request, device_public_key_hash="0" * 64)
        with self.assertRaises(ImportRejected): import_activation_json(json.dumps(bad), self.db)
        self.assertTrue(import_activation_json(json.dumps(self.request), self.db))
        self.assertFalse(import_activation_json(json.dumps(self.request), self.db))
        conflicting = dict(self.request, application_version="0.2.1")
        with self.assertRaises(ImportRejected): import_activation_json(json.dumps(conflicting), self.db)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM activation_requests").fetchone()[0], 1)
        self.assertTrue(self.db.connection.execute("SELECT 1 FROM audit_events WHERE event_type='duplicate_import'").fetchone())
        with self.assertRaises(IssuanceRejected): issue_for_request_for_testing(self.db, EphemeralAuthority(), self.request["request_id"], confirmed=True)

    def test_activation_request_rejects_extra_capability_and_stale_timestamp(self):
        self.approve()
        with self.assertRaises(ImportRejected): import_activation_json(json.dumps(dict(self.request, administrator=True)), self.db)
        stale = dict(self.request, created_at="2020-01-01T00:00:00Z")
        with self.assertRaises(ImportRejected): import_activation_json(json.dumps(stale), self.db)

    def test_public_requested_profile_never_authorizes_entitlements(self):
        self.request["requested_profile"] = "INTERNAL_VALIDATION"
        self.import_request()
        with self.assertRaises(IssuanceRejected):
            issue_for_request_for_testing(self.db, EphemeralAuthority(), self.request["request_id"], now=self.issue_time(), confirmed=True)
        self.assertIsNone(self.db.connection.execute("SELECT authorized_profile FROM activation_requests").fetchone()[0])
        self.authorize(Profile.PROFESSOR_BETA)
        authority = EphemeralAuthority()
        envelope, _ = issue_for_request_for_testing(self.db, authority, self.request["request_id"], now=self.issue_time(), confirmed=True)
        self.assertEqual(envelope["policy_profile"], "PROFESSOR_BETA")
        self.assertEqual(len(envelope["calculation_entitlements"]), 29)

    def test_activation_request_database_tamper_blocks_signing(self):
        self.import_request()
        self.authorize()
        changed_request = dict(self.request, device_id="dev_" + "0" * 32)
        self.db.connection.execute("UPDATE activation_requests SET request_json=?", (json.dumps(changed_request),))
        self.db.connection.commit()
        with self.assertRaises(IssuanceRejected):
            issue_for_request_for_testing(self.db, EphemeralAuthority(), self.request["request_id"], now=self.issue_time(), confirmed=True)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM licences").fetchone()[0], 0)
        self.assertTrue(self.db.connection.execute("SELECT 1 FROM audit_events WHERE details LIKE '%activation_record_integrity_failure%'").fetchone())

    def test_profiles_are_derived_and_exclude_planned_and_external(self):
        professor = derive_profile(Profile.PROFESSOR_BETA)
        internal = derive_profile(Profile.INTERNAL_VALIDATION)
        self.assertEqual(professor.ready_count, 29)
        self.assertEqual(professor.partial_count, 6)
        self.assertEqual(len(professor.calculations), 29)
        self.assertEqual(len(internal.calculations), 35)
        self.assertEqual(len(internal.calculations) - len(professor.calculations), 6)
        self.assertGreater(professor.excluded_planned_count, 0)
        self.assertGreater(professor.external_count, 0)
        self.assertFalse(any("*" in item for item in internal.calculations))
        report = reconcile_catalog(CALCULATIONS, registry, strict=True)
        external_ids = {"calc:" + item.id for item in report.descriptors if item.execution_support is ExecutionSupport.EXTERNAL_BACKEND_REQUIRED}
        planned_ids = {"calc:" + item.id for item in report.descriptors if item.execution_support is ExecutionSupport.PLANNED}
        self.assertFalse(external_ids.intersection(internal.calculations))
        self.assertFalse(planned_ids.intersection(internal.calculations))

    def test_issue_verifies_with_existing_client_and_is_device_bound(self):
        self.import_request()
        self.authorize()
        authority = EphemeralAuthority(kid="test-lic-fixture")
        envelope, event_id = issue_for_request_for_testing(self.db, authority, self.request["request_id"], now=self.issue_time(), confirmed=True)
        verified = LeaseVerifier({authority.kid: authority.public_key}).verify(envelope, self.device)
        self.assertEqual(verified.lease.calculation_entitlements, tuple(sorted(verified.lease.calculation_entitlements)))
        self.assertEqual(envelope["policy_profile"], "PROFESSOR_BETA")
        self.assertEqual(envelope["expires_at"] - envelope["issued_at"], 90 * 86400)
        self.assertEqual(envelope["approved_application_ref"], self.application_id)
        self.assertTrue(self.db.connection.execute("SELECT 1 FROM audit_events WHERE event_type='successful_test_issuance'").fetchone())
        for forbidden in ("Ada Beta Fixture", "ada@example.test", "Example Institute"):
            self.assertNotIn(forbidden, json.dumps(envelope))
        service = LicensingService.for_testing(trusted_public_keys={authority.kid: authority.public_key}, device_identity=self.device, lease=envelope, now=lambda: envelope["issued_at"] + 1)
        self.assertTrue(service.authorize_calculation("scf", ImplementationState.READY).allowed)
        other = device_identity_from_private_key(Ed25519PrivateKey.generate())
        with self.assertRaises(LeaseValidationError): LeaseVerifier({authority.kid: authority.public_key}).verify(envelope, other)
        changed = dict(envelope, policy_profile="INTERNAL_VALIDATION")
        with self.assertRaises(LeaseValidationError): LeaseVerifier({authority.kid: authority.public_key}).verify(changed, self.device)
        with self.assertRaises(LeaseValidationError): LeaseVerifier({},).verify(envelope, self.device)
        future = dict(envelope, not_before=envelope["issued_at"] + 1000)
        future = authority.sign_test_fixture_only({k: v for k, v in future.items() if k not in {"kid", "signature"}})
        pending = LicensingService.for_testing(trusted_public_keys={authority.kid: authority.public_key}, device_identity=self.device, lease=future, now=lambda: envelope["issued_at"] + 1)
        self.assertFalse(pending.authorize_calculation("scf", ImplementationState.READY).allowed)
        expired = LicensingService.for_testing(trusted_public_keys={authority.kid: authority.public_key}, device_identity=self.device, lease=envelope, now=lambda: envelope["expires_at"] + 1)
        self.assertFalse(expired.authorize_calculation("scf", ImplementationState.READY).allowed)

    def test_internal_profile_grants_executable_partial_but_client_still_checks_readiness(self):
        self.request["requested_profile"] = "PROFESSOR_BETA"
        self.import_request()
        self.authorize(Profile.INTERNAL_VALIDATION)
        authority = EphemeralAuthority()
        envelope, _ = issue_for_request_for_testing(self.db, authority, self.request["request_id"], now=self.issue_time(), confirmed=True)
        self.assertEqual(len(envelope["calculation_entitlements"]), 35)
        service = LicensingService.for_testing(trusted_public_keys={authority.kid: authority.public_key}, device_identity=self.device, lease=envelope, now=lambda: envelope["issued_at"] + 1)
        self.assertFalse(service.authorize_calculation("relax", ImplementationState.PARTIAL).allowed)
        report = reconcile_catalog(CALCULATIONS, registry, strict=True)
        executable_partials = tuple(item for item in report.descriptors if item.execution_support is ExecutionSupport.PARTIAL and item.backend_supported)
        self.assertEqual(len(executable_partials), 6)
        decisions = CalculationAuthorizationBoundary(service).authorize(executable_partials)
        self.assertTrue(all(decision.allowed for decision in decisions))

    def test_production_authority_fails_closed_and_has_no_key_generation(self):
        authority = ProductionAuthority(self.root / "missing.dpapi", self.root / "missing.json", database=self.db)
        self.assertEqual(authority.status().state, AuthorityState.UNINITIALIZED)
        self.assertFalse(hasattr(authority, "sign"))
        self.assertFalse(hasattr(authority, "sign_lease"))
        self.assertFalse((self.root / "missing.dpapi").exists())

    def test_production_status_is_structural_and_never_decrypts(self):
        import operator_tools.licence_manager.signing as signing
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        with _mock_dpapi(signing) as (calls, _):
            authority = ProductionAuthority(self.root / "key.dpapi", self.root / "public.json", database=self.db)
            self.assertEqual(calls, [])
            self.assertEqual(authority.status().state, AuthorityState.UNINITIALIZED)
            public_key = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
            authority.metadata_path.write_text(json.dumps({"schema_version": 1, "kid": "lic-status", "public_key": b64url_encode(public_key)}))
            self.assertEqual(authority.status().state, AuthorityState.PROTECTED_KEY_MISSING)
            _write_protected_key_file(authority.key_path, "licence-signing-ed25519")
            first = authority.status()
            second = authority.status()
            self.assertEqual(first.state, AuthorityState.PROTECTED_KEY_PRESENT_UNVERIFIED)
            self.assertIn("validated only during an authorized issuance", first.message)
            self.assertEqual(second.state, AuthorityState.PROTECTED_KEY_PRESENT_UNVERIFIED)
            self.assertEqual(calls, [])

    def test_status_reports_invalid_metadata_without_decrypting(self):
        import operator_tools.licence_manager.signing as signing
        authority = ProductionAuthority(self.root / "key.dpapi", self.root / "public.json", database=self.db)
        authority.metadata_path.write_text("{broken")
        _write_protected_key_file(authority.key_path, "licence-signing-ed25519")
        with _mock_dpapi(signing) as (calls, _):
            status = authority.status()
            self.assertEqual(status.state, AuthorityState.METADATA_INVALID)
            self.assertEqual(status.message, "Signing authority metadata is invalid.")
            self.assertEqual(calls, [])

    def test_window_startup_refresh_import_and_profile_selection_never_decrypt_signing_key(self):
        import operator_tools.licence_manager.signing as signing
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        authority = ProductionAuthority(self.root / "missing.dpapi", self.root / "missing.json", database=self.db)
        with _mock_dpapi(signing) as (calls, _):
            window = LicenceManagerWindow(test_mode=False, database=self.db, authority=authority)
            self.addCleanup(window.close)
            window.refresh()
            import_applicants_json(json.dumps({"schema_version": 1, "applications": []}), self.db)
            self.assertEqual(calls, [])
            self.approve(); import_activation_json(json.dumps(self.request), self.db)
            self.assertEqual(calls, [])
            window.refresh()
            window.requests_table.selectRow(0)
            with patch("operator_tools.licence_manager.main_window.QInputDialog.getItem", return_value=("PROFESSOR_BETA", True)), \
                 patch("operator_tools.licence_manager.main_window.QMessageBox.question", side_effect=[QMessageBox.Yes, QMessageBox.No]):
                window.issue_selected()
            self.assertEqual(calls, [])
        app.processEvents()

    def test_production_authority_has_only_narrow_identifier_profile_api(self):
        import inspect
        authority = ProductionAuthority(self.root / "missing.dpapi", self.root / "missing.json", database=self.db)
        parameters = tuple(inspect.signature(authority.issue).parameters)
        self.assertEqual(parameters, ("application_id", "activation_request_id", "profile", "confirmed"))
        for extra in ({"entitlements": ["calc:planned"]}, {"expires_at": 9999999999}, {"kid": "attacker", "issuer": "attacker"}):
            with self.assertRaises(TypeError): authority.issue(self.application_id, self.request["request_id"], "PROFESSOR_BETA", **extra)
        with self.assertRaises(IssuanceRejected): authority.issue(self.application_id, self.request["request_id"], {"calculation_entitlements": ["calc:planned"]}, confirmed=True)

    def test_production_rejections_happen_before_protected_key_load(self):
        authority = ProductionAuthority(self.root / "missing.dpapi", self.root / "missing.json", database=self.db)
        import operator_tools.licence_manager.signing as signing
        with _mock_dpapi(signing) as (calls, _):
            with self.assertRaises(IssuanceRejected): authority.issue(self.application_id, self.request["request_id"], Profile.PROFESSOR_BETA, confirmed=True)
            self.assertEqual(calls, [])
            self.import_request(); self.authorize()
            with self.assertRaises(IssuanceRejected): authority.issue(str(uuid.uuid4()), self.request["request_id"], Profile.PROFESSOR_BETA, confirmed=True)
            self.assertEqual(calls, [])
            self.db.connection.execute("UPDATE applicants SET status='REJECTED' WHERE application_id=?", (self.application_id,)); self.db.connection.commit()
            with self.assertRaises(IssuanceRejected): authority.issue(self.application_id, self.request["request_id"], Profile.PROFESSOR_BETA, confirmed=True)
            self.assertEqual(calls, [])
            self.db.connection.execute("UPDATE applicants SET status='APPROVED' WHERE application_id=?", (self.application_id,)); self.db.connection.commit()
            self.db.transition(self.application_id, ApplicantStatus.REVOKED)
            with self.assertRaises(IssuanceRejected): authority.issue(self.application_id, self.request["request_id"], Profile.PROFESSOR_BETA, confirmed=True)
            self.assertEqual(calls, [])

    def test_missing_confirmation_invalid_profile_and_policy_failure_do_not_load_key(self):
        import operator_tools.licence_manager.issuance as issuance
        authority = ProductionAuthority(self.root / "missing.dpapi", self.root / "missing.json", database=self.db)
        self.import_request(); self.authorize()
        import operator_tools.licence_manager.signing as signing
        with _mock_dpapi(signing) as (calls, _):
            with self.assertRaises(IssuanceRejected): authority.issue(self.application_id, self.request["request_id"], Profile.PROFESSOR_BETA)
            with self.assertRaises(IssuanceRejected): authority.issue(self.application_id, self.request["request_id"], "NOT_A_PROFILE", confirmed=True)
            with patch.object(issuance, "derive_profile", side_effect=IssuanceRejected("fixture policy failure")):
                with self.assertRaises(IssuanceRejected): authority.issue(self.application_id, self.request["request_id"], Profile.PROFESSOR_BETA, confirmed=True)
            self.assertEqual(calls, [])
            stored_json = self.db.connection.execute("SELECT request_json FROM activation_requests WHERE request_id=?", (self.request["request_id"],)).fetchone()[0]
            self.db.connection.execute("UPDATE activation_requests SET request_json=?", ('{"schema_version":999}',)); self.db.connection.commit()
            with self.assertRaises(IssuanceRejected): authority.issue(self.application_id, self.request["request_id"], Profile.PROFESSOR_BETA, confirmed=True)
            self.assertEqual(calls, [])
            self.db.connection.execute("UPDATE activation_requests SET request_json=?", (stored_json,)); self.db.connection.commit()

    def test_production_issue_signs_only_database_derived_lease(self):
        import operator_tools.licence_manager.signing as signing
        from cryptography.hazmat.primitives import serialization
        self.import_request(); self.authorize()
        key = Ed25519PrivateKey.generate()
        raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
        protected = self.root / "key.dpapi"; _write_protected_key_file(protected, "licence-signing-ed25519")
        metadata = self.root / "public.json"
        metadata.write_text(json.dumps({"schema_version": 1, "kid": "lic-p1b-fixture", "public_key": b64url_encode(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))}))
        authority = ProductionAuthority(protected, metadata, database=self.db)
        def unprotect_after_checks():
            self.assertTrue(self.db.connection.in_transaction)
            self.assertEqual(self.db.connection.execute("SELECT status FROM applicants WHERE application_id=?", (self.application_id,)).fetchone()[0], "APPROVED")
            self.assertEqual(self.db.connection.execute("SELECT authorized_profile FROM activation_requests WHERE request_id=?", (self.request["request_id"],)).fetchone()[0], "PROFESSOR_BETA")
            stored_json, stored_hash = self.db.connection.execute("SELECT request_json,request_hash FROM activation_requests WHERE request_id=?", (self.request["request_id"],)).fetchone()
            stored_request = json.loads(stored_json)
            self.assertEqual(hashlib.sha256(json.dumps(stored_request, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), stored_hash)
            self.assertEqual(stored_request["product"], "Quantum Studio")
            self.assertEqual(stored_request["platform"], "windows-x86_64")
            self.assertEqual(stored_request["device_id"], self.device.device_id)
            self.assertEqual(stored_request["device_public_key_hash"], self.device.public_key_hash)
            self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM licences").fetchone()[0], 0)
            return raw
        with patch.object(signing.sys, "platform", "win32"), _mock_dpapi(signing, unprotected=_key_material("licence-signing-ed25519", raw), on_unprotect=unprotect_after_checks) as (calls, _):
            envelope, event = authority.issue(self.application_id, self.request["request_id"], Profile.PROFESSOR_BETA, confirmed=True)
        self.assertEqual(calls, ["unprotect"])
        verified = LeaseVerifier({"lic-p1b-fixture": key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)}).verify(envelope, self.device)
        self.assertEqual(len(verified.lease.calculation_entitlements), 29)
        self.assertEqual(envelope["expires_at"] - envelope["issued_at"], 90 * 86400)
        self.assertEqual(envelope["issuer_label"], "Quantum Studio Licence Manager")
        self.assertEqual(self.db.connection.execute("SELECT status FROM applicants WHERE application_id=?", (self.application_id,)).fetchone()[0], "LICENCE_ISSUED")
        self.assertTrue(self.db.connection.execute("SELECT 1 FROM audit_events WHERE event_id=? AND event_type='licence_issuance'", (event,)).fetchone())
        self.assertNotIn(raw, self.db.path.read_bytes())
        self.assertEqual(authority.status().state, AuthorityState.LAST_AUTHORIZED_USE_SUCCEEDED)
        self.assertIn("current protected key has not been rechecked", authority.status().message)
        with self.assertRaises(IssuanceRejected): authority.issue(self.application_id, self.request["request_id"], Profile.PROFESSOR_BETA, confirmed=True)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM licences").fetchone()[0], 1)

    def test_production_issuance_rejects_malformed_database_request_and_rolls_back_audit_failure(self):
        self.import_request(); self.authorize()
        authority = EphemeralAuthority(kid="test-lic-p1b-failure")
        self.db.connection.execute("UPDATE activation_requests SET request_json=?", ('{"schema_version":999}',)); self.db.connection.commit()
        with self.assertRaises(IssuanceRejected): issue_for_request_for_testing(self.db, authority, self.request["request_id"], confirmed=True)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM licences").fetchone()[0], 0)
        self.db.connection.execute("UPDATE activation_requests SET request_json=?,request_hash=?", (json.dumps(self.request, sort_keys=True, separators=(",", ":")), hashlib.sha256(json.dumps(self.request, sort_keys=True, separators=(",", ":")).encode()).hexdigest()))
        self.db.connection.execute("CREATE TRIGGER fail_licence_insert BEFORE INSERT ON licences BEGIN SELECT RAISE(ABORT,'test database failure'); END")
        self.db.connection.commit()
        with self.assertRaises(sqlite3.DatabaseError): issue_for_request_for_testing(self.db, authority, self.request["request_id"], confirmed=True)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM licences").fetchone()[0], 0)
        self.assertEqual(self.db.connection.execute("SELECT status FROM applicants WHERE application_id=?", (self.application_id,)).fetchone()[0], "APPROVED")
        self.db.connection.execute("DROP TRIGGER fail_licence_insert")
        self.db.connection.execute("CREATE TRIGGER fail_issuance_audit BEFORE INSERT ON audit_events WHEN NEW.event_type='successful_test_issuance' BEGIN SELECT RAISE(ABORT,'test audit failure'); END")
        self.db.connection.commit()
        with self.assertRaises(sqlite3.DatabaseError): issue_for_request_for_testing(self.db, authority, self.request["request_id"], confirmed=True)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM licences").fetchone()[0], 0)
        self.assertEqual(self.db.connection.execute("SELECT status FROM applicants WHERE application_id=?", (self.application_id,)).fetchone()[0], "APPROVED")

    def test_signing_public_metadata_mismatch_fails_closed(self):
        import operator_tools.licence_manager.signing as signing
        from cryptography.hazmat.primitives import serialization
        self.import_request(); self.authorize()
        private = Ed25519PrivateKey.generate()
        protected = self.root / "key.dpapi"; _write_protected_key_file(protected, "licence-signing-ed25519")
        metadata = self.root / "public.json"
        metadata.write_text(json.dumps({"schema_version": 1, "kid": "lic-fixture", "public_key": b64url_encode(b"x" * 32)}))
        authority = ProductionAuthority(protected, metadata, database=self.db)
        raw = private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
        with patch.object(signing.sys, "platform", "win32"), _mock_dpapi(signing, unprotected=_key_material("licence-signing-ed25519", raw)) as (calls, _):
            self.assertEqual(authority.status().state, AuthorityState.PROTECTED_KEY_PRESENT_UNVERIFIED)
            self.assertEqual(calls, [])
            with self.assertRaises(IssuanceRejected): authority.issue(self.application_id, self.request["request_id"], Profile.PROFESSOR_BETA, confirmed=True)
            self.assertEqual(calls, ["unprotect"])
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM licences").fetchone()[0], 0)
        self.assertEqual(self.db.connection.execute("SELECT status FROM applicants WHERE application_id=?", (self.application_id,)).fetchone()[0], "APPROVED")
        self.assertEqual(authority.status().state, AuthorityState.LAST_AUTHORIZED_USE_FAILED)

    def test_corrupt_protected_key_rolls_back_and_records_only_redacted_failure(self):
        import operator_tools.licence_manager.signing as signing
        self.import_request(); self.authorize()
        key_path = self.root / "corrupt-key.dpapi"; _write_protected_key_file(key_path, "licence-signing-ed25519")
        metadata_path = self.root / "public.json"
        public = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
        metadata_path.write_text(json.dumps({"schema_version": 1, "kid": "lic-corrupt-fixture", "public_key": b64url_encode(public)}))
        authority = ProductionAuthority(key_path, metadata_path, database=self.db)
        with patch.object(signing.sys, "platform", "win32"), _mock_dpapi(signing, fail_unprotect=True) as (calls, _):
            with self.assertRaises(IssuanceRejected): authority.issue(self.application_id, self.request["request_id"], Profile.PROFESSOR_BETA, confirmed=True)
            self.assertEqual(calls, ["unprotect"])
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM licences").fetchone()[0], 0)
        self.assertEqual(self.db.connection.execute("SELECT status FROM applicants WHERE application_id=?", (self.application_id,)).fetchone()[0], "APPROVED")
        details = json.dumps([row[0] for row in self.db.connection.execute("SELECT details FROM audit_events")])
        self.assertNotIn("protected test blob cannot be unwrapped", details)
        self.assertEqual(authority.status().state, AuthorityState.LAST_AUTHORIZED_USE_FAILED)

    def test_dpapi_signing_store_is_explicit_protected_and_refuses_replacement(self):
        import operator_tools.licence_manager.signing as signing
        from cryptography.hazmat.primitives import serialization
        private = Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
        wrapped = b"mock-current-user-dpapi:" + hashlib.sha256(private).digest()
        key_path = self.root / "licence-signing-key.dpapi"
        store = signing._LicenceSigningKeyStore(key_path)
        with patch.object(signing.sys, "platform", "win32"), _mock_dpapi(signing, protected=wrapped) as (calls, protected_inputs):
            store._store_protected_private_key(private)
            stored = json.loads(key_path.read_text(encoding="ascii"))
            self.assertEqual(stored["purpose"], "licence-signing-ed25519")
            self.assertEqual(b64url_decode(stored["protected_data"]), wrapped)
            self.assertEqual(json.loads(protected_inputs[0])["purpose"], "licence-signing-ed25519")
            self.assertEqual(calls, [])
            self.assertFalse(any(name in dir(store) for name in ("load_private_key", "get_private_key", "decrypt_key")))
            with self.assertRaises(SigningUnavailable): store._store_protected_private_key(private)
        self.assertNotIn(private, key_path.read_bytes())

    def test_database_transaction_rolls_back_all_mutations(self):
        before = self.db.connection.execute("SELECT COUNT(*) FROM applicants").fetchone()[0]
        with self.assertRaises(RuntimeError):
            with self.db.transaction() as db:
                db.execute("INSERT INTO applicants VALUES(?,?,?,?,?,datetime('now'))", (str(uuid.uuid4()), b"cipher", "a" * 64, "b" * 64, "APPLIED"))
                raise RuntimeError("forced transaction abort")
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM applicants").fetchone()[0], before)

    def test_test_signer_persists_only_public_metadata(self):
        from cryptography.hazmat.primitives import serialization
        authority = EphemeralAuthority(kid="test-lic-metadata")
        self.assertTrue(record_public_metadata(self.db, authority))
        row = self.db.connection.execute("SELECT public_key,domain FROM signing_keys WHERE kid=?", (authority.kid,)).fetchone()
        self.assertEqual(row[1], "test-licence")
        self.assertEqual(bytes(row[0]), authority.public_key)
        raw = authority._key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
        self.assertNotIn(raw, self.db.path.read_bytes())

    def test_deterministic_receipt_atomic_export_hash_and_offline_revocation(self):
        self.import_request(); authority = EphemeralAuthority()
        self.authorize()
        envelope, event = issue_for_request_for_testing(self.db, authority, self.request["request_id"], now=self.issue_time(), confirmed=True)
        receipt1, receipt2 = receipt_for(envelope, event), receipt_for(envelope, event)
        self.assertEqual(receipt1, receipt2)
        path, receipt_path = export_licence(self.root / "export", envelope, event, database=self.db)
        self.assertEqual(path.parent.name, envelope["licence_id"]); self.assertEqual(path.name, "licence.json")
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), json.loads(receipt_path.read_text())["licence_file_sha256"])
        self.assertTrue(revoke_licence(self.db, envelope["licence_id"], confirmed=True))
        self.assertEqual(json.loads(self.db.connection.execute("SELECT envelope_json FROM licences").fetchone()[0])["expires_at"], envelope["expires_at"])
        self.assertIn("not_immediate", self.db.connection.execute("SELECT details FROM audit_events WHERE event_type='revocation_record'").fetchone()[0])
        self.assertTrue(self.db.connection.execute("SELECT 1 FROM application_status_history WHERE new_state='REVOKED'").fetchone())

    def test_export_revalidates_stored_signature_and_audit_chain(self):
        self.import_request(); self.authorize()
        authority = EphemeralAuthority()
        envelope, event = issue_for_request_for_testing(self.db, authority, self.request["request_id"], now=self.issue_time(), confirmed=True)
        mutated = dict(envelope, policy_profile="INTERNAL_VALIDATION")
        with self.assertRaises(ValueError): export_licence(self.root / "bad-export", mutated, event, database=self.db)
        self.assertFalse((self.root / "bad-export" / f"{envelope['licence_id']}.licence.json").exists())
        self.db.connection.execute("UPDATE audit_events SET details='{}' WHERE seq=1"); self.db.connection.commit()
        with self.assertRaises(ValueError): export_licence(self.root / "bad-chain", envelope, event, database=self.db)

    def test_expiry_recording_and_audit_chain_tamper_detection(self):
        self.import_request(); authority = EphemeralAuthority()
        self.authorize()
        envelope, _ = issue_for_request_for_testing(self.db, authority, self.request["request_id"], now=self.issue_time(), confirmed=True)
        self.assertEqual(record_expiries(self.db, now=envelope["expires_at"] + 1), 1)
        self.assertEqual(self.db.connection.execute("SELECT status FROM applicants").fetchone()[0], "EXPIRED")
        self.assertTrue(self.db.connection.execute("SELECT 1 FROM application_status_history WHERE new_state='EXPIRED'").fetchone())
        ok, count, bad = verify_chain(self.db.connection)
        self.assertTrue(ok); self.assertGreater(count, 0); self.assertIsNone(bad)
        self.db.connection.execute("UPDATE audit_events SET details='{}' WHERE seq=1"); self.db.connection.commit()
        self.assertFalse(verify_chain(self.db.connection)[0])

    def test_expired_licence_can_be_administratively_revoked_with_valid_history(self):
        self.import_request(); self.authorize()
        authority = EphemeralAuthority()
        envelope, _ = issue_for_request_for_testing(self.db, authority, self.request["request_id"], now=self.issue_time(), confirmed=True)
        record_expiries(self.db, now=envelope["expires_at"] + 1)
        self.assertTrue(revoke_licence(self.db, envelope["licence_id"], confirmed=True))
        self.assertEqual(self.db.connection.execute("SELECT status FROM applicants").fetchone()[0], "REVOKED")
        history = self.db.connection.execute("SELECT previous_state,new_state FROM application_status_history WHERE new_state='REVOKED'").fetchone()
        self.assertEqual(tuple(history), ("EXPIRED", "REVOKED"))

    def test_pii_envelope_version_and_record_binding_reject_transplant(self):
        second_id = str(uuid.uuid4())
        second = dict(self.applicant, application_id=second_id, email="other@example.test")
        import_applicants_json(json.dumps({"schema_version": 1, "applications": [second]}), self.db)
        first_cipher = self.db.connection.execute("SELECT encrypted_pii FROM applicants WHERE application_id=?", (self.application_id,)).fetchone()[0]
        second_cipher = self.db.connection.execute("SELECT encrypted_pii FROM applicants WHERE application_id=?", (second_id,)).fetchone()[0]
        self.assertIn(b'"version":1', first_cipher)
        context = json.dumps({"application": "quantum-studio-licence-manager", "schema_id": "operator.sqlite3/applicants/encrypted-pii-v1", "table": "applicants", "record_id": self.application_id, "field": "encrypted_pii"}, sort_keys=True, separators=(",", ":")).encode()
        envelope = json.loads(first_cipher)
        envelope["version"] = 2
        with self.assertRaises(ProtectionUnavailable): self.protector.decrypt(json.dumps(envelope).encode(), aad=context)
        with self.assertRaises(ProtectionUnavailable): DataProtector.for_testing(b"W" * 32).decrypt(first_cipher, aad=context)
        self.db.connection.execute("UPDATE applicants SET encrypted_pii=? WHERE application_id=?", (first_cipher, second_id)); self.db.connection.commit()
        with self.assertRaises(ProtectionUnavailable): self.db.applicant_pii(second_id)
        self.db.connection.execute("UPDATE applicants SET encrypted_pii=? WHERE application_id=?", (second_cipher, second_id)); self.db.connection.commit()
        with self.assertRaises(ProtectionUnavailable): self.protector.decrypt(first_cipher, aad=b'{"application":"other"}')
        with self.assertRaises(ProtectionUnavailable): self.protector.decrypt(first_cipher[:-1], aad=context)

    def test_email_normalization_and_duplicate_identity_policy(self):
        self.assertEqual(normalize_applicant_email("  ADa@Example.test  "), "ada@example.test")
        self.assertEqual(normalize_applicant_email("e\u0301@example.test"), normalize_applicant_email("é@example.test"))
        other = dict(self.applicant, application_id=str(uuid.uuid4()), email=" ADA@EXAMPLE.TEST ")
        self.assertEqual(import_applicants_json(json.dumps({"schema_version": 1, "applications": [other]}), self.db), 0)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM applicants").fetchone()[0], 1)

    def test_audit_chain_detects_middle_removal_and_reordering_but_not_unanchored_tail_truncation(self):
        import sqlite3
        from operator_tools.licence_manager.audit import append_event
        connection = sqlite3.connect(":memory:")
        connection.executescript("CREATE TABLE audit_events(seq INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE,timestamp TEXT,event_type TEXT,operator_id TEXT,affected_ids TEXT,details TEXT,previous_hash TEXT,event_hash TEXT);")
        for name in ("one", "two", "three"):
            append_event(connection, name, "operator", (), {})
        original = connection.execute("SELECT * FROM audit_events ORDER BY seq").fetchall()
        connection.execute("DELETE FROM audit_events WHERE seq=3")
        self.assertTrue(verify_chain(connection)[0], "unanchored tail removal cannot be detected")
        connection.execute("DELETE FROM audit_events"); connection.executemany("INSERT INTO audit_events VALUES(?,?,?,?,?,?,?,?,?)", original)
        connection.execute("DELETE FROM audit_events WHERE seq=2")
        self.assertFalse(verify_chain(connection)[0])
        connection.execute("DELETE FROM audit_events"); connection.executemany("INSERT INTO audit_events VALUES(?,?,?,?,?,?,?,?,?)", original)
        connection.execute("UPDATE audit_events SET seq=-seq")
        self.assertFalse(verify_chain(connection)[0])
        connection.close()

    def test_import_size_utf8_depth_and_field_limits_are_bounded(self):
        from operator_tools.licence_manager.imports import _json
        self.assertEqual(_json(b"{}" + b" " * (MAX_ACTIVATION_IMPORT_BYTES - 3), MAX_ACTIVATION_IMPORT_BYTES), {})
        self.assertEqual(_json(b"{}" + b" " * (MAX_ACTIVATION_IMPORT_BYTES - 2), MAX_ACTIVATION_IMPORT_BYTES), {})
        with self.assertRaises(ImportRejected): _json(b"{}" + b" " * (MAX_ACTIVATION_IMPORT_BYTES - 1), MAX_ACTIVATION_IMPORT_BYTES)
        with self.assertRaises(ImportRejected): _json(b"\xff", MAX_ACTIVATION_IMPORT_BYTES)
        with self.assertRaises(ImportRejected): _json(("[" * 10) + "0" + ("]" * 10), MAX_ACTIVATION_IMPORT_BYTES)
        with self.assertRaises(ImportRejected): _json('{"value":1e10000}', MAX_ACTIVATION_IMPORT_BYTES)
        self.assertEqual(_json("{}" + " " * (MAX_APPLICANT_IMPORT_BYTES - 2), MAX_APPLICANT_IMPORT_BYTES), {})
        with self.assertRaises(ImportRejected): _json("{}" + " " * (MAX_APPLICANT_IMPORT_BYTES - 1), MAX_APPLICANT_IMPORT_BYTES)
        class OversizedStream:
            def read(self, count): return b"{}" + b" " * count
        with self.assertRaises(ImportRejected): _json(OversizedStream(), MAX_ACTIVATION_IMPORT_BYTES)
        bad = dict(self.applicant, full_name="x" * 257)
        with self.assertRaises(ImportRejected): import_applicants_json(json.dumps({"schema_version": 1, "applications": [bad]}), self.db)
        self.approve()
        oversized_request = dict(self.request, device_public_key="A" * 44)
        with self.assertRaises(ImportRejected): import_activation_json(json.dumps(oversized_request), self.db)

    def test_failed_commit_and_rollback_recover_connection(self):
        real = self.db.connection
        class FailingConnection:
            def __init__(self, raw, *, rollback_fails=False): self.raw=raw; self.commit_fails=True; self.rollback_fails=rollback_fails
            @property
            def in_transaction(self): return self.raw.in_transaction
            def execute(self, *args, **kwargs): return self.raw.execute(*args, **kwargs)
            def commit(self):
                if self.commit_fails: self.commit_fails=False; raise sqlite3.OperationalError("injected commit failure")
                return self.raw.commit()
            def rollback(self):
                if self.rollback_fails: self.rollback_fails=False; raise sqlite3.OperationalError("injected rollback failure")
                return self.raw.rollback()
            def close(self): return self.raw.close()
        self.db.connection = FailingConnection(real)
        with self.assertRaisesRegex(sqlite3.OperationalError, "injected commit failure"):
            with self.db.transaction() as db: db.execute("INSERT INTO audit_events(event_id,timestamp,event_type,operator_id,affected_ids,details,previous_hash,event_hash) VALUES('x','t','x','o','[]','{}','','')")
        self.assertFalse(self.db.connection.in_transaction)
        with self.db.transaction() as db: db.execute("INSERT INTO audit_events(event_id,timestamp,event_type,operator_id,affected_ids,details,previous_hash,event_hash) VALUES('y','t','x','o','[]','{}','','')")
        self.db.connection = FailingConnection(self.db.connection, rollback_fails=True)
        with self.assertRaisesRegex(sqlite3.OperationalError, "injected commit failure"):
            with self.db.transaction() as db: db.execute("INSERT INTO audit_events(event_id,timestamp,event_type,operator_id,affected_ids,details,previous_hash,event_hash) VALUES('z','t','x','o','[]','{}','','')")
        self.assertFalse(self.db.connection.in_transaction)
        with self.db.transaction() as db: db.execute("INSERT INTO audit_events(event_id,timestamp,event_type,operator_id,affected_ids,details,previous_hash,event_hash) VALUES('w','t','x','o','[]','{}','','')")
        self.assertIsNotNone(self.db.connection.execute("SELECT 1 FROM audit_events WHERE event_id='w'").fetchone())

    def test_issuance_audit_and_database_failures_leave_no_issued_state_and_allow_retry(self):
        self.import_request(); self.authorize()
        import operator_tools.licence_manager.issuance as issuance
        original = issuance.append_event
        def fail_success(db, event_type, *args, **kwargs):
            if event_type == "successful_test_issuance": raise sqlite3.OperationalError("injected audit failure")
            return original(db, event_type, *args, **kwargs)
        with patch.object(issuance, "append_event", side_effect=fail_success):
            with self.assertRaises(sqlite3.OperationalError): issue_for_request_for_testing(self.db, EphemeralAuthority(), self.request["request_id"], now=self.issue_time(), confirmed=True)
        self.assertFalse(self.db.connection.in_transaction)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM licences").fetchone()[0], 0)
        self.assertEqual(self.db.connection.execute("SELECT status FROM applicants").fetchone()[0], "APPROVED")
        self.assertEqual(self.db.connection.execute("SELECT authorized_profile FROM activation_requests").fetchone()[0], "PROFESSOR_BETA")
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM licences WHERE request_id=?", (self.request["request_id"],)).fetchone()[0], 0)
        trigger = "CREATE TRIGGER reject_licence_insert BEFORE INSERT ON licences BEGIN SELECT RAISE(ABORT,'injected write failure'); END"
        self.db.connection.execute(trigger); self.db.connection.commit()
        with self.assertRaises(sqlite3.IntegrityError): issue_for_request_for_testing(self.db, EphemeralAuthority(), self.request["request_id"], now=self.issue_time(), confirmed=True)
        self.assertFalse(self.db.connection.in_transaction)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM licences").fetchone()[0], 0)
        self.assertEqual(self.db.connection.execute("SELECT status FROM applicants WHERE application_id=?", (self.application_id,)).fetchone()[0], "APPROVED")
        self.db.connection.execute("DROP TRIGGER reject_licence_insert"); self.db.connection.commit()
        result = issue_for_request_for_testing(self.db, EphemeralAuthority(), self.request["request_id"], now=self.issue_time(), confirmed=True)
        self.assertTrue(result[0]["licence_id"])

    def test_export_bundle_is_idempotent_atomic_and_rejects_conflicts_and_symlinks(self):
        self.import_request(); self.authorize()
        envelope, event = issue_for_request_for_testing(self.db, EphemeralAuthority(), self.request["request_id"], now=self.issue_time(), confirmed=True)
        root = self.root / "bundle-export"
        with patch("operator_tools.licence_manager.exports._write_synced", side_effect=OSError("injected stage failure")):
            with self.assertRaises(OSError): export_licence(root, envelope, event, database=self.db)
        final = root / envelope["licence_id"]
        self.assertFalse(final.exists())
        original_write = __import__("operator_tools.licence_manager.exports", fromlist=["_write_synced"])._write_synced
        calls = {"count": 0}
        def fail_after_licence(path, data):
            calls["count"] += 1
            if calls["count"] == 2: raise OSError("injected receipt staging interruption")
            return original_write(path, data)
        with patch("operator_tools.licence_manager.exports._write_synced", side_effect=fail_after_licence):
            with self.assertRaises(OSError): export_licence(root, envelope, event, database=self.db)
        self.assertFalse(final.exists())
        with patch("operator_tools.licence_manager.exports._publish_directory_noreplace", side_effect=OSError("injected rename failure")):
            with self.assertRaises(OSError): export_licence(root, envelope, event, database=self.db)
        self.assertFalse(final.exists())
        licence_path, receipt_path = export_licence(root, envelope, event, database=self.db)
        self.assertEqual(licence_path.read_bytes(), export_licence(root, envelope, event, database=self.db)[0].read_bytes())
        self.assertEqual(hashlib.sha256(licence_path.read_bytes()).hexdigest(), json.loads(receipt_path.read_text())["licence_file_sha256"])
        with patch("operator_tools.licence_manager.exports._record_export", side_effect=OSError("injected post-publication audit failure")):
            with self.assertRaises(OSError): export_licence(self.root / "post-commit-export", envelope, event, database=self.db)
        recover_root = self.root / "post-commit-export"
        recovered = export_licence(recover_root, envelope, event, database=self.db)
        self.assertTrue(recovered[0].is_file() and recovered[1].is_file())
        partial_root = self.root / "partial-export"; partial = partial_root / envelope["licence_id"]
        partial.mkdir(parents=True); (partial / "licence.json").write_bytes(licence_path.read_bytes())
        with self.assertRaises(ExportRecoveryError): export_licence(partial_root, envelope, event, database=self.db)
        (final / "receipt.json").write_text("{}")
        with self.assertRaises(ExportRecoveryError): export_licence(root, envelope, event, database=self.db)
        link = self.root / "export-link"
        try: link.symlink_to(root, target_is_directory=True)
        except (OSError, NotImplementedError): return
        with self.assertRaises(ExportRecoveryError): export_licence(link, envelope, event, database=self.db)

    def test_protected_store_has_no_public_decryption_or_direct_signing_api(self):
        import operator_tools.licence_manager.signing as signing
        store = signing._LicenceSigningKeyStore(self.root / "key.dpapi")
        for name in ("load_private_key", "get_private_key", "decrypt_key", "private_key"):
            self.assertFalse(hasattr(store, name))
        with self.assertRaises(SigningUnavailable): store._sign_authorized_lease({}, "lic-a", b"x" * 32, object())

    def test_installer_boundary_reaudits_bundle_and_metadata(self):
        root = self.root / "installer-bundle"; root.mkdir()
        for relative in ("QuantumStudio.exe", "assets/quantum-studio-v0.1.svg", "PySide6/qt-plugins/platforms/qwindows.dll", "cryptography/hazmat/bindings/_rust.pyd"):
            target = root / relative; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(b"fixture")
        marker = {"schema_version": 1, "product": "Quantum Studio", "version": "0.2.0", "channel": "beta", "platform": "windows", "architecture": "x86_64", "commit": "abc1234", "dirty": False, "build_timestamp":"2026-01-01T00:00:00+00:00", "python":"3.13.0", "pyside6":"6.9.0", "nuitka":"2.7.0", "packaging_format":"nuitka-standalone", "entry_executable": "QuantumStudio.exe", "resource_manifest":"assets/quantum-studio-v0.1.svg"}
        (root / "quantumstudio-build.json").write_text(json.dumps(marker))
        inputs = {"schema_version": 1, "product": "Quantum Studio", "version": "0.2.0", "channel":"beta", "platform": "windows", "architecture": "x86_64", "gui_bundle": {"path":"QuantumStudio.dist", "entry": "QuantumStudio.exe"}, "runtime_image": {"status":"PENDING_W7","descriptor":None}, "runtime_agent":{"protocol_schema":1,"status":"included-in-runtime-image"}, "engine_pack": {"status":"PENDING_LEGAL_AND_W7","descriptor":None}, "licenses_notices":{"status":"PENDING_W7","inputs":[]}, "build_manifest": marker}
        (root / "quantumstudio-installer-input.json").write_text(json.dumps(inputs))
        generate_payload_inventory(root, marker, generated_at="2026-01-01T00:00:00+00:00")
        self.assertTrue(validate_installer_bundle(root)["valid"])
        manager = root / "operator_tools" / "licence_manager"; manager.mkdir(parents=True); (manager / "data.sqlite3").write_bytes(b"x")
        with self.assertRaises(ValueError): validate_installer_bundle(root)
        (root / "quantumstudio-installer-input.json").unlink()
        with self.assertRaises(ValueError): validate_installer_bundle(root)
        (root / "quantumstudio-installer-input.json").write_text(json.dumps(inputs))
        (root / "operator_tools").rename(root / "operator-tools-removed")
        (root / "pw.x").write_bytes(b"engine")
        with self.assertRaises(ValueError): validate_installer_bundle(root)
        link = self.root / "bundle-link"
        try: link.symlink_to(root, target_is_directory=True)
        except (OSError, NotImplementedError): return
        with self.assertRaises(ValueError): validate_installer_bundle(link)
        (root / "pw.x").unlink(); inputs["version"] = "mismatch"; (root / "quantumstudio-installer-input.json").write_text(json.dumps(inputs))
        with self.assertRaises(ValueError): validate_installer_bundle(root)

    def test_test_ui_modes_and_customer_package_exclusion(self):
        app = QApplication.instance() or QApplication([])
        window = LicenceManagerWindow(test_mode=True, database=self.db, authority=EphemeralAuthority())
        self.addCleanup(window.close)
        self.assertIn("TEST MODE", window.mode_banner.text())
        production = LicenceManagerWindow(test_mode=False, database=self.db, authority=ProductionAuthority(self.root / "missing", self.root / "no.json"))
        self.addCleanup(production.close)
        self.assertIn("Production signing authority is not initialized.", production.authority_banner.text())
        staging = self.root / "bundle"; (staging / "frontend").mkdir(parents=True)
        (staging / "frontend" / "main.py").write_text("pass")
        self.assertEqual(customer_package_exclusion_findings(staging), ())
        (staging / "operator_tools" / "licence_manager").mkdir(parents=True)
        (staging / "operator_tools" / "licence_manager" / "crypto.py").write_text("pass")
        self.assertTrue(customer_package_exclusion_findings(staging))
        self.assertIn("operator_tools/licence_manager/crypto.py", audit_package_contents(staging)["forbidden"])
        app.processEvents()

    def test_ui_mode_never_falls_back_between_production_and_test_authorities(self):
        app = QApplication.instance() or QApplication([])
        production = LicenceManagerWindow(test_mode=False, database=self.db, data_root_override=self.root)
        self.addCleanup(production.close)
        self.assertIsInstance(production.authority, ProductionAuthority)
        test = LicenceManagerWindow(test_mode=True, database=self.db)
        self.addCleanup(test.close)
        self.assertIsInstance(test.authority, EphemeralAuthority)
        self.assertNotIsInstance(production.authority, EphemeralAuthority)
        app.processEvents()

    def test_issue_ui_calls_only_identifier_profile_production_api(self):
        from unittest.mock import Mock
        self.import_request(); self.authorize()
        app = QApplication.instance() or QApplication([])
        window = LicenceManagerWindow(test_mode=False, database=self.db, data_root_override=self.root)
        self.addCleanup(window.close)
        window.requests_table.selectRow(0)
        window.authority.issue = Mock(return_value=({"licence_id": "lic_fixture"}, "audit_fixture"))
        with patch("operator_tools.licence_manager.main_window.QInputDialog.getItem", return_value=("PROFESSOR_BETA", True)), \
             patch("operator_tools.licence_manager.main_window.QMessageBox.question", return_value=QMessageBox.Yes), \
             patch("operator_tools.licence_manager.main_window.QMessageBox.information"):
            window.issue_selected()
        window.authority.issue.assert_called_once_with(self.application_id, self.request["request_id"], Profile.PROFESSOR_BETA, confirmed=True)
        app.processEvents()

    def test_customer_build_plan_does_not_include_manager(self):
        repo = Path(__file__).resolve().parents[2]
        plan = build_plan(repo=repo, output=self.root / "build", channel="beta", version="0.2.0", commit="test", dirty=True, python_executable="python")
        args = " ".join(plan.nuitka_argv).casefold()
        self.assertNotIn("operator_tools", args)
        self.assertNotIn("run_licence_manager", args)

    def test_windows_and_linux_package_roots_reject_operator_tool_paths(self):
        windows = self.root / "Windows.dist"
        for relative in ("QuantumStudio.exe", "assets/quantum-studio-v0.1.svg", "PySide6/qt-plugins/platforms/qwindows.dll", "cryptography/hazmat/bindings/_rust.pyd"):
            target = windows / relative; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(b"fixture")
        (windows / "operator_tools" / "licence_manager").mkdir(parents=True)
        findings = audit_package_contents(windows)
        self.assertFalse(findings["valid"])
        self.assertTrue(any("operator_tools" in value for value in findings["forbidden"]))
        linux_appdir = self.root / "QuantumStudio.AppDir"
        linux = linux_appdir / "usr" / "bin"
        (linux / "operator_tools" / "licence_manager").mkdir(parents=True)
        self.assertTrue(customer_package_exclusion_findings(linux_appdir))

    def test_windows_installer_payload_rejects_operator_tool_paths(self):
        payload = self.root / "installer-payload"
        manager = payload / "operator_tools" / "licence_manager"
        manager.mkdir(parents=True)
        (manager / "main_window.py").write_text("operator only")
        findings = audit_installer_payload(payload, declared=())
        self.assertFalse(findings["valid"])
        self.assertTrue(findings["forbidden"])


if __name__ == "__main__":
    unittest.main()
