-- Safe public device identity and licence metadata only; no signing material.
ALTER TABLE beta_activations ADD COLUMN device_public_key_hash TEXT
  CHECK (device_public_key_hash IS NULL OR (
    length(device_public_key_hash) = 64
    AND device_public_key_hash NOT GLOB '*[^0-9a-f]*'
    AND installation_id = 'dev_' || substr(device_public_key_hash, 1, 32)));
ALTER TABLE beta_activations ADD COLUMN licence_id TEXT;
ALTER TABLE beta_activations ADD COLUMN licence_status TEXT CHECK (licence_status IS NULL OR licence_status = 'ISSUED');
ALTER TABLE beta_activations ADD COLUMN licence_issued_at TEXT;
ALTER TABLE beta_activations ADD COLUMN licence_expires_at TEXT;
ALTER TABLE beta_activations ADD COLUMN licence_revoked_at TEXT;
