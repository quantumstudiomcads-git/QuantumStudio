PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS beta_applications (
  application_id TEXT PRIMARY KEY NOT NULL,
  full_name TEXT NOT NULL,
  email TEXT NOT NULL,
  normalized_email TEXT NOT NULL,
  email_lookup_hash TEXT NOT NULL,
  institution TEXT NOT NULL,
  country TEXT NOT NULL,
  academic_role TEXT,
  research_area TEXT NOT NULL,
  intended_evaluation TEXT,
  operating_system TEXT NOT NULL CHECK (operating_system IN ('Windows', 'Linux', 'Both', 'Other')),
  privacy_consent INTEGER NOT NULL CHECK (privacy_consent = 1),
  privacy_version TEXT NOT NULL,
  terms_consent INTEGER NOT NULL CHECK (terms_consent = 1),
  terms_version TEXT NOT NULL,
  communications_consent INTEGER NOT NULL CHECK (communications_consent IN (0, 1)),
  status TEXT NOT NULL CHECK (status IN ('APPLIED', 'UNDER_REVIEW', 'APPROVED', 'REJECTED', 'LICENSE_ISSUED', 'EXPIRED', 'REVOKED')),
  submitted_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  reviewed_at TEXT,
  review_note TEXT,
  licence_id TEXT,
  licence_issued_at TEXT,
  licence_expires_at TEXT,
  revoked_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_beta_applications_email_lookup_hash
  ON beta_applications(email_lookup_hash);
CREATE INDEX IF NOT EXISTS idx_beta_applications_status_submitted_at
  ON beta_applications(status, submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_beta_applications_licence_state
  ON beta_applications(status, licence_expires_at);

CREATE TABLE IF NOT EXISTS beta_audit_events (
  event_id TEXT PRIMARY KEY NOT NULL,
  application_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  event_timestamp TEXT NOT NULL,
  actor_reference TEXT NOT NULL,
  old_status TEXT,
  new_status TEXT,
  metadata_json TEXT NOT NULL,
  FOREIGN KEY (application_id) REFERENCES beta_applications(application_id)
);

CREATE INDEX IF NOT EXISTS idx_beta_audit_events_application_timestamp
  ON beta_audit_events(application_id, event_timestamp DESC);
