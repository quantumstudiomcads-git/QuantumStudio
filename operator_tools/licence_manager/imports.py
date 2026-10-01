"""Strict, versioned website and activation-request import contracts."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
import uuid

from backend.licensing.verifier import public_key_hash
from backend.licensing.canonical import canonical_json, b64url_decode, b64url_encode


class ImportRejected(ValueError): pass

APPLICANT_FIELDS = {"application_id", "full_name", "email", "institution", "country", "academic_role", "research_area", "intended_evaluation", "operating_system", "privacy_consent", "privacy_version", "terms_consent", "terms_version", "communications_consent", "status", "submitted_at", "updated_at", "reviewed_at", "review_note", "licence_id", "licence_issued_at", "licence_expires_at", "revoked_at"}
PII_FIELDS = {"full_name", "email", "institution", "country", "academic_role", "research_area", "intended_evaluation", "operating_system", "privacy_consent", "privacy_version", "terms_consent", "terms_version", "communications_consent", "submitted_at"}
ACTIVATION_FIELDS = {"schema_version", "request_id", "application_id", "product", "application_version", "platform", "device_id", "device_public_key", "device_public_key_hash", "requested_profile", "created_at"}


def import_applicants_json(data: bytes | str, database, *, operator_id="operator"):
    value = _json(data)
    if not isinstance(value, dict) or set(value) != {"schema_version", "applications"} or type(value["schema_version"]) is not int or value["schema_version"] != 1 or not isinstance(value["applications"], list):
        raise ImportRejected("Website applicant file must be a schema_version 1 envelope with applications.")
    if len(value["applications"]) > 10000:
        raise ImportRejected("Applicant export exceeds the import limit.")
    prepared = []
    for row in value["applications"]:
        if not isinstance(row, dict) or set(row) - APPLICANT_FIELDS:
            raise ImportRejected("Applicant record has unknown fields.")
        if not set(PII_FIELDS).issubset(row):
            raise ImportRejected("Applicant record is incomplete.")
        application_id = _uuid(row.get("application_id"), "application_id")
        if any(not isinstance(row[key], (str, int, bool)) for key in PII_FIELDS) or any(len(str(row[key])) > 20000 for key in PII_FIELDS):
            raise ImportRejected("Applicant fields must be bounded scalar values.")
        if not isinstance(row["email"], str) or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[A-Za-z]{2,63}", row["email"]):
            raise ImportRejected("Applicant email is malformed.")
        pii = {key: str(row[key]) for key in PII_FIELDS}
        if not all(pii[k].strip() for k in ("full_name", "email", "institution")):
            raise ImportRejected("Required applicant fields are empty.")
        submission = {key: row[key] for key in sorted(PII_FIELDS)}
        digest = hashlib.sha256(canonical_json(submission)).hexdigest()
        prepared.append((application_id, pii, digest))
    inserted = 0
    for application_id, pii, digest in prepared:
        inserted += bool(database.import_applicant(application_id, pii, digest, operator_id))
    return inserted


def import_activation_json(data: bytes | str, database, *, operator_id="operator", now=None, max_age_days=30):
    value = _json(data)
    if not isinstance(value, dict) or set(value) != ACTIVATION_FIELDS or type(value.get("schema_version")) is not int or value.get("schema_version") != 1:
        raise ImportRejected("Activation request has unsupported version or unexpected fields.")
    request_id = _uuid(value["request_id"], "request_id")
    app_id = _uuid(value["application_id"], "application_id")
    value["request_id"] = request_id
    value["application_id"] = app_id
    if not isinstance(value["product"], str) or value["product"] != "Quantum Studio" or not isinstance(value["platform"], str) or value["platform"] not in {"windows-x86_64", "linux-x86_64"}:
        raise ImportRejected("Unsupported product or platform.")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?", str(value["application_version"])):
        raise ImportRejected("Malformed application version.")
    if not isinstance(value["requested_profile"], str) or value["requested_profile"] not in {"PROFESSOR_BETA", "INTERNAL_VALIDATION"}:
        raise ImportRejected("Unsupported requested profile.")
    try:
        key = b64url_decode(value["device_public_key"])
        created = datetime.fromisoformat(value["created_at"].replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError) as error:
        raise ImportRejected("Malformed key or timestamp.") from error
    if len(key) != 32 or b64url_encode(key) != value["device_public_key"] or not isinstance(value["device_public_key_hash"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["device_public_key_hash"]):
        raise ImportRejected("Malformed device key data.")
    digest = public_key_hash(key)
    if digest != value["device_public_key_hash"] or value["device_id"] != "dev_" + digest[:32]:
        raise ImportRejected("Device public key, hash, and ID do not match.")
    if created.tzinfo is None:
        raise ImportRejected("Creation timestamp must include a timezone.")
    now = now or datetime.now(timezone.utc)
    if created > now or (now - created).total_seconds() > max_age_days * 86400:
        raise ImportRejected("Activation request is expired or from the future.")
    applicant = database.connection.execute("SELECT status FROM applicants WHERE application_id=?", (app_id,)).fetchone()
    if not applicant or applicant[0] != "APPROVED":
        from .audit import append_event
        with database.transaction() as db:
            append_event(db, "rejected_policy_action", operator_id, [request_id, app_id], {"code": "applicant_not_approved"})
        raise ImportRejected("Activation request applicant is not approved.")
    content = canonical_json(value).decode("utf-8")
    request_hash = hashlib.sha256(content.encode()).hexdigest()
    existing = database.connection.execute("SELECT request_hash FROM activation_requests WHERE request_id=?", (request_id,)).fetchone()
    if existing and existing[0] != request_hash:
        from .audit import append_event
        with database.transaction() as db:
            append_event(db, "rejected_policy_action", operator_id, [request_id], {"code": "activation_conflict"})
        raise ImportRejected("Request ID is already used for different content.")
    with database.transaction() as db:
        if existing:
            from .audit import append_event
            if existing[0] == request_hash:
                append_event(db, "duplicate_import", operator_id, [request_id], {"kind": "activation_request"})
                return False
            else:
                append_event(db, "rejected_policy_action", operator_id, [request_id], {"code": "activation_conflict"})
                raise ImportRejected("Request ID is already used for different content.")
        from .audit import append_event, utc_now
        db.execute("INSERT INTO activation_requests(request_id,application_id,request_hash,request_json,imported_at,authorized_profile) VALUES(?,?,?,?,?,NULL)", (request_id, app_id, request_hash, content, utc_now()))
        append_event(db, "activation_request_import", operator_id, [request_id, app_id], {"platform": value["platform"]})
    return True


def _json(data):
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ImportRejected("Import contains a duplicate JSON field.")
            result[key] = value
        return result
    try: return json.loads(data, object_pairs_hook=object_pairs, parse_constant=lambda value: (_ for _ in ()).throw(ImportRejected("Non-finite JSON values are not allowed.")))
    except ImportRejected: raise
    except (ValueError, TypeError, UnicodeDecodeError) as error: raise ImportRejected("Import is not valid JSON.") from error


def _uuid(value, field):
    try:
        parsed = uuid.UUID(value)
        if str(parsed) != value.lower(): raise ValueError
        return str(parsed)
    except (TypeError, ValueError, AttributeError) as error: raise ImportRejected(f"Malformed {field}.") from error
