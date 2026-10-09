"""Atomic licence/receipt bundle export with fail-closed recovery semantics."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from backend.licensing.canonical import b64url_decode, canonical_json
from backend.licensing.models import DeviceIdentity
from backend.licensing.verifier import LeaseVerifier, public_key_hash

RECEIPT_SCHEMA_VERSION = 1
class ExportRecoveryError(RuntimeError):
    """A destination exists but is not the exact complete delivery bundle."""


def receipt_for(envelope: dict, audit_event_id: str) -> dict:
    licence_bytes = canonical_json(envelope)
    return {"receipt_schema_version": RECEIPT_SCHEMA_VERSION, "licence_id": envelope["licence_id"],
        "application_id": envelope["approved_application_ref"], "device_id": envelope["device_id"],
        "device_id_hash": hashlib.sha256(envelope["device_id"].encode()).hexdigest(),
        "issue_date": envelope["issued_at"], "expiry_date": envelope["expires_at"],
        "policy_profile": envelope["policy_profile"],
        "entitlement_summary": {"features": sorted(envelope["feature_entitlements"]),
                                "calculations": sorted(envelope["calculation_entitlements"])},
        "licence_file_sha256": hashlib.sha256(licence_bytes).hexdigest(), "audit_event_id": audit_event_id}


def export_licence(directory: str | Path, envelope: dict, audit_event_id: str, *, database=None, operator_id="operator"):
    if database is None: raise ValueError("Audited export requires the operator database.")
    _verify_stored_envelope(database, envelope, audit_event_id)
    licence_id = envelope.get("licence_id", "")
    if not isinstance(licence_id, str) or not re.fullmatch(r"lic_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", licence_id):
        raise ExportRecoveryError("Licence ID is not a safe opaque export identifier.")
    root = Path(directory).absolute()
    _reject_reparse_components(root)
    root.mkdir(parents=True, exist_ok=True)
    _reject_reparse_components(root)
    root = root.resolve(strict=True)
    root_identity = _identity(root)
    final = root / licence_id
    licence_bytes = canonical_json(envelope)
    receipt_bytes = canonical_json(receipt_for(envelope, audit_event_id))
    licence_path, receipt_path = final / "licence.json", final / "receipt.json"
    if final.exists() or final.is_symlink():
        _reject_reparse_components(final)
        if not final.is_dir(): raise ExportRecoveryError("Existing export destination is unsafe.")
        try:
            if {item.name for item in final.iterdir()} != {"licence.json", "receipt.json"}:
                raise ExportRecoveryError("Existing delivery bundle is incomplete or contains unexpected files.")
            matched = _read_regular(licence_path) == licence_bytes and _read_regular(receipt_path) == receipt_bytes
        except FileNotFoundError as error:
            raise ExportRecoveryError("Existing delivery bundle is incomplete; preserve it for operator recovery.") from error
        if matched:
            _record_export(database, licence_id, operator_id, licence_bytes, idempotent=True)
            return licence_path, receipt_path
        raise ExportRecoveryError("Existing delivery bundle is incomplete or does not match; preserve it for operator recovery.")

    stage = Path(tempfile.mkdtemp(prefix=f".{licence_id}.staging-", dir=root))
    try:
        _reject_reparse_components(root)
        if _identity(root) != root_identity: raise ExportRecoveryError("Export root changed during publication.")
        _write_synced(stage / "licence.json", licence_bytes)
        _write_synced(stage / "receipt.json", receipt_bytes)
        _fsync_directory(stage)
        _reject_reparse_components(root)
        if _identity(root) != root_identity or final.exists() or final.is_symlink():
            raise ExportRecoveryError("Export destination changed before publication.")
        _publish_directory_noreplace(stage, final)
        _fsync_directory(root)
        _record_export(database, licence_id, operator_id, licence_bytes)
        return licence_path, receipt_path
    except Exception:
        # If rename completed, keep the complete verified pair for an idempotent retry.
        if stage.exists(): shutil.rmtree(stage)
        raise


def _record_export(database, licence_id, operator_id, licence_bytes, idempotent=False):
    from .audit import append_event
    digest = hashlib.sha256(licence_bytes).hexdigest()
    with database.transaction() as db:
        append_event(db, "export_attempt", operator_id, [licence_id], {"licence_sha256": digest})
        append_event(db, "export", operator_id, [licence_id], {"licence_sha256": digest, "idempotent": idempotent})


def _identity(path):
    stat = path.stat()
    return (stat.st_dev, stat.st_ino, getattr(stat, "st_file_attributes", 0))


def _reject_reparse_components(path):
    import stat
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try: info = current.lstat()
        except FileNotFoundError: continue
        attrs = getattr(info, "st_file_attributes", 0)
        if stat.S_ISLNK(info.st_mode) or attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise ExportRecoveryError("Export path contains a symlink or reparse point.")
        if current != path and not current.is_dir():
            raise ExportRecoveryError("Export path contains a non-directory parent.")


def _read_regular(path):
    import stat
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
        raise ExportRecoveryError("Existing bundle contains an unsafe file.")
    before = (info.st_dev, info.st_ino, getattr(info, "st_file_attributes", 0))
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != before[:2]:
            raise ExportRecoveryError("Existing bundle file changed during inspection.")
        with os.fdopen(descriptor, "rb", closefd=False) as stream: data = stream.read()
        after = path.lstat()
        if (after.st_dev, after.st_ino, getattr(after, "st_file_attributes", 0)) != before:
            raise ExportRecoveryError("Existing bundle file changed during inspection.")
        return data
    finally: os.close(descriptor)


def _write_synced(path, data):
    with path.open("xb") as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())


def _fsync_directory(path):
    if os.name == "nt": return
    descriptor = os.open(path, os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def _publish_directory_noreplace(stage, final):
    if os.name == "nt":
        # Windows os.rename fails when the destination already exists.
        os.rename(stage, final)
        return
    # POSIX rename() may replace an empty directory on some systems. Use the
    # kernel no-replace operation or fail closed instead of accepting a race.
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise ExportRecoveryError("Filesystem does not provide atomic no-replace directory publication.")
    renameat2.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    renameat2.restype = ctypes.c_int
    if renameat2(-100, os.fsencode(stage), -100, os.fsencode(final), 1) != 0:
        error = ctypes.get_errno()
        if error == 17: raise ExportRecoveryError("Export bundle destination already exists.")
        raise OSError(error, "Atomic no-replace export publication failed.")


def _verify_stored_envelope(database, envelope, audit_event_id):
    from .audit import verify_chain
    if not verify_chain(database.connection)[0]: raise ValueError("Audit chain is invalid; licence export is blocked.")
    issued = database.connection.execute("SELECT request_id,envelope_json FROM licences WHERE licence_id=?", (envelope.get("licence_id"),)).fetchone()
    if not issued or issued[1] != canonical_json(envelope).decode("utf-8"):
        raise ValueError("Licence envelope does not match the stored issuance record.")
    audit_record = database.connection.execute("SELECT event_type,affected_ids FROM audit_events WHERE event_id=?", (audit_event_id,)).fetchone()
    if not audit_record or audit_record[0] not in {"successful_test_issuance", "licence_issuance"} or envelope["licence_id"] not in json.loads(audit_record[1]):
        raise ValueError("Licence issuance audit event is unavailable.")
    request = database.connection.execute("SELECT request_json,request_hash FROM activation_requests WHERE request_id=?", (issued[0],)).fetchone()
    keyring = {row[0]: bytes(row[1]) for row in database.connection.execute("SELECT kid,public_key FROM signing_keys WHERE domain IN ('licence','test-licence')")}
    if not request or not keyring: raise ValueError("Activation request or public signing metadata is unavailable.")
    request_value = json.loads(request[0])
    if hashlib.sha256(canonical_json(request_value)).hexdigest() != request[1]: raise ValueError("Stored activation request failed its integrity check.")
    device_key = b64url_decode(request_value["device_public_key"])
    device = DeviceIdentity(request_value["device_id"], device_key, public_key_hash(device_key))
    LeaseVerifier(keyring).verify(envelope, device)
