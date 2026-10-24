"""Explicit fixed beta entitlement fixtures; never production configuration."""
from datetime import datetime, timezone


def beta_entitlement(application_id="12345678-1234-4123-8123-123456789abc", *, starts_at=1792368000, device_limit=1):
    def stamp(value):
        return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return dict(entitlement_id="ent_" + "a" * 32, user_id="user-a", application_id=application_id,
                plan_id="beta", starts_at=stamp(starts_at), expires_at=stamp(starts_at+90*86400),
                device_limit=device_limit, revision=1, created_at=stamp(starts_at), updated_at=stamp(starts_at))
