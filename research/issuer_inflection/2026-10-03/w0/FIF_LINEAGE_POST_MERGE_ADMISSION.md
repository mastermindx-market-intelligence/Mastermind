# FIF lineage post-merge admission — I3 dependency state

**Disposition: relation/value observed on merged owner source; lineage disclosure NOT TRUSTED for I3 source/correction references.**

Macro PR #7518 merged as `4294fd498e8c31cb72424e34b8769a48b1f0afd2`. Exact current-main probe pin `05216ea0ec0367a1e4061c05c73d0b0a363d4e00` now returns AAPL `total_assets` at instant `2025-09-27` as `value=359241000000` under `latest_known_as_of` once the owner lineage clock is visible. The response remains committed-golden, `attested=false`, `production_issuer_service=false`, `context_only`.

This does **not** erase the historical W1 refusal: at pre-lineage cutoffs the canonical answer remains `not_evaluable / unlinked source vintages require an explicit typed revision lineage`. Knowability is cutoff-dependent.

## New owner result

Genuine exact-main response:

- response SHA-256 `74e134907d44731555b9a2db07a2cab42998d63d4f5c6d4bfcd6c2b6efae84a5`;
- query hash `c857b4767f6d8af44ffb142c9c8d042dd44d792c5813d903f05eaa16c9e0e934`;
- selected A2 occurrence `rawfact_9669446bc8076fa26bca33a3d9a067093bddadbb28e4617318bb3de33a4eca29`;
- genuine lineage receipt `lineage_receipt_f58a751950d176fb40ac389181346a295b517df8969307547dcb13907e413fb0`.

## Blocking semantic defect

The P2 review seam was not changed between reviewed head, final feature head, and current main: `query.py` blob `529d9e7df8e6183848fea0a37280e938c0bd9238`. An exact-main hostile probe changed only `positive_evidence.parent_document_id`, kept the genuine parent/child occurrence IDs, and rebuilt the receipt's own digest/ID over the forged payload. The owner query **accepted** it, selected the same value, and emitted the forged document ID verbatim. Forged response SHA-256: `93f8e469c63f73c57283564b184e70565a32b8778652527dd747dc31ad610f41`.

Therefore I3 may record that merged FIF can now resolve this golden value after the lineage clock, but it may **not** treat the top-level lineage disclosure as a trusted owner source/correction reference. Before cross-filing I3 composition is admitted, the FIF owner must reconstruct the expected disclosure evidence from the live parent/child occurrence groups and require exact equality (or equivalent owner-proof), then return reviewed current-main evidence. Owner repair request: Macro #7518 comment `5983145862`.

No FIF source, fixture, rights, trial, product or production state was changed by this probe.
