// Transport references only, in Paperclip's native plugin namespace.
// Native PRIMARY KEY and expected-revision UPDATE arbitrate concurrent workers.
export class Store {
  constructor(db) {
    if (!/^plugin_[a-z0-9_]+$/.test(db.namespace)) throw new Error('NAMESPACE_INVALID');
    this.db = db; this.ns = db.namespace;
  }
  async binding(company, issue) {
    const rows = await this.db.query(`SELECT revision, payload FROM ${this.ns}.bindings WHERE company_id=$1 AND issue_id=$2`, [company, issue]);
    return rows.length ? { ...rows[0].payload, revision: rows[0].revision } : null;
  }
  async saveBinding(company, issue, expected, payload) {
    const result = expected === 0
      ? await this.db.execute(`INSERT INTO ${this.ns}.bindings (company_id,issue_id,revision,payload) VALUES ($1,$2,1,$3::jsonb) ON CONFLICT DO NOTHING`, [company, issue, JSON.stringify(payload)])
      : await this.db.execute(`UPDATE ${this.ns}.bindings SET revision=revision+1,payload=$4::jsonb WHERE company_id=$1 AND issue_id=$2 AND revision=$3`, [company, issue, expected, JSON.stringify(payload)]);
    if (result.rowCount !== 1) throw new Error('BINDING_REVISION_CONFLICT');
    return this.binding(company, issue);
  }
  async get(company, operation) {
    const rows = await this.db.query(`SELECT revision,phase,payload,fingerprint FROM ${this.ns}.deliveries WHERE company_id=$1 AND operation_id=$2`, [company, operation]);
    return rows.length ? { ...rows[0].payload, revision: rows[0].revision, phase: rows[0].phase, fingerprint: rows[0].fingerprint } : null;
  }
  async insert(row) {
    const r = await this.db.execute(`INSERT INTO ${this.ns}.deliveries (company_id,operation_id,issue_id,fingerprint,revision,phase,payload) VALUES ($1,$2,$3,$4,1,$5,$6::jsonb) ON CONFLICT DO NOTHING`, [row.companyId, row.operationId, row.issueId, row.fingerprint, row.phase, JSON.stringify(row)]);
    return { inserted: r.rowCount === 1, row: await this.get(row.companyId, row.operationId) };
  }
  async change(row, patch) {
    const payload = { ...row, ...patch }; delete payload.revision;
    const r = await this.db.execute(`UPDATE ${this.ns}.deliveries SET revision=revision+1,phase=$4,payload=$5::jsonb,updated_at=CURRENT_TIMESTAMP WHERE company_id=$1 AND operation_id=$2 AND revision=$3`, [row.companyId, row.operationId, row.revision, payload.phase, JSON.stringify(payload)]);
    if (r.rowCount !== 1) throw new Error('OPERATION_REVISION_CONFLICT');
    return this.get(row.companyId, row.operationId);
  }
  async list(company, issue = null) {
    const rows = issue
      ? await this.db.query(`SELECT revision,phase,payload,fingerprint FROM ${this.ns}.deliveries WHERE company_id=$1 AND issue_id=$2 ORDER BY CASE WHEN phase IN ('consumed','returned','wake_requested','refused','expired') THEN 1 ELSE 0 END,updated_at DESC LIMIT 100`, [company, issue])
      : await this.db.query(`SELECT revision,phase,payload,fingerprint FROM ${this.ns}.deliveries WHERE company_id=$1 AND phase NOT IN ('consumed','returned','wake_requested','refused','expired') ORDER BY last_attempt_at ASC,updated_at ASC LIMIT 32`, [company]);
    return rows.map(r => ({ ...r.payload, revision: r.revision, phase: r.phase, fingerprint: r.fingerprint }));
  }
  async bindings(company) {
    const rows = await this.db.query(`SELECT revision,payload FROM ${this.ns}.bindings WHERE company_id=$1 ORDER BY last_scan_attempt_at ASC LIMIT 32`, [company]);
    return rows.map(r => ({ ...r.payload, revision: r.revision }));
  }
  async outgoingRun(company, binding, run) {
    const rows = await this.db.query(`SELECT operation_id FROM ${this.ns}.deliveries WHERE company_id=$1 AND payload->>'bindingId'=$2 AND payload->>'direction'='paperclip_to_t3' AND payload->'nativeRun'->>'runId'=$3 LIMIT 1`, [company, binding, run]);
    return rows.length > 0;
  }
  async attempted(company, operation) {
    await this.db.execute(`UPDATE ${this.ns}.deliveries SET last_attempt_at=CURRENT_TIMESTAMP WHERE company_id=$1 AND operation_id=$2`, [company, operation]);
  }
  async scanAttempted(company, issue) {
    await this.db.execute(`UPDATE ${this.ns}.bindings SET last_scan_attempt_at=CURRENT_TIMESTAMP WHERE company_id=$1 AND issue_id=$2`, [company, issue]);
  }
}
