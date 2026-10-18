PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS beta_activations (
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
  FOREIGN KEY (user_id) REFERENCES users(user_id),
  FOREIGN KEY (application_id) REFERENCES beta_applications(application_id),
  UNIQUE (user_id, installation_id)
);

CREATE INDEX IF NOT EXISTS idx_beta_activations_user_status_created
  ON beta_activations(user_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_beta_activations_application
  ON beta_activations(application_id);
