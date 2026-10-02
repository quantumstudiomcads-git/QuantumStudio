from __future__ import annotations

import base64
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

from backend.licensing.canonical import b64url_encode
from backend.licensing.models import ImplementationState
from backend.licensing.service import LicensingService
from backend.licensing.verifier import LeaseValidationError, LeaseVerifier, device_identity_from_private_key
from backend.licensing.enforcement import CalculationAuthorizationBoundary
from backend.calculations import registry
from operator_tools.licence_manager.audit import verify_chain
from operator_tools.licence_manager.crypto import DataProtector, ProtectionUnavailable
from operator_tools.licence_manager.database import Database
from operator_tools.licence_manager.exports import export_licence, receipt_for
from operator_tools.licence_manager.imports import ImportRejected, import_activation_json, import_applicants_json
from operator_tools.licence_manager.issuance import (IssuanceRejected, authorize_activation_profile,
    issue_for_request_for_testing, record_expiries, revoke_licence)
from operator_tools.licence_manager.main_window import LicenceManagerWindow
from operator_tools.licence_manager.models import ApplicantStatus, Profile
from operator_tools.licence_manager.policy import derive_profile
from operator_tools.licence_manager.signing import (LicenceSigningKeyStore, ProductionAuthority,
    AuthorityState, SigningUnavailable, TestEphemeralAuthority as EphemeralAuthority, record_public_metadata)
from scripts.package_exclusions import customer_package_exclusion_findings
from scripts.windows_packaging import audit_package_contents, build_plan
from scripts.windows_installer.payload_audit import audit_installer_payload
from frontend.calculations.catalog import CALCULATIONS
from frontend.calculations.reconciliation import ExecutionSupport, reconcile_catalog


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
        self.assertEqual(self.db.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 2)
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
        self.assertEqual(upgraded.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 2)

    def test_raw_pii_keys_are_test_only_and_json_duplicate_fields_reject(self):
        with self.assertRaises(ProtectionUnavailable): DataProtector(b"K" * 32)
        with self.assertRaises(ImportRejected): import_applicants_json('{"schema_version":1,"schema_version":1,"applications":[]}', self.db)
        from operator_tools.licence_manager import crypto
        protected_path = self.root / "unsupported.dpapi"
        with patch.object(crypto.sys, "platform", "linux"):
            with self.assertRaises(ProtectionUnavailable): DataProtector.from_windows_keyfile(protected_path)
        self.assertFalse(protected_path.exists())

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
        with patch.object(signing, "dpapi_unprotect", side_effect=AssertionError("status decrypted key")) as unprotect:
            authority = ProductionAuthority(self.root / "key.dpapi", self.root / "public.json", database=self.db)
            unprotect.assert_not_called()
            self.assertEqual(authority.status().state, AuthorityState.UNINITIALIZED)
            public_key = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
            authority.metadata_path.write_text(json.dumps({"schema_version": 1, "kid": "lic-status", "public_key": b64url_encode(public_key)}))
            self.assertEqual(authority.status().state, AuthorityState.PROTECTED_KEY_MISSING)
            authority.key_path.write_bytes(b"opaque protected test blob")
            first = authority.status()
            second = authority.status()
            self.assertEqual(first.state, AuthorityState.PROTECTED_KEY_PRESENT_UNVERIFIED)
            self.assertIn("validated only during an authorized issuance", first.message)
            self.assertEqual(second.state, AuthorityState.PROTECTED_KEY_PRESENT_UNVERIFIED)
            unprotect.assert_not_called()

    def test_status_reports_invalid_metadata_without_decrypting(self):
        import operator_tools.licence_manager.signing as signing
        authority = ProductionAuthority(self.root / "key.dpapi", self.root / "public.json", database=self.db)
        authority.metadata_path.write_text("{broken")
        authority.key_path.write_bytes(b"opaque protected test blob")
        with patch.object(signing, "dpapi_unprotect", side_effect=AssertionError("invalid metadata status decrypted key")) as unprotect:
            status = authority.status()
            self.assertEqual(status.state, AuthorityState.METADATA_INVALID)
            self.assertEqual(status.message, "Signing authority metadata is invalid.")
            unprotect.assert_not_called()

    def test_window_startup_refresh_import_and_profile_selection_never_decrypt_signing_key(self):
        import operator_tools.licence_manager.signing as signing
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        authority = ProductionAuthority(self.root / "missing.dpapi", self.root / "missing.json", database=self.db)
        with patch.object(signing, "dpapi_unprotect", side_effect=AssertionError("UI decrypted signing key")) as unprotect:
            window = LicenceManagerWindow(test_mode=False, database=self.db, authority=authority)
            self.addCleanup(window.close)
            window.refresh()
            import_applicants_json(json.dumps({"schema_version": 1, "applications": []}), self.db)
            unprotect.assert_not_called()
            self.approve(); import_activation_json(json.dumps(self.request), self.db)
            unprotect.assert_not_called()
            window.refresh()
            window.requests_table.selectRow(0)
            with patch("operator_tools.licence_manager.main_window.QInputDialog.getItem", return_value=("PROFESSOR_BETA", True)), \
                 patch("operator_tools.licence_manager.main_window.QMessageBox.question", side_effect=[QMessageBox.Yes, QMessageBox.No]):
                window.issue_selected()
            unprotect.assert_not_called()
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
        with patch.object(authority, "_load", side_effect=AssertionError("key load before authorization")) as load:
            with self.assertRaises(IssuanceRejected): authority.issue(self.application_id, self.request["request_id"], Profile.PROFESSOR_BETA, confirmed=True)
            load.assert_not_called()
            self.import_request(); self.authorize()
            with self.assertRaises(IssuanceRejected): authority.issue(str(uuid.uuid4()), self.request["request_id"], Profile.PROFESSOR_BETA, confirmed=True)
            load.assert_not_called()
            self.db.connection.execute("UPDATE applicants SET status='REJECTED' WHERE application_id=?", (self.application_id,)); self.db.connection.commit()
            with self.assertRaises(IssuanceRejected): authority.issue(self.application_id, self.request["request_id"], Profile.PROFESSOR_BETA, confirmed=True)
            load.assert_not_called()
            self.db.connection.execute("UPDATE applicants SET status='APPROVED' WHERE application_id=?", (self.application_id,)); self.db.connection.commit()
            self.db.transition(self.application_id, ApplicantStatus.REVOKED)
            with self.assertRaises(IssuanceRejected): authority.issue(self.application_id, self.request["request_id"], Profile.PROFESSOR_BETA, confirmed=True)
            load.assert_not_called()

    def test_missing_confirmation_invalid_profile_and_policy_failure_do_not_load_key(self):
        import operator_tools.licence_manager.issuance as issuance
        authority = ProductionAuthority(self.root / "missing.dpapi", self.root / "missing.json", database=self.db)
        self.import_request(); self.authorize()
        with patch.object(authority, "_load", side_effect=AssertionError("unauthorized key load")) as load:
            with self.assertRaises(IssuanceRejected): authority.issue(self.application_id, self.request["request_id"], Profile.PROFESSOR_BETA)
            with self.assertRaises(IssuanceRejected): authority.issue(self.application_id, self.request["request_id"], "NOT_A_PROFILE", confirmed=True)
            with patch.object(issuance, "derive_profile", side_effect=IssuanceRejected("fixture policy failure")):
                with self.assertRaises(IssuanceRejected): authority.issue(self.application_id, self.request["request_id"], Profile.PROFESSOR_BETA, confirmed=True)
            load.assert_not_called()
            stored_json = self.db.connection.execute("SELECT request_json FROM activation_requests WHERE request_id=?", (self.request["request_id"],)).fetchone()[0]
            self.db.connection.execute("UPDATE activation_requests SET request_json=?", ('{"schema_version":999}',)); self.db.connection.commit()
            with self.assertRaises(IssuanceRejected): authority.issue(self.application_id, self.request["request_id"], Profile.PROFESSOR_BETA, confirmed=True)
            load.assert_not_called()
            self.db.connection.execute("UPDATE activation_requests SET request_json=?", (stored_json,)); self.db.connection.commit()

    def test_production_issue_signs_only_database_derived_lease(self):
        import operator_tools.licence_manager.signing as signing
        from cryptography.hazmat.primitives import serialization
        self.import_request(); self.authorize()
        key = Ed25519PrivateKey.generate()
        raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
        protected = self.root / "key.dpapi"; protected.write_bytes(b"opaque protected test blob")
        metadata = self.root / "public.json"
        metadata.write_text(json.dumps({"schema_version": 1, "kid": "lic-p1b-fixture", "public_key": b64url_encode(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))}))
        authority = ProductionAuthority(protected, metadata, database=self.db)
        def unprotect_after_checks(blob):
            self.assertEqual(blob, b"opaque protected test blob")
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
        with patch.object(signing.sys, "platform", "win32"), patch.object(signing, "dpapi_unprotect", side_effect=unprotect_after_checks) as unprotect:
            envelope, event = authority.issue(self.application_id, self.request["request_id"], Profile.PROFESSOR_BETA, confirmed=True)
        unprotect.assert_called_once()
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
        protected = self.root / "key.dpapi"; protected.write_bytes(b"opaque protected test blob")
        metadata = self.root / "public.json"
        metadata.write_text(json.dumps({"schema_version": 1, "kid": "lic-fixture", "public_key": b64url_encode(b"x" * 32)}))
        authority = ProductionAuthority(protected, metadata, database=self.db)
        raw = private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
        with patch.object(signing.sys, "platform", "win32"), patch.object(signing, "dpapi_unprotect", return_value=raw) as unprotect:
            self.assertEqual(authority.status().state, AuthorityState.PROTECTED_KEY_PRESENT_UNVERIFIED)
            unprotect.assert_not_called()
            with self.assertRaises(IssuanceRejected): authority.issue(self.application_id, self.request["request_id"], Profile.PROFESSOR_BETA, confirmed=True)
            unprotect.assert_called_once()
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM licences").fetchone()[0], 0)
        self.assertEqual(self.db.connection.execute("SELECT status FROM applicants WHERE application_id=?", (self.application_id,)).fetchone()[0], "APPROVED")
        self.assertEqual(authority.status().state, AuthorityState.LAST_AUTHORIZED_USE_FAILED)

    def test_corrupt_protected_key_rolls_back_and_records_only_redacted_failure(self):
        import operator_tools.licence_manager.signing as signing
        self.import_request(); self.authorize()
        key_path = self.root / "corrupt-key.dpapi"; key_path.write_bytes(b"opaque corrupted test blob")
        metadata_path = self.root / "public.json"
        public = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
        metadata_path.write_text(json.dumps({"schema_version": 1, "kid": "lic-corrupt-fixture", "public_key": b64url_encode(public)}))
        authority = ProductionAuthority(key_path, metadata_path, database=self.db)
        with patch.object(signing.sys, "platform", "win32"), patch.object(signing, "dpapi_unprotect", side_effect=ProtectionUnavailable("protected test blob cannot be unwrapped")) as unprotect:
            with self.assertRaises(IssuanceRejected): authority.issue(self.application_id, self.request["request_id"], Profile.PROFESSOR_BETA, confirmed=True)
            unprotect.assert_called_once()
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
        store = LicenceSigningKeyStore(key_path)
        with patch.object(signing.sys, "platform", "win32"), patch.object(signing, "dpapi_protect", return_value=wrapped), patch.object(signing, "dpapi_unprotect", return_value=private):
            store.store_protected_private_key(private)
            self.assertEqual(store.load_private_key(), private)
            self.assertEqual(key_path.read_bytes(), wrapped)
            with self.assertRaises(SigningUnavailable): store.store_protected_private_key(private)
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
        self.assertTrue(path.name.startswith("lic_")); self.assertNotIn("ada", path.name.casefold())
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
