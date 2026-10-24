-- No legacy backfill: only new approved-account transitions provision a grant.
CREATE TABLE account_entitlements (
  entitlement_id TEXT PRIMARY KEY NOT NULL,
  user_id TEXT NOT NULL UNIQUE REFERENCES users(user_id),
  application_id TEXT NOT NULL UNIQUE REFERENCES beta_applications(application_id),
  plan_id TEXT NOT NULL CHECK(plan_id = 'beta'),
  starts_at TEXT NOT NULL CHECK(julianday(starts_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%SZ',starts_at)=starts_at),
  expires_at TEXT NOT NULL CHECK(julianday(expires_at) IS NOT NULL AND julianday(starts_at) < julianday(expires_at) AND strftime('%Y-%m-%dT%H:%M:%SZ',expires_at)=expires_at AND unixepoch(expires_at)-unixepoch(starts_at)=7776000),
  device_limit INTEGER NOT NULL DEFAULT 1 CHECK(typeof(device_limit) = 'integer' AND device_limit >= 1),
  revision INTEGER NOT NULL DEFAULT 1 CHECK(typeof(revision) = 'integer' AND revision >= 1),
  created_at TEXT NOT NULL CHECK(julianday(created_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%SZ',created_at)=created_at),
  updated_at TEXT NOT NULL CHECK(julianday(updated_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%SZ',updated_at)=updated_at)
);

-- Approval triggers are installed by 0010 after its activation-history rebuild.
