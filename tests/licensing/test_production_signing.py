"""Synthetic fixture seeds only: no production key generation/provisioning or network."""
from copy import deepcopy
from dataclasses import replace
import json
import traceback
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from backend.licensing.canonical import b64url_encode, canonical_json
from backend.licensing.configuration import Environment, desktop_configuration
from backend.licensing.verifier import LeaseVerifier, LeaseValidationError, device_identity_from_private_key, public_key_bytes
from backend.licensing.service import LicensingService
from operator_tools.licence_manager.crypto import DataProtector
from operator_tools.licence_manager.database import Database
from operator_tools.licence_manager.issuance import issue_website_activation, IssuanceRejected
from operator_tools.licence_manager.signing import TestEphemeralAuthority as _TestAuthority, SigningUnavailable
from operator_tools.licence_manager import signing_runtime as module
from operator_tools.licence_manager.signing_runtime import RuntimeEd25519Signer, configured_licence_signer, sign_verified_licence
from operator_tools.licence_manager.website_sync import WebsiteActivation
from tests.helpers.licensing import beta_entitlement

# Publicly known unit material, never a deployable secret.
SEED = bytes(range(32))
PUBLIC = public_key_bytes(Ed25519PrivateKey.from_private_bytes(SEED))
NOW = 1800000000
APP = "12345678-1234-4123-8123-123456789abc"


def configuration(mode="production", seed=SEED, issuer="lic-unit-fixture"):
    public = public_key_bytes(Ed25519PrivateKey.from_private_bytes(seed))
    return {"BETA_ENVIRONMENT": mode, "QS_LICENCE_SIGNING_ISSUER_ID": issuer,
        "QS_LICENCE_SIGNING_PUBLIC_KEY": b64url_encode(public),
        "QS_LICENCE_SIGNING_KEY": json.dumps({"schema_version": 1, "environment": mode,
            "domain": "licence", "algorithm": "Ed25519", "private_key": b64url_encode(seed)})}


def select(monkeypatch, mode="production", **changes):
    values = {**configuration(mode), **changes}
    for name in ("QS_TEST_LICENSING", "QS_TEST_LICENCE_TRUST_FILE", "QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP",
                 "BETA_TURNSTILE_TEST_MODE", "AUTH_EMAIL_TEST_MODE", "CLOUDFLARE_LOCAL"):
        monkeypatch.delenv(name, raising=False)
    for name, value in values.items(): monkeypatch.setenv(name, value)
    return values


@pytest.fixture
def payload():
    device = device_identity_from_private_key(Ed25519PrivateKey.from_private_bytes(b'D'*32))
    return {"schema_version": 1, "licence_id": "lic_aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "account_id": "sub_"+APP, "subject_type": "beta_applicant", "subject_id": "sub_"+APP,
        "approved_application_ref": APP, "product": "Quantum Studio", "channel": "beta", "plan_id": "pro",
        "device_id": device.device_id, "device_public_key_hash": device.public_key_hash,
        "issued_at": NOW, "not_before": NOW, "expires_at": NOW+90*86400, "offline_until": NOW+90*86400,
        "entitlement_version": 1, "feature_entitlements": ["builder", "device_builder"],
        "calculation_entitlements": [], "registered_device_limit": 1, "concurrent_session_limit": 1,
        "offline_device_limit": 1, "nonce": "unit-nonce", "policy_profile": "PROFESSOR_BETA",
        "issuer_label": "Quantum Studio Licence Manager"}


@pytest.mark.parametrize("mode", ["staging", "production"])
def test_valid_runtime_signer_matches_existing_verifier_and_public_desktop_trust(mode, payload, monkeypatch):
    select(monkeypatch, mode)
    signer = configured_licence_signer()
    envelope = sign_verified_licence(signer, payload)
    device = device_identity_from_private_key(Ed25519PrivateKey.from_private_bytes(b'D'*32))
    trust = {"schema_version": 1, "environment": mode, "domain": "licence", "algorithm": "Ed25519",
        "keys": {signer.kid: b64url_encode(signer.public_key)}}
    config = desktop_configuration({"BETA_ENVIRONMENT": mode, "QS_WEBSITE_URL": "https://licence.unit-fixture.org",
        "QS_LICENCE_TRUST": json.dumps(trust)})
    verified = LeaseVerifier(config.trusted_public_keys).verify(envelope, device)
    assert verified.lease.kid == signer.kid and signer.mode == mode.upper()
    assert envelope.keys() == payload.keys() | {"kid", "signature"}
    assert verified.lease.expires_at == payload["expires_at"]
    service = LicensingService(trusted_public_keys=config.trusted_public_keys, device_identity=device,
        deployment_config=config, now=lambda: NOW)
    service.accept_lease(envelope, persist=False)
    assert not service.policy.validity_decision().allowed  # A signature never creates offline authorization.


def test_canonical_signatures_stable_across_order_and_runtime_restart(payload, monkeypatch):
    values = select(monkeypatch)
    signer = RuntimeEd25519Signer(values)
    first = signer.sign_licence(payload)
    assert first == signer.sign_licence(dict(reversed(list(payload.items()))))
    assert canonical_json(first) == canonical_json(RuntimeEd25519Signer(values).sign_licence(payload))
    assert {name: value for name, value in first.items() if name not in {"kid", "signature"}} == payload
    payload["feature_entitlements"].append("later-edit")
    assert "later-edit" not in first["feature_entitlements"]
    device = device_identity_from_private_key(Ed25519PrivateKey.from_private_bytes(b'D'*32))
    LeaseVerifier({signer.kid: signer.public_key}).verify(first, device)
    first["expires_at"] += 1
    with pytest.raises(LeaseValidationError): LeaseVerifier({signer.kid: signer.public_key}).verify(first, device)


@pytest.mark.parametrize("issuer", [None, "", "test-lic-unit", "update-unit", "lic-UPPER", " lic-fixture"])
def test_missing_or_test_issuer_rejected(issuer):
    values = configuration()
    if issuer is None: values.pop("QS_LICENCE_SIGNING_ISSUER_ID")
    else: values["QS_LICENCE_SIGNING_ISSUER_ID"] = issuer
    with pytest.raises(SigningUnavailable, match="invalid-issuer"): RuntimeEd25519Signer(values)


@pytest.mark.parametrize("raw", [None, "", "not-json", "[]", "null", '{}', '{"private_key":"unit-canary"}'])
def test_malformed_or_missing_key_record_is_safe(raw):
    values = configuration()
    if raw is None: values.pop("QS_LICENCE_SIGNING_KEY")
    else: values["QS_LICENCE_SIGNING_KEY"] = raw
    with pytest.raises(SigningUnavailable, match="invalid-private-key") as failure:
        RuntimeEd25519Signer(values)
    assert "unit-canary" not in ''.join(traceback.format_exception(failure.value))


@pytest.mark.parametrize("change", [{"private_key": "invalid-canary"}, {"private_key": b64url_encode(b'x'*31)},
    {"private_key": b64url_encode(b'x'*64)}, {"private_key": b64url_encode(SEED)+"="},
    {"private_key": "-----BEGIN PRIVATE KEY-----"}, {"environment": "local"}, {"environment": "staging"},
    {"domain": "test-licence"}, {"algorithm": "RSA"}, {"schema_version": True}, {"extra": "field"}])
def test_wrong_key_format_size_or_test_provenance_rejected(change):
    values = configuration()
    record = json.loads(values["QS_LICENCE_SIGNING_KEY"]); record.update(change)
    values["QS_LICENCE_SIGNING_KEY"] = json.dumps(record)
    with pytest.raises(SigningUnavailable, match="invalid-private-key"): RuntimeEd25519Signer(values)


def test_duplicate_secret_members_fail_closed():
    values = configuration()
    values["QS_LICENCE_SIGNING_KEY"] = values["QS_LICENCE_SIGNING_KEY"].replace('"environment": "production"',
        '"environment": "local", "environment": "production"')
    with pytest.raises(SigningUnavailable): RuntimeEd25519Signer(values)


@pytest.mark.parametrize("public", [None, "", "invalid", b64url_encode(b'x'*31), b64url_encode(b'x'*32)])
def test_required_public_pin_validated_and_matched(public):
    values = configuration()
    if public is None: values.pop("QS_LICENCE_SIGNING_PUBLIC_KEY")
    else: values["QS_LICENCE_SIGNING_PUBLIC_KEY"] = public
    with pytest.raises(SigningUnavailable): RuntimeEd25519Signer(values)


@pytest.mark.parametrize("mode", [None, "", "staging", "production", "development"])
def test_test_authority_rejected_before_key_generation_outside_explicit_local(mode, monkeypatch):
    if mode is None: monkeypatch.delenv("BETA_ENVIRONMENT", raising=False)
    else: monkeypatch.setenv("BETA_ENVIRONMENT", mode)
    def forbidden(): pytest.fail("A TEST key must not be generated")
    monkeypatch.setattr(Ed25519PrivateKey, "generate", forbidden)
    with pytest.raises(SigningUnavailable): _TestAuthority()


def test_existing_test_signer_remains_explicit_local_only(payload, monkeypatch):
    select(monkeypatch, "local", QS_TEST_LICENSING="1")
    signer = configured_licence_signer()
    assert isinstance(signer, _TestAuthority) and signer.mode == "TEST"
    assert sign_verified_licence(signer, payload)["kid"].startswith("test-lic-")
    monkeypatch.setenv("BETA_ENVIRONMENT", "production")
    for method in (signer.sign_licence, signer.sign_test_fixture_only):
        with pytest.raises(SigningUnavailable): method(payload)
    with pytest.raises(SigningUnavailable): sign_verified_licence(signer, payload)


@pytest.mark.parametrize("mode", ["staging", "production"])
def test_deployed_factory_never_falls_back_to_test_on_missing_key(mode, monkeypatch):
    select(monkeypatch, mode, QS_LICENCE_SIGNING_KEY="")
    with pytest.raises(SigningUnavailable): configured_licence_signer()
    monkeypatch.setenv("QS_TEST_LICENSING", "1")
    with pytest.raises(SigningUnavailable): configured_licence_signer()


def test_no_key_io_or_secret_serialization_or_logging(payload, monkeypatch, caplog):
    values = select(monkeypatch)
    def forbidden(*args, **kwargs): pytest.fail("Signing must not persist or read a key file")
    monkeypatch.setattr('builtins.open', forbidden)
    signer = RuntimeEd25519Signer(values)
    envelope = signer.sign_licence(payload)
    serialized = canonical_json(envelope).decode() + repr(signer) + repr(signer.status()) + caplog.text
    assert b64url_encode(SEED) not in serialized and SEED.hex() not in serialized
    assert "private_key" not in serialized and "QS_LICENCE_SIGNING_KEY" not in serialized
    assert not caplog.records


@pytest.mark.parametrize("change", [{"signature": "arbitrary"}, {"kid": "caller-controlled"},
    {"schema_version": 2}, {"private_key": "payload-canary"}, {"expires_at": float('nan')}])
def test_malformed_or_pre_signed_payload_rejected_safely(payload, change, monkeypatch):
    select(monkeypatch)
    with pytest.raises(SigningUnavailable): RuntimeEd25519Signer().sign_licence({**payload, **change})


@pytest.fixture
def context(tmp_path, monkeypatch):
    select(monkeypatch)
    db = Database(tmp_path / "operator", DataProtector.for_testing(b'K'*32))
    device = device_identity_from_private_key(Ed25519PrivateKey.from_private_bytes(b'D'*32))
    activation = WebsiteActivation("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", APP, device.device_id,
        "windows", "x86_64", "0.2.0", "AUTHORIZED", None, "2027-01-15T08:00:00Z",
        "2027-01-15T08:00:00Z", "2027-01-15T08:00:00Z", None, device.public_key_hash,
        account_entitlement=beta_entitlement(starts_at=NOW-100))
    yield SimpleNamespace(db=db, device=device, activation=activation, signer=configured_licence_signer())
    db.close()


def test_authorized_production_issuance_persists_original_and_inherits_entitlement(context, monkeypatch):
    b = context
    envelope = issue_website_activation(b.db, b.signer, b.activation, now=NOW)
    assert LeaseVerifier({b.signer.kid: b.signer.public_key}).verify(envelope, b.device).lease.kid == b.signer.kid
    assert envelope["expires_at"] == NOW-100+90*86400
    assert envelope["registered_device_limit"] == 1 and envelope["offline_until"] == envelope["expires_at"]
    # Reloading the persistent identity recovers bytes without creating another signature.
    restarted = configured_licence_signer()
    def forbidden(*args, **kwargs): pytest.fail("Never re-sign an immutable activation")
    monkeypatch.setattr(restarted, "sign_licence", forbidden)
    assert issue_website_activation(b.db, restarted, b.activation, now=NOW+1) == envelope
    assert b.db.connection.execute('SELECT COUNT(*) FROM website_activation_licences').fetchone()[0] == 1
    assert b.db.connection.execute("SELECT COUNT(*) FROM audit_events WHERE event_type='licence_issuance'").fetchone()[0] == 1
    row = b.db.connection.execute('SELECT domain,public_key FROM signing_keys').fetchone()
    assert row['domain'] == 'licence' and bytes(row['public_key']) == PUBLIC
    assert b64url_encode(SEED).encode() not in b.db.path.read_bytes()


@pytest.mark.parametrize("attack", ["signature", "payload", "exception"])
def test_verification_failure_rolls_back_before_envelope_can_be_published(context, attack, monkeypatch):
    b = context
    original = b.signer.sign_licence
    def invalid(payload):
        if attack == "exception": raise RuntimeError("PRIVATE-KEY-CANARY")
        envelope = original(payload)
        if attack == "signature": envelope['signature'] = 'bad'
        else: envelope['registered_device_limit'] = 99
        return envelope
    monkeypatch.setattr(b.signer, "sign_licence", invalid)
    with pytest.raises(SigningUnavailable) as error:
        issue_website_activation(b.db, b.signer, b.activation, now=NOW)
    assert "PRIVATE-KEY-CANARY" not in ''.join(traceback.format_exception(error.value))
    for table in ('website_activation_licences', 'signing_keys', 'website_account_entitlements'):
        assert b.db.connection.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] == 0


@pytest.mark.parametrize("change", [{"status": "REVOKED"}, {"flag_reason": "conflict"},
    {"revoked_at": "2027-01-15T08:00:00Z"}, {"licence_revoked_at": "2027-01-15T08:00:00Z"}])
def test_existing_revocation_and_conflict_states_stay_closed(context, change):
    b = context
    with pytest.raises(IssuanceRejected):
        issue_website_activation(b.db, b.signer, replace(b.activation, **change), now=NOW)
    assert b.db.connection.execute('SELECT COUNT(*) FROM website_activation_licences').fetchone()[0] == 0


def test_rotation_keeps_old_envelope_and_rejects_reuse_of_issuer_id(context, monkeypatch):
    b = context
    first = issue_website_activation(b.db, b.signer, b.activation, now=NOW)
    values = configuration(seed=b'R'*32)
    with pytest.raises(SigningUnavailable):
        issue_website_activation(b.db, RuntimeEd25519Signer(values), b.activation, now=NOW+1)
    values = configuration(seed=b'R'*32, issuer="lic-rotated-unit")
    rotated = RuntimeEd25519Signer(values)
    assert issue_website_activation(b.db, rotated, b.activation, now=NOW+1) == first
    replacement = replace(b.activation, activation_request_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    second = issue_website_activation(b.db, rotated, replacement, now=NOW+100)
    assert second['kid'] == rotated.kid and second['expires_at'] == first['expires_at']
    LeaseVerifier({b.signer.kid: b.signer.public_key, rotated.kid: rotated.public_key}).verify(second, b.device)


@pytest.mark.parametrize("mode", [None, "", "local", "test", "development"])
def test_runtime_authority_requires_explicit_deployed_profile(mode):
    values = configuration()
    if mode is None: values.pop("BETA_ENVIRONMENT")
    else: values["BETA_ENVIRONMENT"] = mode
    with pytest.raises(SigningUnavailable, match="invalid-environment"):
        RuntimeEd25519Signer(values)


def test_runtime_signer_cannot_cross_environment_after_composition(payload, monkeypatch):
    select(monkeypatch, "staging")
    signer = RuntimeEd25519Signer()
    monkeypatch.setenv("BETA_ENVIRONMENT", "production")
    with pytest.raises(SigningUnavailable, match="environment-mismatch"):
        signer.sign_licence(payload)


@pytest.mark.parametrize("name", ["QS_TEST_LICENSING", "QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP",
    "AUTH_EMAIL_TEST_MODE", "BETA_TURNSTILE_TEST_MODE", "CLOUDFLARE_LOCAL"])
def test_production_signer_rejects_test_runtime_settings(name):
    with pytest.raises(SigningUnavailable):
        RuntimeEd25519Signer({**configuration(), name: "true"})


@pytest.mark.parametrize("attack", ["malformed", "signature", "binding", "missing-key", "missing-issuer"])
def test_recovery_rejects_corrupt_or_misbound_original_envelope(context, attack):
    b = context
    first = issue_website_activation(b.db, b.signer, b.activation, now=NOW)
    if attack == "missing-key":
        b.db.connection.execute('DELETE FROM signing_keys')
    else:
        changed = deepcopy(first)
        if attack == "signature": changed['signature'] = 'bad'
        if attack == "missing-issuer": changed.pop('kid')
        if attack == "binding":
            payload = {name: value for name, value in changed.items() if name not in {'kid', 'signature'}}
            payload['device_id'] = 'dev_'+'a'*32
            payload['device_public_key_hash'] = 'a'*64
            changed = b.signer.sign_licence(payload)
        value = '{invalid-json' if attack == "malformed" else json.dumps(changed)
        b.db.connection.execute('UPDATE website_activation_licences SET envelope_json=?', (value,))
    b.db.connection.commit()
    with pytest.raises(SigningUnavailable):
        issue_website_activation(b.db, b.signer, b.activation, now=NOW+1)
    assert b.db.connection.execute("SELECT COUNT(*) FROM audit_events WHERE event_type='licence_issuance'").fetchone()[0] == 1
