# Recovery replay integrity: active bounded phase

Original research commission and PR1470 continue. Source pin78388ac29f7e54c9dfe7799a8e4769fb46d4aed6 reused; startinghead2dd591f3d clean. Current phase tests and repairs the explicit normalized synthetic recovery contract, not the blocked DEEP+ decoder or the blocked legacy timestamp-impact audit. No workerstatus/result action is attempted; original lp-clock04-design-review return obligation remains unresolved.

Done when: normalized atomic batches are transactional, intermediate unobservable states cannot masquerade as forecasts, multi-symbol replay and cutoffs preserve exact clocks/IDs, incomplete source coverage is not invented, and an end-to-end research consumer demonstrably reads the same bounded outputs. Code/tests/evidence only; no production schema, trading/ranking/sizing, data purchase or new source.

All batches/watermarks in this phase are explicit synthetic input declarations, never inferred from equal timestamps in a real feed. Actual source event-group and reset rules still need separate verified mapping. Preserve the previous empiricalresults unchanged.
