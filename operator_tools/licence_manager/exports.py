"""Atomic deterministic licence JSON and privacy-minimal operator receipt export."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile

from backend.licensing.canonical import b64url_decode, canonical_json
from backend.licensing.models import DeviceIdentity
from backend.licensing.verifier import LeaseVerifier, public_key_hash


RECEIPT_SCHEMA_VERSION = 1


def receipt_for(envelope: dict, audit_event_id: str) -> dict:
    licence_bytes = canonical_json(envelope)
    return {
        "receipt_schema_version": RECEIPT_SCHEMA_VERSION,
        "licence_id": envelope["licence_id"],
        "application_id": envelope["approved_application_ref"],
        "device_id": envelope["device_id"],
        "device_id_hash": hashlib.sha256(envelope["device_id"].encode()).hexdigest(),
        "issue_date": envelope["issued_at"], "expiry_date": envelope["expires_at"],
        "policy_profile": envelope["policy_profile"],
        "entitlement_summary": {"features": sorted(envelope["feature_entitlements"]), "calculations": sorted(envelope["calculation_entitlements"])},
        "licence_file_sha256": hashlib.sha256(licence_bytes).hexdigest(), "audit_event_id": audit_event_id,
    }


def export_licence(directory: str | Path, envelope: dict, audit_event_id: str, *, database=None, operator_id="operator"):
    if database is None:
        raise ValueError("Audited export requires the operator database.")
    _verify_stored_envelope(database, envelope, audit_event_id)
    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)
    licence_id = envelope["licence_id"]
    licence_path = target_dir / f"{licence_id}.licence.json"
    receipt_path = target_dir / f"{licence_id}.receipt.json"
    licence_bytes = canonical_json(envelope)
    receipt = canonical_json(receipt_for(envelope, audit_event_id))
    from .audit import append_event
    existing = (licence_path.exists(), receipt_path.exists())
    if any(existing):
        if all(existing) and licence_path.read_bytes() == licence_bytes and receipt_path.read_bytes() == receipt:
            from .audit import append_event
            with database.transaction() as db:
                append_event(db, "export_attempt", operator_id, [licence_id], {"licence_sha256": hashlib.sha256(licence_bytes).hexdigest()})
                append_event(db, "export", operator_id, [licence_id], {"licence_sha256": hashlib.sha256(licence_bytes).hexdigest(), "idempotent": True})
            return licence_path, receipt_path
        with database.transaction() as db:
            append_event(db, "rejected_policy_action", operator_id, [licence_id], {"code": "export_destination_conflict"})
        raise ValueError("Export destination already contains a different or incomplete licence export.")
    with database.transaction() as db:
        append_event(db, "export_attempt", operator_id, [licence_id], {"licence_sha256": hashlib.sha256(licence_bytes).hexdigest()})
    staged = []
    published = []
    try:
        staged.append(_stage(licence_path, licence_bytes))
        staged.append(_stage(receipt_path, receipt))
        for temporary, final in zip(staged, (licence_path, receipt_path)):
            os.replace(temporary, final)
            published.append(final)
        with database.transaction() as db:
            append_event(db, "export", operator_id, [licence_id], {"licence_sha256": hashlib.sha256(licence_bytes).hexdigest()})
    except Exception:
        for final in published:
            final.unlink(missing_ok=True)
        raise
    finally:
        for temporary in staged:
            temporary.unlink(missing_ok=True)
    return licence_path, receipt_path


def _verify_stored_envelope(database, envelope, audit_event_id):
    from .audit import verify_chain
    if not verify_chain(database.connection)[0]:
        raise ValueError("Audit chain is invalid; licence export is blocked.")
    issued = database.connection.execute("SELECT request_id,envelope_json FROM licences WHERE licence_id=?", (envelope.get("licence_id"),)).fetchone()
    if not issued or issued[1] != canonical_json(envelope).decode("utf-8"):
        raise ValueError("Licence envelope does not match the stored issuance record.")
    audit_record = database.connection.execute("SELECT event_type,affected_ids FROM audit_events WHERE event_id=?", (audit_event_id,)).fetchone()
    if not audit_record or audit_record[0] not in {"successful_test_issuance", "licence_issuance"} or envelope["licence_id"] not in json.loads(audit_record[1]):
        raise ValueError("Licence issuance audit event is unavailable.")
    request = database.connection.execute("SELECT request_json,request_hash FROM activation_requests WHERE request_id=?", (issued[0],)).fetchone()
    keyring = {row[0]: bytes(row[1]) for row in database.connection.execute("SELECT kid,public_key FROM signing_keys WHERE domain IN ('licence','test-licence')")}
    if not request or not keyring:
        raise ValueError("Activation request or public signing metadata is unavailable.")
    request_value = json.loads(request[0])
    if hashlib.sha256(canonical_json(request_value)).hexdigest() != request[1]:
        raise ValueError("Stored activation request failed its integrity check.")
    device_key = b64url_decode(request_value["device_public_key"])
    device = DeviceIdentity(request_value["device_id"], device_key, public_key_hash(device_key))
    LeaseVerifier(keyring).verify(envelope, device)


def _atomic(path: Path, data: bytes):
    temp = path.with_name("." + path.name + ".tmp")
    try:
        with temp.open("wb") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists(): temp.unlink()


def _stage(path: Path, data: bytes) -> Path:
    descriptor, name = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return temporary
