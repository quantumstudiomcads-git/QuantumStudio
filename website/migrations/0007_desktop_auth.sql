-- Desktop codes are distinct from browser sessions. Only public device facts.
CREATE TABLE desktop_auth_challenges (
  challenge_id TEXT PRIMARY KEY NOT NULL,
  device_code_hash TEXT NOT NULL,
  facts_json TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('PENDING','PROCESSING','COMPLETED','CONSUMED','CANCELLED','FAILED','EXPIRED')),
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  next_poll_at INTEGER NOT NULL,
  completed_at INTEGER,
  consumed_at INTEGER,
  result_json TEXT
);
CREATE INDEX idx_desktop_auth_expiry ON desktop_auth_challenges(expires_at);
CREATE TABLE desktop_auth_rate_limits (
  bucket_key TEXT PRIMARY KEY NOT NULL,
  window_start INTEGER NOT NULL,
  attempts INTEGER NOT NULL
);
