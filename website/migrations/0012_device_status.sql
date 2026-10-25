-- Status revision is distinct from immutable account entitlement revision.
ALTER TABLE beta_activations ADD COLUMN authorization_revision INTEGER NOT NULL DEFAULT 1 CHECK(authorization_revision >= 1);
CREATE TRIGGER beta_activation_state_revision
AFTER UPDATE OF status ON beta_activations WHEN OLD.status <> NEW.status
BEGIN
  UPDATE beta_activations SET authorization_revision = OLD.authorization_revision + 1
  WHERE activation_request_id = NEW.activation_request_id;
END;
CREATE TABLE device_status_challenges (
  challenge_id TEXT PRIMARY KEY,
  activation_request_id TEXT NOT NULL REFERENCES beta_activations(activation_request_id),
  message_json TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  consumed_at INTEGER
);
CREATE INDEX idx_device_status_challenge_expiry ON device_status_challenges(expires_at);
