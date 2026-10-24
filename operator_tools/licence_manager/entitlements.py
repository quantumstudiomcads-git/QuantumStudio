"""Strict public beta grant snapshots; no billing or signing authority here."""
from datetime import datetime
import json
import re
from backend.licensing.canonical import canonical_json

BETA_DURATION_SECONDS = 90 * 86400
FIELDS = set("entitlement_id user_id application_id plan_id starts_at expires_at device_limit revision created_at updated_at".split())


def validate_entitlement(record, application_id):
    try:
        if not isinstance(record, dict) or set(record) != FIELDS:
            raise ValueError
        if (not re.fullmatch(r"ent_[0-9a-f]{32}", record["entitlement_id"])
                or not isinstance(record["user_id"], str) or not 1 <= len(record["user_id"]) <= 128
                or record["application_id"] != application_id or record["plan_id"] != "beta"):
            raise ValueError
        for name in ("device_limit", "revision"):
            if type(record[name]) is not int or record[name] < 1:
                raise ValueError
        times = {}
        for name in ("starts_at", "expires_at", "created_at", "updated_at"):
            stamp = datetime.fromisoformat(record[name].replace("Z", "+00:00"))
            if (stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0
                    or stamp.isoformat(timespec="seconds").replace("+00:00", "Z") != record[name]):
                raise ValueError
            times[name] = stamp.timestamp()
        if times["expires_at"] - times["starts_at"] != BETA_DURATION_SECONDS:
            raise ValueError
        return int(times["starts_at"]), int(times["expires_at"])
    except (ValueError, TypeError, AttributeError, KeyError):
        raise ValueError("A valid fixed 90-day account entitlement is required; legacy records need reviewed provisioning.") from None


def require_current_entitlement(record, application_id, now):
    starts, expires = validate_entitlement(record, application_id)
    if not starts <= now < expires:
        raise ValueError("Account entitlement is not currently valid.")
    return starts, expires


def remember_entitlement(db, record):
    existing = db.execute("SELECT snapshot_json FROM website_account_entitlements WHERE application_id=?", (record["application_id"],)).fetchone()
    snapshot = canonical_json(record).decode()
    if existing and json.loads(existing[0]) != record:
        raise ValueError("Account entitlement conflicts with its original local snapshot; no new licence was issued.")
    db.execute("INSERT OR IGNORE INTO website_account_entitlements VALUES(?,?,?)",
               (record["application_id"], record["entitlement_id"], snapshot))
