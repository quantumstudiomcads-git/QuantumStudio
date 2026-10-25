-- Additive only: activation IDs and all licence foreign keys remain intact.
ALTER TABLE beta_activations ADD COLUMN revocation_reason_code TEXT
  CHECK (revocation_reason_code IS NULL OR revocation_reason_code IN
    ('DEVICE_REPLACED','DEVICE_LOST','USER_REQUEST','BETA_ACCESS_REVOKED','ADMINISTRATIVE','OTHER'));
ALTER TABLE beta_activations ADD COLUMN revocation_reason_text TEXT
  CHECK (revocation_reason_text IS NULL OR length(revocation_reason_text) BETWEEN 1 AND 240);

-- A physical device may register again, but must get a new history entry.
CREATE TRIGGER beta_activation_revoked_terminal
BEFORE UPDATE OF status ON beta_activations
WHEN OLD.status = 'REVOKED' AND NEW.status <> 'REVOKED'
BEGIN
  SELECT RAISE(ABORT, 'revoked_activation_is_terminal');
END;
