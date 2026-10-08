# CEO submission with full autonomy armed

The existing `ceo-submit-arm` and `ceo-submit-disarm` operations can change only
`ceo_submit_armed` while the COO and both operator harness flags are already
armed. Admission requires the current root-sealed full-autonomy receipt: exact
release, both config hashes, all authority predicates, and unexpired readiness.
Split flags or a manually edited arm bit remain ineligible. This path does not
renew readiness, acquire credentials, change providers, or write the worker
configuration.

Both receipt generations share the existing `AUTONOMY_TRANSACTION` owner. Before
publishing that marker, the controller seals the exact prior config bytes,
full-autonomy receipt, optional CEO receipt, their hashes, and the persistent
Control launchd override. The full receipt is rebound only to the control config
hash, prior control hash and transaction id. All other evidence, including its
original readiness expiry, is preserved. The CEO receipt is then bound to the
same target configuration and unchanged worker hash.

Known failures restore the exact prior control and receipt bytes, prove the
restored Control process, and restore its launchd override before releasing the
marker. Unknown effects keep that exact marker. The existing
`ceo-submit-recover` owner reconciles the same transaction; it does not replay
arm/disarm. Recovery refuses modified archives or any live config/receipt that
matches neither the sealed prior generation nor its recorded target.

Fresh public CEO admission on the installed service checks its current
config/process attestation and sealed receipts immediately before the existing
canonical sink. A pending transaction, missing or stale seal, expired readiness,
or inconsistent pair refuses. Control reads the root-owned public receipts;
`worker-codex.json` remains private with its existing permissions. Full autonomy
must prove `READY` after Control reconciliation; the harness-closed path retains
`AWAITING_CANARY`.

Exact durable replay remains independent of fresh admission and current source
availability, returning the original Job without another dispatch. Changed
content still conflicts. The private principal ingress keeps its own peer,
source and admission checks. This patch does not enable production flags or
prove Autonomy V1 live; installation, normal product submission, governed worker
execution, original-parent return and independent acceptance remain required.
