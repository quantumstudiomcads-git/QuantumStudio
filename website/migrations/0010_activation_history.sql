-- Preserve revoked activations, publications and outstanding proof challenges.
-- Child staging avoids disabling foreign keys while rebuilding their parent.
CREATE TABLE m9_saved_publications AS SELECT * FROM published_licences;
CREATE TABLE m9_saved_challenges AS SELECT * FROM licence_device_challenges;
DROP TABLE licence_device_challenges;
DROP TABLE published_licences;
CREATE TABLE beta_activations_m9 (
  activation_request_id TEXT PRIMARY KEY NOT NULL,
  user_id TEXT NOT NULL,
  application_id TEXT NOT NULL,
  installation_id TEXT NOT NULL,
  platform TEXT NOT NULL CHECK (platform IN ('windows', 'linux')),
  architecture TEXT NOT NULL CHECK (architecture = 'x86_64'),
  app_version TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('AUTHORIZED', 'FLAGGED', 'REVOKED')),
  flag_reason TEXT CHECK (
    flag_reason IS NULL OR flag_reason IN (
      'DEVICE_LIMIT',
      'APPLICATION_NOT_ELIGIBLE',
      'INSTALLATION_REVOKED',
      'INVALID_INSTALLATION',
      'UNSUPPORTED_VERSION'
    )
  ),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  authorized_at TEXT,
  revoked_at TEXT,
  device_public_key_hash TEXT CHECK(device_public_key_hash IS NULL OR (
    length(device_public_key_hash)=64 AND device_public_key_hash NOT GLOB '*[^0-9a-f]*'
    AND installation_id='dev_' || substr(device_public_key_hash,1,32))),
  licence_id TEXT,
  licence_status TEXT CHECK(licence_status IS NULL OR licence_status='ISSUED'),
  licence_issued_at TEXT,
  licence_expires_at TEXT,
  licence_revoked_at TEXT,
  FOREIGN KEY (user_id) REFERENCES users(user_id),
  FOREIGN KEY (application_id) REFERENCES beta_applications(application_id)
);

INSERT INTO beta_activations_m9(activation_request_id,user_id,application_id,installation_id,platform,architecture,app_version,status,flag_reason,created_at,updated_at,authorized_at,revoked_at,device_public_key_hash,licence_id,licence_status,licence_issued_at,licence_expires_at,licence_revoked_at) SELECT activation_request_id,user_id,application_id,installation_id,platform,architecture,app_version,status,flag_reason,created_at,updated_at,authorized_at,revoked_at,device_public_key_hash,licence_id,licence_status,licence_issued_at,licence_expires_at,licence_revoked_at FROM beta_activations;
DROP TABLE beta_activations;
ALTER TABLE beta_activations_m9 RENAME TO beta_activations;
CREATE UNIQUE INDEX ux_beta_activations_current_device ON beta_activations(user_id,installation_id) WHERE status <> 'REVOKED';
CREATE INDEX idx_beta_activations_user_status_created ON beta_activations(user_id,status,created_at DESC);
CREATE INDEX idx_beta_activations_application ON beta_activations(application_id);
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

INSERT INTO published_licences SELECT * FROM m9_saved_publications;
INSERT INTO licence_device_challenges SELECT * FROM m9_saved_challenges;
DROP TABLE m9_saved_publications;
DROP TABLE m9_saved_challenges;

CREATE TRIGGER provision_beta_entitlement_insert
AFTER INSERT ON beta_applications
WHEN NEW.status = 'APPROVED' AND NEW.user_id IS NOT NULL
BEGIN
  INSERT INTO account_entitlements
    (entitlement_id,user_id,application_id,plan_id,starts_at,expires_at,device_limit,revision,created_at,updated_at)
  SELECT 'ent_' || lower(hex(randomblob(16))), NEW.user_id, NEW.application_id, 'beta',
    strftime('%Y-%m-%dT%H:%M:%SZ',COALESCE(NEW.reviewed_at,NEW.updated_at)),
    strftime('%Y-%m-%dT%H:%M:%SZ',COALESCE(NEW.reviewed_at,NEW.updated_at),'+90 days'),
    1, 1, strftime('%Y-%m-%dT%H:%M:%SZ',NEW.updated_at), strftime('%Y-%m-%dT%H:%M:%SZ',NEW.updated_at)
  WHERE NOT EXISTS (SELECT 1 FROM account_entitlements WHERE application_id=NEW.application_id OR user_id=NEW.user_id)
    AND NEW.licence_id IS NULL AND NEW.licence_issued_at IS NULL AND NEW.licence_expires_at IS NULL
    AND NOT EXISTS (SELECT 1 FROM beta_activations WHERE application_id=NEW.application_id
      AND (status IN ('AUTHORIZED','REVOKED') OR licence_id IS NOT NULL));
  INSERT INTO beta_audit_events(event_id,application_id,event_type,event_timestamp,actor_reference,old_status,new_status,metadata_json)
  SELECT 'evt_' || lower(hex(randomblob(16))), NEW.application_id, 'ACCOUNT_ENTITLEMENT_PROVISIONED',
    created_at, 'approved-account-workflow', NULL, NULL,
    json_object('schema',1,'entitlement_id',entitlement_id,'plan_id',plan_id,'starts_at',starts_at,'expires_at',expires_at,'device_limit',device_limit)
  FROM account_entitlements WHERE application_id=NEW.application_id AND changes()=1;
END;

CREATE TRIGGER provision_beta_entitlement_approve
AFTER UPDATE OF status ON beta_applications
WHEN OLD.status = 'UNDER_REVIEW' AND NEW.status = 'APPROVED' AND NEW.user_id IS NOT NULL
BEGIN
  INSERT INTO account_entitlements
    (entitlement_id,user_id,application_id,plan_id,starts_at,expires_at,device_limit,revision,created_at,updated_at)
  SELECT 'ent_' || lower(hex(randomblob(16))), NEW.user_id, NEW.application_id, 'beta',
    strftime('%Y-%m-%dT%H:%M:%SZ',COALESCE(NEW.reviewed_at,NEW.updated_at)),
    strftime('%Y-%m-%dT%H:%M:%SZ',COALESCE(NEW.reviewed_at,NEW.updated_at),'+90 days'),
    1, 1, strftime('%Y-%m-%dT%H:%M:%SZ',NEW.updated_at), strftime('%Y-%m-%dT%H:%M:%SZ',NEW.updated_at)
  WHERE NOT EXISTS (SELECT 1 FROM account_entitlements WHERE application_id=NEW.application_id OR user_id=NEW.user_id)
    AND NEW.licence_id IS NULL AND NEW.licence_issued_at IS NULL AND NEW.licence_expires_at IS NULL
    AND NOT EXISTS (SELECT 1 FROM beta_activations WHERE application_id=NEW.application_id
      AND (status IN ('AUTHORIZED','REVOKED') OR licence_id IS NOT NULL));
  INSERT INTO beta_audit_events(event_id,application_id,event_type,event_timestamp,actor_reference,old_status,new_status,metadata_json)
  SELECT 'evt_' || lower(hex(randomblob(16))), NEW.application_id, 'ACCOUNT_ENTITLEMENT_PROVISIONED',
    created_at, 'approved-account-workflow', NULL, NULL,
    json_object('schema',1,'entitlement_id',entitlement_id,'plan_id',plan_id,'starts_at',starts_at,'expires_at',expires_at,'device_limit',device_limit)
  FROM account_entitlements WHERE application_id=NEW.application_id AND changes()=1;
END;
