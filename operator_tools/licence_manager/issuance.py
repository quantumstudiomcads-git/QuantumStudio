"""Policy-checked offline licence creation and local administrative revocation."""
from __future__ import annotations

from datetime import datetime, timezone
from copy import deepcopy
import json
import hashlib
import re
import uuid

from backend.licensing.canonical import canonical_json, b64url_decode, b64url_encode
from backend.licensing.verifier import public_key_hash
from .audit import append_event
from .models import ApplicantStatus, Profile, TRANSITIONS
from .policy import derive_profile
from .signing import AuthorityState, SigningUnavailable


PRODUCT = "Quantum Studio"
DURATION_SECONDS = 90 * 24 * 60 * 60


class IssuanceRejected(RuntimeError): pass


def authorize_activation_profile(database, request_id: str, profile: Profile | str, *, operator_id="operator", confirmed=False):
    """Persist a local operator decision; imported requested_profile is informational only."""
    try: selected = Profile(profile)
    except ValueError as error: raise IssuanceRejected("Unsupported local policy profile.") from error
    if not confirmed:
        with database.transaction() as db:
            append_event(db, "rejected_policy_action", operator_id, [request_id], {"code": "profile_confirmation_required"})
        raise IssuanceRejected("Explicit profile authorization confirmation is required.")
    row = database.connection.execute("SELECT application_id FROM activation_requests WHERE request_id=?", (request_id,)).fetchone()
    if not row: raise IssuanceRejected("Activation request does not exist.")
    applicant = database.connection.execute("SELECT status FROM applicants WHERE application_id=?", (row[0],)).fetchone()
    if not applicant or applicant[0] != ApplicantStatus.APPROVED.value:
        with database.transaction() as db: append_event(db, "rejected_policy_action", operator_id, [request_id, row[0]], {"code": "applicant_not_approved"})
        raise IssuanceRejected("Applicant is not approved.")
    with database.transaction() as db:
        previous = db.execute("SELECT authorized_profile FROM activation_requests WHERE request_id=?", (request_id,)).fetchone()[0]
        event = append_event(db, "policy_profile_authorized", operator_id, [request_id, row[0]], {"profile": selected.value, "previous_profile": previous})
        db.execute("UPDATE activation_requests SET authorized_profile=? WHERE request_id=?", (selected.value, request_id))
    return event


def issue_for_request_for_testing(database, test_authority, request_id: str, *, operator_id="operator", now=None, confirmed=False):
    """TEST ONLY workflow using an explicitly injected ephemeral fixture signer."""
    from .signing import TestEphemeralAuthority
    if not isinstance(test_authority, TestEphemeralAuthority):
        raise IssuanceRejected("Test issuance requires the explicit TEST ONLY ephemeral authority.")
    row = database.connection.execute("SELECT application_id,authorized_profile FROM activation_requests WHERE request_id=?", (request_id,)).fetchone()
    if not row:
        _rejected(database, operator_id, [request_id], "request_missing")
        raise IssuanceRejected("Activation request does not exist.")
    try: profile = Profile(row[1])
    except (ValueError, TypeError) as error: raise IssuanceRejected("A local operator must authorize a policy profile before issuance.") from error
    return _issue_from_authoritative_records(database, row[0], request_id, profile, operator_id=operator_id,
        now=now, confirmed=confirmed, signer=lambda _db, payload: test_authority.sign_test_fixture_only(payload),
        mode="TEST", metadata_authority=test_authority)


def _rejected(database, operator_id, ids, code):
    with database.transaction() as db:
        append_event(db, "rejected_policy_action", operator_id, ids, {"code": code})


def _issue_from_authoritative_records(database, application_id, request_id, selected_profile, *, operator_id="operator", now=None, confirmed=False, signer, mode, metadata_authority):
    """Private shared workflow. Only ProductionAuthority and TEST ONLY entry point call this."""
    if not confirmed:
        _rejected(database, operator_id, [request_id], "issuance_confirmation_required")
        raise IssuanceRejected("Explicit operator confirmation is required.")
    try: profile = Profile(selected_profile)
    except (ValueError, TypeError) as error: raise IssuanceRejected("Unsupported local policy profile.") from error
    now = int(now.timestamp()) if isinstance(now, datetime) else int(now if now is not None else datetime.now(timezone.utc).timestamp())
    conn = database.connection
    request = conn.execute("SELECT application_id,request_json,authorized_profile,request_hash FROM activation_requests WHERE request_id=?", (request_id,)).fetchone()
    if not request:
        _rejected(database, operator_id, [application_id, request_id], "request_missing")
        raise IssuanceRejected("Activation request does not exist.")
    app_id, request_json, authorized_profile, stored_hash = request[0], request[1], request[2], request[3]
    if app_id != application_id:
        _rejected(database, operator_id, [application_id, request_id], "request_application_mismatch")
        raise IssuanceRejected("Activation request does not belong to this application.")
    if authorized_profile != profile.value:
        _rejected(database, operator_id, [application_id, request_id], "profile_not_operator_authorized")
        raise IssuanceRejected("Selected profile must match the audited local profile authorization.")
    try:
        req = json.loads(request_json)
    except (TypeError, ValueError) as error:
        _rejected(database, operator_id, [app_id, request_id], "activation_record_invalid")
        raise IssuanceRejected("Stored activation request is malformed.") from error
    if hashlib.sha256(canonical_json(req)).hexdigest() != stored_hash:
        with database.transaction() as db: append_event(db, "rejected_policy_action", operator_id, [app_id, request_id], {"code": "activation_record_integrity_failure"})
        raise IssuanceRejected("Stored activation request failed its integrity check.")
    _validate_request_for_issuance(req, app_id, request_id, now)
    status = conn.execute("SELECT status FROM applicants WHERE application_id=?", (app_id,)).fetchone()
    if not status or status[0] != ApplicantStatus.APPROVED.value:
        with database.transaction() as db: append_event(db, "rejected_policy_action", operator_id, [app_id, request_id], {"code": "applicant_not_approved"})
        raise IssuanceRejected("Applicant is not approved.")
    active = conn.execute("SELECT 1 FROM licences WHERE application_id=? AND revoked_at IS NULL AND expires_at>? LIMIT 1", (app_id, now)).fetchone()
    if active:
        with database.transaction() as db: append_event(db, "rejected_policy_action", operator_id, [app_id, request_id], {"code": "active_licence_exists"})
        raise IssuanceRejected("Applicant already has an active device-bound licence; controlled renewal requires expiry and review.")
    if req["created_at"] and now - int(datetime.fromisoformat(req["created_at"].replace("Z", "+00:00")).timestamp()) > 30 * 86400:
        with database.transaction() as db: append_event(db, "rejected_policy_action", operator_id, [app_id, request_id], {"code": "activation_request_expired"})
        raise IssuanceRejected("Activation request has expired.")
    if authorized_profile is None:
        with database.transaction() as db: append_event(db, "rejected_policy_action", operator_id, [app_id, request_id], {"code": "profile_not_operator_authorized"})
        raise IssuanceRejected("A local operator must authorize an entitlement profile before issuance.")
    grants = derive_profile(profile)
    if profile not in (Profile.PROFESSOR_BETA, Profile.INTERNAL_VALIDATION):
        raise IssuanceRejected("Unsupported local policy profile.")
    next_state = ApplicantStatus.LICENCE_ISSUED
    current = ApplicantStatus(status[0])
    if next_state not in TRANSITIONS[current]:
        _rejected(database, operator_id, [app_id, request_id], "invalid_transition")
        raise IssuanceRejected("Application state does not permit licence issuance.")
    licence_id = "lic_" + str(uuid.uuid4())
    subject_id = "sub_" + app_id
    payload = {
        "schema_version": 1, "licence_id": licence_id, "account_id": subject_id,
        "subject_type": "beta_applicant", "plan_id": "pro", "product": PRODUCT,
        "channel": "beta", "subject_id": subject_id, "approved_application_ref": app_id,
        "device_id": req["device_id"], "device_public_key_hash": req["device_public_key_hash"],
        "issued_at": now, "not_before": now, "expires_at": now + DURATION_SECONDS,
        "offline_until": now + DURATION_SECONDS, "entitlement_version": 1,
        "feature_entitlements": list(grants.features), "calculation_entitlements": list(grants.calculations),
        "registered_device_limit": 1, "concurrent_session_limit": 1, "offline_device_limit": 1,
        "nonce": str(uuid.uuid4()), "policy_profile": profile.value, "issuer_label": "Quantum Studio Licence Manager",
    }
    try:
        with database.transaction() as db:
            # Recheck authoritative state under BEGIN IMMEDIATE to close the
            # validation/signing race before any protected key is loaded.
            locked_request = db.execute("SELECT application_id,request_json,authorized_profile,request_hash FROM activation_requests WHERE request_id=?", (request_id,)).fetchone()
            locked_app = db.execute("SELECT status FROM applicants WHERE application_id=?", (application_id,)).fetchone()
            if not locked_request or locked_request[0] != application_id or not locked_app or locked_app[0] != ApplicantStatus.APPROVED.value:
                raise IssuanceRejected("Application or activation request changed before issuance.")
            try:
                locked_value = json.loads(locked_request[1])
                locked_hash = hashlib.sha256(canonical_json(locked_value)).hexdigest()
            except (TypeError, ValueError) as error:
                raise IssuanceRejected("Stored activation request is malformed.") from error
            if locked_request[2] != profile.value or locked_hash != locked_request[3]:
                raise IssuanceRejected("Activation request or authorized profile changed before issuance.")
            _validate_request_for_issuance(locked_value, application_id, request_id, now)
            if db.execute("SELECT 1 FROM licences WHERE request_id=?", (request_id,)).fetchone():
                raise IssuanceRejected("Activation request has already been used for a licence.")
            if db.execute("SELECT 1 FROM licences WHERE application_id=? AND revoked_at IS NULL AND expires_at>? LIMIT 1", (application_id, now)).fetchone():
                raise IssuanceRejected("Applicant already has an active licence.")
            _record_signing_metadata_in_transaction(db, metadata_authority, operator_id)
            envelope = signer(db, payload)
            append_event(db, "issuance_attempt", operator_id, [licence_id, app_id, request_id], {"result": "signed"})
            event_id = append_event(db, "successful_test_issuance" if mode == "TEST" else "licence_issuance",
                                    operator_id, [licence_id, app_id, request_id], {"profile": profile.value})
            db.execute("INSERT INTO licences(licence_id,application_id,request_id,device_id,profile,issued_at,expires_at,envelope_json,audit_event_id) VALUES(?,?,?,?,?,?,?,?,?)",
                   (licence_id, app_id, request_id, req["device_id"], profile.value, now, now + DURATION_SECONDS, canonical_json(envelope).decode(), event_id))
            changed = db.execute("UPDATE applicants SET status=? WHERE application_id=? AND status=?", (ApplicantStatus.LICENCE_ISSUED.value, app_id, ApplicantStatus.APPROVED.value)).rowcount
            if changed != 1:
                raise IssuanceRejected("Application state changed before issuance could be recorded.")
            from .audit import utc_now
            db.execute("INSERT INTO application_status_history VALUES(?,?,?,?,?,?,?,?)",
                   (str(uuid.uuid4()), app_id, utc_now(), operator_id, status[0], ApplicantStatus.LICENCE_ISSUED.value, "licence_issued", event_id))
    except Exception as error:
        try:
            with database.transaction() as db:
                append_event(db, "issuance_attempt", operator_id, [app_id, request_id], {"result": "failed", "code": "issuance_failed"})
        except Exception:
            # The failed issuance remains failed; failure telemetry must not
            # conceal the primary error or falsely claim issuance success.
            pass
        if isinstance(error, SigningUnavailable): raise IssuanceRejected("Signing authority is unavailable.") from error
        raise
    return envelope, event_id


def _validate_request_for_issuance(request, application_id, request_id, now):
    """Revalidate the strict import contract at the private-key boundary."""
    fields = {"schema_version", "request_id", "application_id", "product", "application_version", "platform", "device_id", "device_public_key", "device_public_key_hash", "requested_profile", "created_at"}
    try:
        if not isinstance(request, dict) or set(request) != fields or type(request["schema_version"]) is not int or request["schema_version"] != 1:
            raise ValueError
        if request["request_id"] != request_id or request["application_id"] != application_id or request["product"] != PRODUCT:
            raise ValueError
        if request["platform"] not in {"windows-x86_64", "linux-x86_64"} or request["requested_profile"] not in {item.value for item in Profile}:
            raise ValueError
        if not isinstance(request["application_version"], str) or not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?", request["application_version"]):
            raise ValueError
        key = b64url_decode(request["device_public_key"])
        digest = public_key_hash(key)
        if len(key) != 32 or b64url_encode(key) != request["device_public_key"] or request["device_public_key_hash"] != digest or request["device_id"] != "dev_" + digest[:32]:
            raise ValueError
        created = datetime.fromisoformat(request["created_at"].replace("Z", "+00:00"))
        if created.tzinfo is None or created.timestamp() > now or now - created.timestamp() > 30 * 86400:
            raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise IssuanceRejected("Stored activation request failed issuance validation.") from error


def _record_signing_metadata_in_transaction(db, authority, operator_id):
    """Persist public metadata and its audit event in the issuance transaction."""
    from .audit import utc_now
    status = authority.status()
    if not status.kid or status.public_key is None or status.state in {
        AuthorityState.UNINITIALIZED, AuthorityState.METADATA_INVALID, AuthorityState.PROTECTED_KEY_MISSING,
    }:
        raise IssuanceRejected("Signing authority is unavailable.")
    public_key = bytes(status.public_key)
    domain = "test-licence" if status.mode == "TEST" else "licence"
    existing = db.execute("SELECT public_key,domain FROM signing_keys WHERE kid=?", (status.kid,)).fetchone()
    if existing and (bytes(existing[0]) != public_key or existing[1] != domain):
        raise IssuanceRejected("Stored signing metadata does not match the active authority.")
    if not existing:
        db.execute("INSERT INTO signing_keys VALUES(?,?,?,?,?)", (status.kid, public_key, domain, utc_now(), "active"))
    append_event(db, "signing_authority_status", operator_id, [status.kid], {"state": status.state.value, "mode": status.mode, "domain": domain})


def revoke_licence(database, licence_id: str, *, operator_id="operator", note_code="administrative_revocation", confirmed=False):
    if note_code != "administrative_revocation": raise ValueError("Revocation note must use the controlled administrative code.")
    if not confirmed:
        with database.transaction() as db: append_event(db, "rejected_policy_action", operator_id, [licence_id], {"code": "revocation_confirmation_required"})
        raise IssuanceRejected("Explicit operator confirmation is required.")
    with database.transaction() as db:
        row = db.execute("SELECT application_id,revoked_at FROM licences WHERE licence_id=?", (licence_id,)).fetchone()
        if not row: raise KeyError(licence_id)
        if row[1]: return False
        from .audit import utc_now
        timestamp = utc_now()
        event = append_event(db, "revocation_record", operator_id, [licence_id, row[0]], {"note_code": note_code, "offline_effect": "not_immediate"}, timestamp)
        db.execute("UPDATE licences SET revoked_at=?,revoke_note_code=?,audit_event_id=? WHERE licence_id=?", (timestamp, note_code, event, licence_id))
        state_row = db.execute("SELECT status FROM applicants WHERE application_id=?", (row[0],)).fetchone()
        previous = ApplicantStatus(state_row[0]) if state_row else None
        if previous and ApplicantStatus.REVOKED in TRANSITIONS[previous]:
            db.execute("UPDATE applicants SET status=? WHERE application_id=?", (ApplicantStatus.REVOKED.value, row[0]))
            db.execute("INSERT INTO application_status_history VALUES(?,?,?,?,?,?,?,?)",
                       (str(uuid.uuid4()), row[0], timestamp, operator_id, previous.value,
                        ApplicantStatus.REVOKED.value, "administrative_revocation", event))
    return True


def record_expiries(database, *, now=None, operator_id="operator"):
    """Record expiry locally; offline enforcement follows the signed expiry timestamp."""
    now = int(now.timestamp()) if isinstance(now, datetime) else int(now if now is not None else datetime.now(timezone.utc).timestamp())
    from .audit import utc_now
    count = 0
    with database.transaction() as db:
        rows = db.execute("SELECT licence_id,application_id FROM licences WHERE revoked_at IS NULL AND expires_at<=? AND expiry_recorded_at IS NULL", (now,)).fetchall()
        for row in rows:
            event = append_event(db, "expiry_record", operator_id, [row[0], row[1]], {"offline_effect": "signed_expiry"})
            db.execute("UPDATE licences SET expiry_recorded_at=?,audit_event_id=? WHERE licence_id=?", (utc_now(), event, row[0]))
            changed = db.execute("UPDATE applicants SET status=? WHERE application_id=? AND status=?", (ApplicantStatus.EXPIRED.value, row[1], ApplicantStatus.LICENCE_ISSUED.value)).rowcount
            if changed:
                db.execute("INSERT INTO application_status_history VALUES(?,?,?,?,?,?,?,?)",
                           (str(uuid.uuid4()), row[1], utc_now(), operator_id, ApplicantStatus.LICENCE_ISSUED.value,
                            ApplicantStatus.EXPIRED.value, "licence_expired", event))
            count += 1
    return count


def issue_website_activation_for_testing(database, test_authority, activation, *, operator_id="operator", now=None):
    """Use an already AUTHORIZED website record, without a second approval.

    Business identity and the original signed envelope survive signer restart.
    No replacement signature is created when a new ephemeral authority is used.
    This entry point never accepts a production signing authority.
    """
    from .signing import TestEphemeralAuthority
    if not isinstance(test_authority, TestEphemeralAuthority):
        raise IssuanceRejected("Website issuance requires the TEST ONLY authority.")
    try:
        valid = (
            activation.status == "AUTHORIZED"
            and str(uuid.UUID(activation.activation_request_id)) == activation.activation_request_id.lower()
            and str(uuid.UUID(activation.application_id)) == activation.application_id.lower()
            and isinstance(activation.device_public_key_hash, str)
            and re.fullmatch(r"[0-9a-f]{64}", activation.device_public_key_hash) is not None
            and activation.installation_id == "dev_" + activation.device_public_key_hash[:32]
        )
    except (ValueError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise IssuanceRejected("An AUTHORIZED activation with a matching full device public-key hash is required.")
    with database.transaction() as db:
        existing = db.execute(
            "SELECT * FROM website_activation_licences WHERE activation_request_id=?",
            (activation.activation_request_id,),
        ).fetchone()
        if existing:
            if any(existing[field] != getattr(activation, field) for field in (
                "application_id", "installation_id", "device_public_key_hash")):
                raise IssuanceRejected("Website activation identity conflicts with its stored licence.")
            return json.loads(existing["envelope_json"])
        issued = int(now.timestamp()) if isinstance(now, datetime) else int(
            now if now is not None else datetime.now(timezone.utc).timestamp())
        from .entitlements import require_current_entitlement, remember_entitlement
        try:
            entitlement = deepcopy(activation.account_entitlement)
            starts, expires = require_current_entitlement(entitlement, activation.application_id, issued)
            remember_entitlement(db, entitlement)
        except ValueError as error:
            raise IssuanceRejected(str(error)) from None
        grants = derive_profile(Profile.PROFESSOR_BETA)
        licence_id = "lic_" + str(uuid.uuid4())
        subject = "sub_" + activation.application_id
        payload = {
            "schema_version": 1, "licence_id": licence_id, "account_id": subject,
            "subject_type": "beta_applicant", "subject_id": subject,
            "approved_application_ref": activation.application_id,
            "product": PRODUCT, "channel": "beta", "plan_id": "pro",
            "device_id": activation.installation_id,
            "device_public_key_hash": activation.device_public_key_hash,
            "issued_at": issued, "not_before": max(issued, starts),
            "expires_at": expires, "offline_until": expires,
            "entitlement_version": 1, "feature_entitlements": list(grants.features),
            "calculation_entitlements": list(grants.calculations),
            "registered_device_limit": entitlement["device_limit"], "concurrent_session_limit": 1, "offline_device_limit": 1,
            "nonce": str(uuid.uuid4()), "policy_profile": Profile.PROFESSOR_BETA.value,
            "issuer_label": "Quantum Studio Licence Manager",
        }
        _record_signing_metadata_in_transaction(db, test_authority, operator_id)
        envelope = test_authority.sign_test_fixture_only(payload)
        event = append_event(db, "successful_test_issuance", operator_id,
                             [activation.activation_request_id, licence_id], {"source": "website_activation"})
        db.execute("INSERT INTO website_activation_licences VALUES(?,?,?,?,?,?,?)", (
            activation.activation_request_id, activation.application_id,
            activation.installation_id, activation.device_public_key_hash, licence_id,
            canonical_json(envelope).decode(), event))
        return envelope
