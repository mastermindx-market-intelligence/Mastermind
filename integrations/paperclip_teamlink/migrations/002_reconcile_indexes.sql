CREATE INDEX IF NOT EXISTS deliveries_pending_by_issue
  ON plugin_mastermind_teamlink_ddd6e53475.deliveries (company_id, issue_id, last_attempt_at, updated_at)
  WHERE phase NOT IN ('consumed','returned','wake_requested','refused','expired');
CREATE INDEX IF NOT EXISTS deliveries_pending_by_attempt
  ON plugin_mastermind_teamlink_ddd6e53475.deliveries (company_id, last_attempt_at, updated_at)
  WHERE phase NOT IN ('consumed','returned','wake_requested','refused','expired');
CREATE INDEX IF NOT EXISTS bindings_by_scan_attempt
  ON plugin_mastermind_teamlink_ddd6e53475.bindings (company_id, last_scan_attempt_at);
