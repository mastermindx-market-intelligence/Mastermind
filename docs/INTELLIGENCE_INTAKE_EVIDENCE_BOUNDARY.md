# Intelligence intake: research relevance and candidacy evidence

## Mission and authority

The Chairman's Intelligence Hub / root-intelligence-network modernization requires useful research without converting repeated or unqualified information into portfolio-candidate authority. This bounded R1C implementation lives in `brain/intake.py`, is carried by Mastermind PR #867 / operation `intel-network-r1c-source-qualification-20260919-sol-001`, and changes neither sizing nor execution. Source custody and release procedure remain with existing owners; this document creates no new permission or state plane.

## Contract

`score` orders research relevance. `candidacy_score` controls only the existing `intake.tickers()` contribution to `portfolio.conviction.candidates()`. Observed records remain visible even when their candidacy contribution is zero. `sources` and `n_observed_sources` describe observations. `n_sources` counts eligible source families after excluding known derivatives; it is **not** a statistical independent-event sample size or a calibrated confidence estimate.

Alt-data qualification preserves source `as_of`, `generated_utc`, usability, context-only status, the reported Article-3 decision/reason, and calibration fields. Unknown values remain null. Direct alt-data candidacy requires the existing explicit grant, context-only false, and usable brain. This reader does not mint a grant or interpret sample count as validation.

Derived briefings and divergence flags remain research-visible without independent candidacy. A derived summary may compete with primitive research relevance; its already-composed score is not the base for another primitive corroboration bonus. The divergence flag contributes its existing relevance increment exactly once.

## Known Radar lineage

Macro `engine/radar_ticker.py` at `9a4dabe574e228789bf6e0bfaa9d916ac9b8917e`, blob `27c78c68b82539f182359b3882bd785932425b5e`, builds `radar_ticker.v1` rows with `source=signal` from the alt-data score and relative-strength field. Optional confirmations do not turn that row into a separately admitted source.

Those rows therefore carry internal `independent_evidence=false` and `ranking_eligible=false`. Their qualification records the source dates, context-only value, source kind, `derived_from=[altdata]`, and `altdata_derivative_without_independent_admission` reason. They remain visible for research, but cannot reintroduce a refused source through Radar, borrow an unrelated current parent grant, or earn a second source-family corroboration increment. A separately eligible raw alt-data observation still contributes on its own direct path.

This is a known family-level derivation, not an invented event-level lineage graph. Basket-attributed and other legacy Radar behavior is unchanged. Their complete dependency/admission review remains outstanding; this patch is not evidence that all remaining sources are independent or validated.

## Cutoff and fallback compatibility

Candidacy filters the complete research queue before truncation. Equal eligible score/source counts use stable ticker identity, never research relevance or inherited research ordering. Only the genuine all-seed no-evidence fallback preserves its established deliberate order. A real observation about a ticker that happens to belong to `_SEED` is not a seed fallback. Existing threshold and limit behavior is retained.

## Discriminating evidence

The unchanged fallback test failed at `d728dc59` and passed after the compatibility repair `50402d00`. The existing test was not rewritten. Sixteen additional cases cover negative/zero/large limits, threshold boundaries, and real evidence on seed symbols.

A synthetic exact-source witness used the cited Macro producer with neutral optional confirmations: refused alt-data score 90 and RS -8 produced a Radar edge of 52; the old real intake/conviction consumer admitted PROBE with candidacy 0.52. Five of six new transitive cases failed before repair, with the unaffected basket-attributed control passing. Those cases now run in the existing provenance test module, including the actual conviction candidate consumer.

A separate shadow composition used exact committed Macro inputs at `9a4dabe...`, not current installed production:

- `site/altdata/mastermind.json`: SHA-256 `5294317702e47aeffd74886017d4176a65ae593a0f4068c6f8c0e3cbfa2a2438`.
- `site/basketdata/radar_ticker.json`: SHA-256 `049725672d94fa6d8df60f6ddab87c891b85aa44a3b95c45302ccf2e54d748fc`.
- Both inputs were as-of 2026-09-18; the alt-data grant was false.
- In the isolated two-source composition, 301 research rows remained before and after; ten alt-derived names crossed candidacy 0.4 before and zero did afterward.
- This is not a change to the entire portfolio universe, an investment recommendation, or deployed proof. Other intake sources were intentionally isolated out. No orders or sizing calls were made.

## Verification and release boundary

The isolated Python 3.12 environment uses the repository's declared development dependencies and CI-pinned Macro import code `256c757b3c4f0ec759571c29a30a71387d0a18f8`. Its setup invokes no model/provider. The eight-file dependency selection passed 179 cases after the transitive repair. The expanded twelve-file intake/conviction/lenses/Brain-tool/research selection then passed 221 cases with 4 skips. Whole-repository and independent review are separate gates.

A full local canonical gate on the preceding `50402d00` head discovered 641 modules with zero exclusions. It was explicitly interrupted after the new transitive defect invalidated that candidate; it is not a pass. Before interruption it reported these seven failures:

- `tests/test_cap_s1_mastermind_operator_canary.py::test_cap_s1_fake_child_bytecode_binding_prevents_owned_source_residue`
- `tests/test_capacity_host_artifacts.py::test_complete_transport_v2_binds_nonmaterial_closure_and_exact_archive`
- `tests/test_capacity_host_artifacts.py::test_complete_transport_v2_semantic_inventory_survives_different_pack_layouts`
- `tests/test_capacity_host_artifacts.py::test_complete_transport_v2_does_not_full_buffer_pack_or_archive`
- `tests/test_capacity_host_artifacts.py::test_complete_repository_refuses_dangling_loose_object_before_git`
- `tests/test_capacity_host_artifacts.py::test_complete_repository_refuses_transient_restored_index_swap_across_git`
- `tests/test_capacity_host_artifacts.py::test_complete_transport_v3_is_canonical_zip64_and_materializes`

Observed local diagnostics included `SOURCE_METADATA_INVALID` on the macOS temporary-path ancestry. No source-custody/security check was relaxed, and no independent baseline execution is implied. Exact-head hosted integration remains required. Draft/HOLD stays until the source's actual review/release requirements are satisfied; merge and installed consumer proof remain distinct.

## Owner boundaries and next work

Macro #7305 keeps SEC and overlapping composer ownership. This implementation does not absorb its sponsorship repair. R1A must preserve source envelope/time/health through the Macro composer and real Hub interface; R1B must extend lineage beyond this known family-level derivation. GMI, MarketOntology, Data OS, evaluation, and Prophet retain their owners. Do not create another registry, event store, evaluator, graph, model router, or publication plane to complete those jobs.

After exact-head tests and independent review, use the existing release path and prove the installed reader before acceptance. Preserve this operation and its tests; do not repeat the completed reconnaissance or recreate PR #867.
