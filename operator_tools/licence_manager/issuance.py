"""Policy-checked offline licence creation and local administrative revocation."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import hashlib
import uuid

from backend.licensing.canonical import canonical_json
from .audit import append_event
from .models import ApplicantStatus, Profile, TRANSITIONS
from .policy import derive_profile
from .signing import SigningUnavailable, record_public_metadata


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


def issue_for_request(database, authority, request_id: str, *, operator_id="operator", now=None, confirmed=False):
    if not confirmed:
        with database.transaction() as db:
            append_event(db, "rejected_policy_action", operator_id, [request_id], {"code": "issuance_confirmation_required"})
        raise IssuanceRejected("Explicit operator confirmation is required.")
    now = int(now.timestamp()) if isinstance(now, datetime) else int(now if now is not None else datetime.now(timezone.utc).timestamp())
    conn = database.connection
    request = conn.execute("SELECT application_id,request_json,authorized_profile,request_hash FROM activation_requests WHERE request_id=?", (request_id,)).fetchone()
    if not request:
        with database.transaction() as db: append_event(db, "issuance_attempt", operator_id, [request_id], {"result": "failed", "code": "request_missing"})
        raise IssuanceRejected("Activation request does not exist.")
    app_id, request_json, authorized_profile, stored_hash = request[0], request[1], request[2], request[3]
    req = json.loads(request_json)
    if hashlib.sha256(canonical_json(req)).hexdigest() != stored_hash:
        with database.transaction() as db: append_event(db, "rejected_policy_action", operator_id, [app_id, request_id], {"code": "activation_record_integrity_failure"})
        raise IssuanceRejected("Stored activation request failed its integrity check.")
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
    profile = Profile(authorized_profile)
    grants = derive_profile(profile)
    try:
        record_public_metadata(database, authority, operator_id=operator_id)
    except SigningUnavailable as error:
        with database.transaction() as db:
            append_event(db, "issuance_attempt", operator_id, [app_id, request_id], {"result": "failed", "code": "signing_metadata_mismatch"})
        raise IssuanceRejected("Signing authority metadata is inconsistent.") from error
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
            envelope = authority.sign(payload)
            append_event(db, "issuance_attempt", operator_id, [licence_id, app_id, request_id], {"result": "signed"})
            event_id = append_event(db, "successful_test_issuance" if authority.mode == "TEST" else "licence_issuance",
                                    operator_id, [licence_id, app_id, request_id], {"profile": profile.value})
            db.execute("INSERT INTO licences(licence_id,application_id,request_id,device_id,profile,issued_at,expires_at,envelope_json,audit_event_id) VALUES(?,?,?,?,?,?,?,?,?)",
                   (licence_id, app_id, request_id, req["device_id"], profile.value, now, now + DURATION_SECONDS, canonical_json(envelope).decode(), event_id))
            db.execute("UPDATE applicants SET status=? WHERE application_id=?", (ApplicantStatus.LICENCE_ISSUED.value, app_id))
            from .audit import utc_now
            db.execute("INSERT INTO application_status_history VALUES(?,?,?,?,?,?,?,?)",
                   (str(uuid.uuid4()), app_id, utc_now(), operator_id, status[0], ApplicantStatus.LICENCE_ISSUED.value, "licence_issued", event_id))
    except Exception as error:
        with database.transaction() as db:
            append_event(db, "issuance_attempt", operator_id, [app_id, request_id], {"result": "failed", "code": "issuance_failed"})
        if isinstance(error, SigningUnavailable): raise IssuanceRejected("Signing authority is unavailable.") from error
        raise
    return envelope, event_id


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
