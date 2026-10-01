"""SQLite operator records, strict state changes, and transactional audit."""
from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from .audit import append_event
from .models import ApplicantStatus, TRANSITIONS


SCHEMA_VERSION = 2


class Database:
    def __init__(self, root: str | Path, protector):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "operator.sqlite3"
        self.protector = protector
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.migrate()

    def close(self):
        self.connection.close()

    def migrate(self):
        db = self.connection
        db.executescript("""
        BEGIN IMMEDIATE;
        CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS applicants(application_id TEXT PRIMARY KEY, encrypted_pii BLOB NOT NULL,
            email_index TEXT NOT NULL, submission_hash TEXT NOT NULL, status TEXT NOT NULL, imported_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS application_status_history(history_id TEXT PRIMARY KEY, application_id TEXT NOT NULL REFERENCES applicants(application_id),
            timestamp TEXT NOT NULL, operator_id TEXT NOT NULL, previous_state TEXT, new_state TEXT NOT NULL, note_code TEXT NOT NULL, audit_event_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS activation_requests(request_id TEXT PRIMARY KEY, application_id TEXT NOT NULL REFERENCES applicants(application_id),
            request_hash TEXT NOT NULL, request_json TEXT NOT NULL, imported_at TEXT NOT NULL, authorized_profile TEXT);
        CREATE TABLE IF NOT EXISTS licences(licence_id TEXT PRIMARY KEY, application_id TEXT NOT NULL REFERENCES applicants(application_id),
            request_id TEXT NOT NULL REFERENCES activation_requests(request_id), device_id TEXT NOT NULL, profile TEXT NOT NULL,
            issued_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, envelope_json TEXT NOT NULL, revoked_at TEXT, revoke_note_code TEXT, expiry_recorded_at TEXT, audit_event_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS signing_keys(kid TEXT PRIMARY KEY, public_key BLOB NOT NULL, domain TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit_events(seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL, timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL, operator_id TEXT NOT NULL, affected_ids TEXT NOT NULL, details TEXT NOT NULL, previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL);
        """)
        if not db.execute("SELECT 1 FROM schema_migrations WHERE version=1").fetchone():
            db.execute("INSERT INTO schema_migrations VALUES(1,datetime('now'))")
        columns = {row[1] for row in db.execute("PRAGMA table_info(activation_requests)")}
        if "authorized_profile" not in columns:
            db.execute("ALTER TABLE activation_requests ADD COLUMN authorized_profile TEXT")
        if not db.execute("SELECT 1 FROM schema_migrations WHERE version=2").fetchone():
            db.execute("INSERT INTO schema_migrations VALUES(2,datetime('now'))")
        db.commit()

    def transaction(self):
        return _Transaction(self.connection)

    def import_applicant(self, application_id, pii, submission_hash, operator_id="operator"):
        normalized = pii["email"].strip().casefold()
        encrypted = self.protector.encrypt(json.dumps(pii, sort_keys=True, separators=(",", ":")).encode(), aad=("applicant-pii:" + application_id).encode())
        email_index = self.protector.email_index(normalized)
        with self.transaction() as db:
            existing = db.execute("SELECT submission_hash FROM applicants WHERE application_id=?", (application_id,)).fetchone()
            if existing:
                if existing[0] != submission_hash:
                    append_event(db, "rejected_policy_action", operator_id, [application_id], {"code": "applicant_conflict"})
                    return False
                append_event(db, "duplicate_import", operator_id, [application_id], {"kind": "applicant"})
                return False
            db.execute("INSERT INTO applicants VALUES(?,?,?,?,?,datetime('now'))", (application_id, encrypted, email_index, submission_hash, ApplicantStatus.APPLIED.value))
            event_id = append_event(db, "applicant_import", operator_id, [application_id], {"source": "website"})
            from .audit import utc_now
            db.execute("INSERT INTO application_status_history VALUES(?,?,?,?,?,?,?,?)",
                       (str(uuid.uuid4()), application_id, utc_now(), operator_id, None, ApplicantStatus.APPLIED.value, "website_import", event_id))
        return True

    def applicant_pii(self, application_id):
        row = self.connection.execute("SELECT encrypted_pii FROM applicants WHERE application_id=?", (application_id,)).fetchone()
        if not row: raise KeyError(application_id)
        return json.loads(self.protector.decrypt(row[0], aad=("applicant-pii:" + application_id).encode()))

    def transition(self, application_id, new_state: ApplicantStatus, *, operator_id="operator", note_code="operator_action"):
        if note_code not in {"operator_action", "manual_review", "approved_by_operator", "rejected_by_operator", "renewal_review", "administrative_revocation", "licence_issued"}:
            raise ValueError("Status history note must use a non-sensitive controlled code.")
        row = self.connection.execute("SELECT status FROM applicants WHERE application_id=?", (application_id,)).fetchone()
        if not row: raise KeyError(application_id)
        old = ApplicantStatus(row[0])
        if new_state not in TRANSITIONS[old]:
            with self.transaction() as db:
                append_event(db, "rejected_policy_action", operator_id, [application_id], {"code": "invalid_transition"})
            raise ValueError(f"Invalid applicant transition {old.value} -> {new_state.value}.")
        with self.transaction() as db:
            row = db.execute("SELECT status FROM applicants WHERE application_id=?", (application_id,)).fetchone()
            if not row: raise KeyError(application_id)
            old = ApplicantStatus(row[0])
            if new_state not in TRANSITIONS[old]:
                raise ValueError(f"Applicant state changed concurrently; {old.value} -> {new_state.value} is no longer valid.")
            event_id = append_event(db, "application_transition", operator_id, [application_id], {"from": old.value, "to": new_state.value, "note_code": note_code})
            db.execute("UPDATE applicants SET status=? WHERE application_id=?", (new_state.value, application_id))
            from .audit import utc_now
            db.execute("INSERT INTO application_status_history VALUES(?,?,?,?,?,?,?,?)",
                       (str(uuid.uuid4()), application_id, utc_now(), operator_id, old.value, new_state.value, note_code, event_id))
        return event_id


class _Transaction:
    def __init__(self, db): self.db = db
    def __enter__(self): self.db.execute("BEGIN IMMEDIATE"); return self.db
    def __exit__(self, typ, value, traceback):
        self.db.rollback() if typ else self.db.commit()
        return False
