CREATE TABLE IF NOT EXISTS plugin_mastermind_teamlink_ddd6e53475.bindings (
  company_id text NOT NULL,
  issue_id text NOT NULL,
  revision integer NOT NULL,
  payload jsonb NOT NULL,
  last_scan_attempt_at timestamptz NOT NULL DEFAULT '1970-01-01T00:00:00Z',
  PRIMARY KEY (company_id, issue_id)
);
CREATE TABLE IF NOT EXISTS plugin_mastermind_teamlink_ddd6e53475.deliveries (
  company_id text NOT NULL,
  operation_id text NOT NULL,
  issue_id text NOT NULL,
  fingerprint text NOT NULL,
  revision integer NOT NULL,
  phase text NOT NULL,
  payload jsonb NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_attempt_at timestamptz NOT NULL DEFAULT '1970-01-01T00:00:00Z',
  PRIMARY KEY (company_id, operation_id)
);
CREATE INDEX IF NOT EXISTS deliveries_by_issue ON plugin_mastermind_teamlink_ddd6e53475.deliveries (company_id, issue_id);
