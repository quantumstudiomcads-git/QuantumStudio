PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS auth_identities (
  identity_id TEXT PRIMARY KEY NOT NULL,
  user_id TEXT NOT NULL,
  provider TEXT NOT NULL CHECK (provider IN ('GOOGLE')),
  provider_subject TEXT NOT NULL,
  provider_email TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_auth_identities_provider_subject
  ON auth_identities(provider, provider_subject);

CREATE INDEX IF NOT EXISTS idx_auth_identities_user_id
  ON auth_identities(user_id);

CREATE INDEX IF NOT EXISTS idx_auth_identities_provider_email
  ON auth_identities(provider_email);

CREATE TABLE IF NOT EXISTS google_oauth_states (
  state_hash TEXT PRIMARY KEY NOT NULL,
  purpose TEXT NOT NULL CHECK (purpose IN ('LOGIN', 'SIGNUP')),
  return_to TEXT NOT NULL,
  code_verifier TEXT NOT NULL,
  google_sub TEXT,
  google_email TEXT,
  google_name TEXT,
  email_verified INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_google_oauth_states_expires_at
  ON google_oauth_states(expires_at);

CREATE INDEX IF NOT EXISTS idx_google_oauth_states_email
  ON google_oauth_states(google_email);
