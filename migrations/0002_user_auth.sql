PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY NOT NULL,
  full_name TEXT NOT NULL,
  institution TEXT NOT NULL,
  email TEXT NOT NULL,
  normalized_email TEXT NOT NULL,
  email_lookup_hash TEXT NOT NULL,
  email_verified_at TEXT,
  status TEXT NOT NULL CHECK (status IN ('PENDING', 'VERIFIED', 'DISABLED')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_users_normalized_email
  ON users(normalized_email);

CREATE INDEX IF NOT EXISTS idx_users_email_lookup_hash
  ON users(email_lookup_hash);

CREATE INDEX IF NOT EXISTS idx_users_status_created_at
  ON users(status, created_at DESC);

CREATE TABLE IF NOT EXISTS auth_challenges (
  challenge_id TEXT PRIMARY KEY NOT NULL,
  user_id TEXT NOT NULL,
  normalized_email TEXT NOT NULL,
  purpose TEXT NOT NULL CHECK (purpose IN ('SIGNUP', 'LOGIN')),
  otp_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used_at TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_auth_challenges_email_purpose
  ON auth_challenges(normalized_email, purpose, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_auth_challenges_expires_at
  ON auth_challenges(expires_at);

CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY NOT NULL,
  user_id TEXT NOT NULL,
  token_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  last_seen_at TEXT,
  revoked_at TEXT,
  FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id
  ON sessions(user_id);

CREATE INDEX IF NOT EXISTS idx_sessions_expires_at
  ON sessions(expires_at);

CREATE INDEX IF NOT EXISTS idx_sessions_revoked_at
  ON sessions(revoked_at);
