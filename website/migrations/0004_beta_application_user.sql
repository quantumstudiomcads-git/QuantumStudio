PRAGMA foreign_keys = ON;

ALTER TABLE beta_applications
  ADD COLUMN user_id TEXT REFERENCES users(user_id);

CREATE UNIQUE INDEX IF NOT EXISTS ux_beta_applications_user_id
  ON beta_applications(user_id)
  WHERE user_id IS NOT NULL;
