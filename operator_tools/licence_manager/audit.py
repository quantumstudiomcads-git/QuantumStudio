"""Canonical tamper-evident local audit chain (not protection from a compromised operator)."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import uuid
import getpass
import re

from backend.licensing.canonical import canonical_json


GENESIS = "0" * 64


def current_operator_id() -> str:
    """Return a stable pseudonymous local account identifier for audit records."""
    name = getpass.getuser().strip().casefold() or "unknown"
    return "operator-" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def event_hash(event: dict) -> str:
    values = dict(event)
    values.pop("event_hash", None)
    return hashlib.sha256(canonical_json(values)).hexdigest()


def append_event(db, event_type: str, operator_id: str, affected_ids=(), details=None, timestamp=None) -> str:
    if not isinstance(operator_id, str) or not re.fullmatch(r"(?:operator|operator-[0-9a-f]{16})", operator_id):
        raise ValueError("Audit operator identifier must be a local opaque account ID.")
    previous = db.execute("SELECT event_hash FROM audit_events ORDER BY seq DESC LIMIT 1").fetchone()
    event = {
        "event_id": str(uuid.uuid4()), "timestamp": timestamp or utc_now(),
        "event_type": event_type, "operator_id": operator_id,
        "affected_ids": sorted(set(str(x) for x in affected_ids)),
        "details": details or {}, "previous_hash": previous[0] if previous else GENESIS,
    }
    digest = event_hash(event)
    db.execute("INSERT INTO audit_events(event_id,timestamp,event_type,operator_id,affected_ids,details,previous_hash,event_hash) VALUES(?,?,?,?,?,?,?,?)",
               (event["event_id"], event["timestamp"], event_type, operator_id,
                json.dumps(event["affected_ids"], separators=(",", ":")),
                canonical_json(event["details"]).decode(), event["previous_hash"], digest))
    return event["event_id"]


def verify_chain(connection) -> tuple[bool, int, str | None]:
    previous = GENESIS
    rows = connection.execute("SELECT event_id,timestamp,event_type,operator_id,affected_ids,details,previous_hash,event_hash FROM audit_events ORDER BY seq")
    count = 0
    for row in rows:
        event = {"event_id": row[0], "timestamp": row[1], "event_type": row[2], "operator_id": row[3],
                 "affected_ids": json.loads(row[4]), "details": json.loads(row[5]), "previous_hash": row[6]}
        if row[6] != previous or event_hash(event) != row[7]:
            return False, count, row[0]
        previous = row[7]
        count += 1
    return True, count, None
