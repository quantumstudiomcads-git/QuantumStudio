-- Immutable signed public artifacts; the website never signs licences.
CREATE TABLE published_licences (
  activation_request_id TEXT PRIMARY KEY REFERENCES beta_activations(activation_request_id),
  licence_id TEXT UNIQUE NOT NULL,
  envelope_json TEXT NOT NULL,
  envelope_sha256 TEXT NOT NULL,
  published_at INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status = 'PUBLISHED')
);
CREATE TABLE licence_device_challenges (
  challenge_id TEXT PRIMARY KEY,
  activation_request_id TEXT NOT NULL REFERENCES beta_activations(activation_request_id),
  installation_id TEXT NOT NULL,
  device_public_key_hash TEXT NOT NULL,
  message_json TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  consumed_at INTEGER
);
CREATE INDEX idx_licence_device_challenge_expiry ON licence_device_challenges(expires_at);
