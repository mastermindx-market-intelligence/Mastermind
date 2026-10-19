# W0 owner-response validation R2 — development evidence

**Capability state: BUILT_NOT_PROVEN / DEVELOPMENT ONLY.** This hardens the I3 fixture consumer against malformed or internally contradictory `fundamental_forensics.financial_query_response/v1` bytes. It does not alter FIF source, admit a new owner contract, register I3, grant rights, or establish production coverage.

## New invariants

The single shared `baseline_replay.owner_snapshot()` boundary now requires:

- receipt schema `fundamental_forensics.metric_query/v1`;
- exact `proof_scope=selected_occurrence_consistency_only`;
- exact `selection_proof=external_immutable_ledger_required`;
- declared receipt entity equals AAPL source-native CIK `0000320193`;
- declared metric and period membership equals the fixed request;
- `query_hash` equals SHA-256 of the canonical unsigned receipt;
- every root cell has `status == state`;
- cell reason equals provenance reason;
- value cells carry no refusal reason;
- existing selected-fact issuer/source/period/unit/clock/definition/occurrence checks remain in force.

The request boundary admits only the two frozen development fixture shapes already captured by this program: the four-slot baseline replay request and the same-filing two-duration revenue request. It is not a general financial-query parser or a production API.

## Verification

- baseline reconstruction suite: **52 passed** (previous 42 plus 10 owner-envelope/receipt discriminators);
- selected-source binding suite: **15 passed**;
- verified-reader suite: **26 passed**;
- equal-duration comparator suite after reuse of this validator: **22 passed**;
- comparator arithmetic/semantic candidate suite: **17 passed**;
- candidate schema suite: **29 passed**.

Synthetic mutation tests recompute a valid `query_hash` before testing downstream semantics, except the explicit forged-query-hash discriminator. This prevents a stale checksum from making every mutation test trivially green.

The fixed owner response hashes remain unchanged:

- same-filing revenue: `a752302d0d11457920be1425cb9ebb6d1f29560b7f1e8f41a5de98075083c6af`;
- unlinked assets: `aa6f82dc415e2d3449118c627deb339f98814f0a1be6dff61e88f8819495bb21`.

No raw owner byte, frozen FIF test, source accession, rights status, trial state, product route or authority flag was modified.
