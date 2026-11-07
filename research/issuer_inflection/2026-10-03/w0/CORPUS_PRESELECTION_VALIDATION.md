# Corpus preselection validation receipt

- Status: **metadata-only discovery pool; not a validation corpus**
- Source-controlled selector SHA-256: `14e73eee775cfdba6085997ac01e033d0aea0e54abc00dd32e4147f2f447d0ef`
- Selector test SHA-256: `b0b506e5e738943badb6b001fa50339117a03fbac7a33b5c7d1b45825c8e92b9`
- Selector tests: **4 passed**
- Pinned industry-map Git blob: `d33e40ae40040efd21fe1895cf3544a89d5b3637`
- Pinned industry-map file SHA-256: `b72cc28c092c911dee71cde2883238cf09b20bd9c47857119c3e30a54ee08872`
- Exact selected-row SHA-256: `210dd66ab256b056e322e3602fd1fc2d3398352f6b9f76b5259739e4f533f336`
- Reproduction receipt SHA-256 (scratch execution result, not a registry): `262f158912aab03b26002ecd89039a4f85871bf9af789eb17dd96e6b9a25eb62`
- Existing PIT-membership blob for historical eligibility: `ec7085bc7460aca4a07661fa5983c424e1559be8`

Observed result: the pinned current industry map reproduces the frozen 30-name sequence exactly.

- 30 unique candidate tickers
- AAPL and PG excluded as development-exposed
- 12 beta candidates across four discovery proxies
- 12 prospective temporal-holdout candidates across five discovery proxies
- 6 reserves
- holdout event bodies unassigned and unread
- all source support and rights remain unqualified
- `trial_registered=false`
- `classification_validated=false`
- `prediction_validated=false`

**Leakage boundary:** current proxy membership never certifies historical eligibility. Historical beta assignment requires event-date PIT membership plus event-time/source-qualified business-family evidence. When that evidence is missing, the historical assignment is refused; a future eligible post-freeze event may be used instead. Prospective holdout assignment remains strictly post-freeze and pre-body-inspection.

This receipt validates deterministic metadata preselection only. The 30 names are not 30 validation units and do not satisfy the W6 heterogeneous corpus or classification sample-size gates.
