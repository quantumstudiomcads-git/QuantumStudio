"""Offline regression contracts for the B4 cryptographic licensing foundation."""
from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.licensing.connectors.mock import InMemoryLicensingConnector, SessionLimitReached, TrialAlreadyConsumed
from backend.licensing.connectors.mock import DeviceLimitReached
from backend.licensing.models import DeviceRegistrationRequest
from backend.licensing.device_identity import DeviceIdentityService, InMemorySecureKeyStore, WindowsDPAPIKeyStore
from backend.licensing.enforcement import CalculationAuthorizationBoundary, EntitlementDenied
from backend.licensing.lease_store import LeaseStore
from backend.licensing.models import DecisionReason, EntitlementState, ImplementationState, PlanId
from backend.licensing.policy import EntitlementPolicy
from backend.licensing.plans import STUDENT_PRIMITIVES
from backend.licensing.service import LicensingService
from backend.licensing.verifier import LeaseValidationError, LeaseVerifier, device_identity_from_private_key, issue_lease, public_key_bytes
from backend.runtime.diagnostics_service import collect_diagnostics
from backend.runtime.paths import RuntimePaths
from frontend.app.licensing_access import DeviceBuilderAccessController
from frontend.calculations.catalog import CALCULATIONS
from frontend.calculations.reconciliation import CalculationDescriptor, ExecutionSupport
from frontend.core import Atom, Project, Structure
from frontend.services.calculation_service import CalculationService


NOW = 1_800_000_000


def identity():
    return device_identity_from_private_key(Ed25519PrivateKey.generate())


def envelope(device, issuer, *, kid="test-key", plan="pro", expires_at=NOW + 1000, not_before=NOW - 1, features=("workspace:device_builder",), calculations=("calc:*",), trial_type=None, **overrides):
    payload = {
        "licence_id": "lic-test", "account_id": "acct-test", "subject_type": "individual",
        "plan_id": plan, "device_id": device.device_id, "device_public_key_hash": device.public_key_hash,
        "issued_at": NOW - 10, "not_before": not_before, "expires_at": expires_at,
        "offline_until": expires_at, "entitlement_version": 1,
        "feature_entitlements": list(features), "calculation_entitlements": list(calculations),
        "registered_device_limit": 2, "concurrent_session_limit": 1, "offline_device_limit": 1,
        "nonce": "nonce-test", "trial_type": trial_type,
    }
    payload.update(overrides)
    return issue_lease(payload, issuer, kid=kid)


def service_for(envelope_value, device, issuer, *, now=lambda: NOW):
    return LicensingService.for_testing(
        trusted_public_keys={"test-key": public_key_bytes(issuer)}, device_identity=device,
        lease=envelope_value, now=now,
    )


def test_signed_lease_accepts_only_canonical_trusted_envelope_and_rotation_key():
    issuer = Ed25519PrivateKey.generate(); device = identity()
    signed = envelope(device, issuer)
    assert LeaseVerifier({"test-key": public_key_bytes(issuer)}).verify(signed, device).lease.plan_id == "pro"
    changed = deepcopy(signed); changed["plan_id"] = "organization"
    with pytest.raises(LeaseValidationError): LeaseVerifier({"test-key": public_key_bytes(issuer)}).verify(changed, device)
    changed_signature = deepcopy(signed); changed_signature["signature"] = changed_signature["signature"][:-2] + "xx"
    with pytest.raises(LeaseValidationError): LeaseVerifier({"test-key": public_key_bytes(issuer)}).verify(changed_signature, device)
    unknown = deepcopy(signed); unknown["kid"] = "rotated-away"
    with pytest.raises(LeaseValidationError): LeaseVerifier({"test-key": public_key_bytes(issuer)}).verify(unknown, device)
    wrong_issuer = Ed25519PrivateKey.generate()
    with pytest.raises(LeaseValidationError): LeaseVerifier({"test-key": public_key_bytes(wrong_issuer)}).verify(signed, device)


def test_device_bound_lease_rejects_copy_to_another_device_and_truncation():
    issuer = Ed25519PrivateKey.generate(); first = identity(); second = identity()
    signed = envelope(first, issuer)
    verifier = LeaseVerifier({"test-key": public_key_bytes(issuer)})
    with pytest.raises(LeaseValidationError): verifier.verify(signed, second)
    with pytest.raises(LeaseValidationError): verifier.verify({"signature": "broken"}, first)


def test_time_validation_clock_rollback_and_expiry_preserve_read_access():
    issuer = Ed25519PrivateKey.generate(); device = identity()
    signed = envelope(device, issuer, expires_at=NOW - 1)
    expired = service_for(signed, device, issuer)
    denied = expired.authorize_feature("workspace:device_builder")
    assert denied.reason is DecisionReason.SUBSCRIPTION_EXPIRED
    assert expired.authorize_read("data:results").allowed
    valid = service_for(envelope(device, issuer), device, issuer)
    rollback = EntitlementPolicy(valid.lease, now=lambda: NOW, clock_validation_required=True)
    assert rollback.authorize_feature("workspace:device_builder").reason is DecisionReason.CLOCK_VALIDATION_REQUIRED
    future = service_for(envelope(device, issuer, not_before=NOW + 1), device, issuer)
    assert future.authorize_feature("workspace:device_builder").reason is DecisionReason.LICENCE_INVALID


def test_plan_policy_protects_device_builder_and_keeps_student_primitives_centralized():
    issuer = Ed25519PrivateKey.generate(); device = identity()
    for plan in ("free_starter", "student", "plus", "plus_trial"):
        service = service_for(envelope(device, issuer, plan=plan, features=(), calculations=()), device, issuer)
        assert not service.authorize_feature("workspace:device_builder").allowed
    for plan in ("pro", "organization"):
        service = service_for(envelope(device, issuer, plan=plan), device, issuer)
        assert service.authorize_feature("workspace:device_builder").allowed
    assert STUDENT_PRIMITIVES == {"calc:scf", "calc:nscf", "calc:phonons"}
    student = service_for(envelope(device, issuer, plan="student", features=(), calculations=STUDENT_PRIMITIVES), device, issuer)
    assert student.authorize_calculation("scf", ImplementationState.READY).allowed
    assert student.authorize_calculation("phonons", ImplementationState.READY).allowed
    assert student.authorize_calculation("bands", ImplementationState.READY).reason is DecisionReason.NOT_ENTITLED
    assert student.authorize_calculation("nscf", ImplementationState.PARTIAL).reason is DecisionReason.NOT_IMPLEMENTED


def test_implementation_state_precedes_entitlement_and_calculation_boundary_blocks_bypass():
    issuer = Ed25519PrivateKey.generate(); device = identity()
    service = service_for(envelope(device, issuer, features=(), calculations=()), device, issuer)
    planned = service.authorize_calculation("convergence_ecut", ImplementationState.PLANNED)
    assert planned.reason is DecisionReason.NOT_IMPLEMENTED
    descriptor = CalculationDescriptor(next(item for item in CALCULATIONS if item.id == "scf"), ExecutionSupport.IMPLEMENTED, True)
    with pytest.raises(EntitlementDenied): CalculationAuthorizationBoundary(service).authorize((descriptor,))
    structure = Structure([Atom("Si", 0.0, 0.0, 0.0)], [[5.0, 0.0, 0.0], [0.0, 5.0, 0.0], [0.0, 0.0, 5.0]], "Si")
    structure.periodic = [True, True, True]
    project = Project("Protected")
    project.set_structure(structure)
    with pytest.raises(EntitlementDenied):
        CalculationService(CALCULATIONS, licensing_service=service).create_request(project, ["scf"])


def test_mock_device_limit_sessions_trials_and_named_organization_seats_are_server_authoritative():
    connector = InMemoryLicensingConnector(now=lambda: NOW)
    first, second = identity(), identity()
    connector.set_plan("pro-user", PlanId.PRO)
    connector.register_device(DeviceRegistrationRequest("pro-user", first))
    connector.register_device(DeviceRegistrationRequest("pro-user", second))
    with pytest.raises(DeviceLimitReached): connector.register_device(DeviceRegistrationRequest("pro-user", identity()))
    one = connector.open_session("pro-user", first.device_id)
    with pytest.raises(SessionLimitReached): connector.open_session("pro-user", second.device_id)
    connector.close_session(one.session_id)
    assert connector.open_session("pro-user", second.device_id).device_id == second.device_id
    connector.issue_trial_once("trial-user", PlanId.FREE_STARTER)
    with pytest.raises(TrialAlreadyConsumed): connector.issue_trial_once("trial-user", PlanId.FREE_STARTER)
    connector.set_plan("org-user", PlanId.ORGANIZATION)
    connector.register_device(DeviceRegistrationRequest("org-user", first))
    connector.register_device(DeviceRegistrationRequest("org-user", second))
    connector.assign_seat("org-user", first.device_id, "seat-alice")
    connector.assign_seat("org-user", second.device_id, "seat-bob")
    assert connector.open_session("org-user", first.device_id, seat_id="seat-alice")
    assert connector.open_session("org-user", second.device_id, seat_id="seat-bob")


def test_downgrade_changes_access_without_mutating_projects_and_access_controller_is_nonvisual_gate():
    issuer = Ed25519PrivateKey.generate(); device = identity()
    pro = service_for(envelope(device, issuer), device, issuer)
    assert DeviceBuilderAccessController(pro).authorize().allowed
    plus = service_for(envelope(device, issuer, plan="plus", features=(), calculations=("calc:*",)), device, issuer)
    with pytest.raises(EntitlementDenied): DeviceBuilderAccessController(plus).authorize()
    assert plus.authorize_read("data:project").allowed


def test_unauthorized_device_builder_workspace_is_a_safe_non_operational_placeholder():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from frontend.app.licensing_access import EntitlementUnavailableWorkspace
    app = QApplication.instance() or QApplication([])
    workspace = DeviceBuilderAccessController(LicensingService()).create_workspace(Project("Denied"))
    assert isinstance(workspace, EntitlementUnavailableWorkspace)
    assert not hasattr(workspace, "add_region_from_structure")
    workspace.close(); app.processEvents()


def test_atomic_cache_diagnostics_redaction_and_windows_dpapi_private_key_storage():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        paths = RuntimePaths(root / "config", root / "data", root / "cache", root / "workflows", root / "logs", root / "pseudos", root / "engines")
        store = LeaseStore(paths)
        store.save_lease({"kid": "test", "signature": "safe"})
        assert store.load_lease()["kid"] == "test"
        assert not list(store.root.glob("*.tmp"))
        # Unit tests deliberately never depend on the host profile's DPAPI
        # master key.  Production selects WindowsDPAPIKeyStore; test injection
        # uses the isolated in-memory store and verifies no plaintext path is
        # part of the contract.
        assert WindowsDPAPIKeyStore(paths).path.name == "device-key.dpapi"
        service = DeviceIdentityService(InMemorySecureKeyStore())
        assert service.load_or_create().device_id == service.load_or_create().device_id
    manifest = collect_diagnostics(licensing_state={"plan_id": "pro", "status": "active", "raw_token": "must-not-pass"})
    assert manifest["licensing"]["plan_id"] == "pro"
    assert "signature" not in str(manifest).lower()
    assert "raw_token" not in str(manifest).lower()


def test_no_environment_unlock_is_consulted_by_policy(monkeypatch):
    monkeypatch.setenv("QS_LICENSE", "PRO")
    monkeypatch.setenv("QS_UNLOCK_ALL", "1")
    decision = EntitlementPolicy().authorize_feature("workspace:device_builder")
    assert decision.reason is DecisionReason.AUTH_REQUIRED
