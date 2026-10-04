# CI #5992 — precise failure and held evidence-placement repair

**Release remains blocked. The guard and original captured bytes have not been changed.**

Candidate tested: `b95a7ddcb24f74a81b9486620c219217518d6f20`. CI run `37164665870` (#5992), job `111325140274`. The job checked integrated merge ref `d56dbdd2246ec46d51e67bd95b2c47de215608be` (candidate into `c776f8dc8d3dabb0070b51ad7f04d71987ff6df1`). Shards one and three succeeded; shard two failed in `tests/test_ceo_submit_armed_composition.py::test_d8_template_topology_and_protected_defaults`, with 150 findings of literal `400`. Other setup, compile and shell checks succeeded; their passes are not whole-CI acceptance.

The failure was obtained through the documented native GitHub workflow-job log action. A prior CLI log read failed because the client protected terminal escape sequences. That protection was not disabled. A generic GitHub annotations request was outside that action's URL allowlist; it was not used as evidence or retried under alternate arguments.

## Source-bound diagnosis

The protected guard at current procedure source `1c435eb9b079ea36ac8cebceb6b0666946804030` is byte-identical to the inspected local guard; Git blob `db923c6ee6f852e808f7dd21e06a3b32c352b693`, SHA-256 `211137a1f9c39d1fbe02e431f56044b9847d196bb9bcd85e9ff4aa95155813b3`.

Its existing contract distinguishes executable/config source from JSON under `research/evidence/`, where a bounded structural identity check applies. Our six captured `.response.json` files live under the I3 candidate's nested evidence path, so they entered the generic source scanner. A read-only exact-path diagnostic attributes 25 findings to each of these six unchanged responses, accounting for all 150 findings:

- `evidence/aapl_same_filing_annual_revenue.response.json`
- `evidence/aapl_unlinked_assets.response.json`
- `evidence/baseline-replay/after_a1_before_a2_admission.response.json`
- `evidence/baseline-replay/after_a2_admission.response.json`
- `evidence/baseline-replay/before_a1_admission.response.json`
- `evidence/baseline-replay/before_a2_source.response.json`

No executable I3 source produced those findings. Each unchanged response passes the guard's existing structural evidence function; adding a synthetic `control_uid` field with a forbidden topology value causes that same function to report it. The pure diagnostic did not modify the guard, source data, rights or runtime. This is a placement/classification diagnosis, not a new allowlist or a claim that the failing guard may be ignored.

## Repair state

The proposed correction is byte-preserving placement of these six files under the repository's existing `research/evidence/issuer_inflection/2026-10-03/` home, with explicit old/new path/hash lineage and updated consumers. It must retain the current structural identity guard and negative controls, not obscure literals, rewrite source receipts or weaken the check.

**That relocation has NOT occurred.** Its preflight—bounded reference lookup plus exact destination presence/custody check—was platform-blocked before execution. No destination absence or custody clearance was inferred, and that action was not retried/repackaged through another tool. All six original files remain in place with their original hashes. No guard source or exception was changed.

Astra/C4 retains the repair obligation on #1195. The next repair requires a permitted, reconciled destination/custody preflight and review of byte-preserving placement, followed by the existing guard and exact-head CI. Until then this draft must not be readied, merged or deployed. Independent W0/interface/publication/rights/capture acceptance remains separately required even after CI is repaired.
