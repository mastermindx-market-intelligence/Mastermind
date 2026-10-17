# I3 W0 corpus preselection — candidate, not registered

**Status: CANDIDATE_NOT_REGISTERED. No holdout body was read, no event was assigned, and no trial/exposure registry was written.**

This freezes a metadata-only issuer preselection under the existing #1183 / #1195 program. It is not a classification result, source-support claim, rights admission, issuer-archetype truth label, untouched-OOS claim or prediction cohort. The existing Research/Brain registry remains the only eventual trial owner.

## Reproducible method evidence

- Source-controlled selector: `corpus_preselection_protocol.py`, SHA-256 `14e73eee775cfdba6085997ac01e033d0aea0e54abc00dd32e4147f2f447d0ef`.
- Selector tests: `test_corpus_preselection_protocol.py`, SHA-256 `b0b506e5e738943badb6b001fa50339117a03fbac7a33b5c7d1b45825c8e92b9`; **4 passed**.
- Freeze timestamp: `2026-10-04T05:35:05.807358+00:00`.
- Security master: `data/reference/security_master.parquet`, SHA-256 `ed45e4a4f9e17cc91da1a382ebeffbb1e73ae4d9fb2556036eb4efedb5b30158`.
- Issuer master: SHA-256 `61738052362bdd939d686461d2bb19fcb7b01ce6fc2dc8fddd77d8e4ea44b61c`.
- Current discovery source: Macro `94e5865e13fc42063f9c7d1e9b485958ccaee5b1` `data/sp500_heatmap/industry_map.json`, Git blob `d33e40ae40040efd21fe1895cf3544a89d5b3637`, file SHA-256 `b72cc28c092c911dee71cde2883238cf09b20bd9c47857119c3e30a54ee08872`.
- Existing historical membership owner: `data/breadth/sp1500_pit_membership.parquet`, Git blob `ec7085bc7460aca4a07661fa5983c424e1559be8`.
- Exact current-source regeneration produced the same 30-name sequence; canonical selected-row SHA-256 `210dd66ab256b056e322e3602fd1fc2d3398352f6b9f76b5259739e4f533f336`.
- The earlier scratch method/manifest hashes remain historical provenance only; the committed selector above is the reproducible method contract.

Selection used only these metadata sources. It did **not** inspect filing/event/transcript bodies, candidate outputs, prices, future outcomes or validation labels.

## Frozen selection law

- Archetypes below are **sampling proxies**, not economic classifications. Metric/KPI applicability remains with the domain/source owners.
- Exact proxy predicates are source-controlled in `corpus_preselection_protocol.py` as closed `(sector, sub_industry)` sets; ordering is ticker-lexical after excluding AAPL/P&G. The selected rows are deterministic positions, not a winner list.
- The pinned current industry map is **candidate discovery only**. It cannot certify historical membership or historical business-family eligibility.
- A beta candidate may receive a historical event only after event-date membership is re-qualified through the existing PIT membership owner and event-time/source-qualified business-family metadata. If that evidence is unavailable, historical beta assignment is blocked and the candidate may only receive a future eligible post-freeze event.
- Beta-validation candidate: first three identities in each of semiconductor, application-software, industrial/backlog and bank proxies → 12 issuers / 4 proxies.
- Prospective temporal-holdout candidate: positions 4–6 semiconductors, positions 4–5 software/industrial/bank, first three consumer price/mix → 12 issuers / 5 proxies. **Only a future eligible event strictly after the freeze can be assigned.**
- Broad reserve: six remaining selected identities, including the homebuilder family. Homebuilder/IMCE is already a development-exposed family and is not an untouched holdout on this record.
- AAPL and P&G are explicitly development-exposed and excluded from this candidate pool.
- If metadata/source/rights qualification fails **before body inspection**, advance deterministically to the next frozen ticker in the same proxy and retain the exclusion in the denominator. No replacement after body/outcome inspection.
- E3 sealed revisions are excluded. Historical model knowledge is not claimed PIT-clean. Prospective event freezing is required for predictive use.
- `trial_registered=false`; `source_support_status=UNQUALIFIED_METADATA_ONLY`; `rights_status=UNQUALIFIED` for every row.

## Candidate identities

| Role | Proxy | Pos | Ticker | Canonical issuer | Canonical security |
|---|---|---:|---|---|---|
| beta_validation_candidate | bank | 1 | BAC | `ISS:US-XNYS-BAC` | `SEC:US-XNYS-BAC` |
| beta_validation_candidate | bank | 2 | C | `ISS:US-XNYS-C` | `SEC:US-XNYS-C` |
| beta_validation_candidate | bank | 3 | CFG | `ISS:US-XNYS-CFG` | `SEC:US-XNYS-CFG` |
| beta_validation_candidate | industrial_backlog_proxy | 1 | AME | `ISS:US-XNYS-AME` | `SEC:US-XNYS-AME` |
| beta_validation_candidate | industrial_backlog_proxy | 2 | AOS | `ISS:US-XNYS-AOS` | `SEC:US-XNYS-AOS` |
| beta_validation_candidate | industrial_backlog_proxy | 3 | CAT | `ISS:US-XNYS-CAT` | `SEC:US-XNYS-CAT` |
| beta_validation_candidate | saas_proxy | 1 | ADSK | `ISS:US-XNAS-ADSK` | `SEC:US-XNAS-ADSK` |
| beta_validation_candidate | saas_proxy | 2 | APP | `ISS:US-XNAS-APP` | `SEC:US-XNAS-APP` |
| beta_validation_candidate | saas_proxy | 3 | CRM | `ISS:US-XNYS-CRM` | `SEC:US-XNYS-CRM` |
| beta_validation_candidate | semiconductor_channel | 1 | ADI | `ISS:US-XNAS-ADI` | `SEC:US-XNAS-ADI` |
| beta_validation_candidate | semiconductor_channel | 2 | AMD | `ISS:US-XNAS-AMD` | `SEC:US-XNAS-AMD` |
| beta_validation_candidate | semiconductor_channel | 3 | AVGO | `ISS:US-XNAS-AVGO` | `SEC:US-XNAS-AVGO` |
| broad_reserve_candidate | consumer_price_mix_proxy | 4 | CLX | `ISS:US-XNYS-CLX` | `SEC:US-XNYS-CLX` |
| broad_reserve_candidate | consumer_price_mix_proxy | 5 | EL | `ISS:US-XNYS-EL` | `SEC:US-XNYS-EL` |
| broad_reserve_candidate | homebuilder | 1 | DHI | `ISS:US-XNYS-DHI` | `SEC:US-XNYS-DHI` |
| broad_reserve_candidate | homebuilder | 2 | LEN | `ISS:US-XNYS-LEN` | `SEC:US-XNYS-LEN` |
| broad_reserve_candidate | homebuilder | 3 | NVR | `ISS:US-XNYS-NVR` | `SEC:US-XNYS-NVR` |
| broad_reserve_candidate | homebuilder | 4 | PHM | `ISS:US-XNYS-PHM` | `SEC:US-XNYS-PHM` |
| prospective_temporal_holdout_candidate | bank | 4 | FITB | `ISS:US-XNYS-FITB` | `SEC:US-XNYS-FITB` |
| prospective_temporal_holdout_candidate | bank | 5 | HBAN | `ISS:US-XNAS-HBAN` | `SEC:US-XNAS-HBAN` |
| prospective_temporal_holdout_candidate | consumer_price_mix_proxy | 1 | CAG | `ISS:US-XNYS-CAG` | `SEC:US-XNYS-CAG` |
| prospective_temporal_holdout_candidate | consumer_price_mix_proxy | 2 | CHD | `ISS:US-XNYS-CHD` | `SEC:US-XNYS-CHD` |
| prospective_temporal_holdout_candidate | consumer_price_mix_proxy | 3 | CL | `ISS:US-XNYS-CL` | `SEC:US-XNYS-CL` |
| prospective_temporal_holdout_candidate | industrial_backlog_proxy | 4 | CMI | `ISS:US-XNYS-CMI` | `SEC:US-XNYS-CMI` |
| prospective_temporal_holdout_candidate | industrial_backlog_proxy | 5 | DE | `ISS:US-XNYS-DE` | `SEC:US-XNYS-DE` |
| prospective_temporal_holdout_candidate | saas_proxy | 4 | DASH | `ISS:US-XNAS-DASH` | `SEC:US-XNAS-DASH` |
| prospective_temporal_holdout_candidate | saas_proxy | 5 | FICO | `ISS:US-XNYS-FICO` | `SEC:US-XNYS-FICO` |
| prospective_temporal_holdout_candidate | semiconductor_channel | 4 | INTC | `ISS:US-XNAS-INTC` | `SEC:US-XNAS-INTC` |
| prospective_temporal_holdout_candidate | semiconductor_channel | 5 | MCHP | `ISS:US-XNAS-MCHP` | `SEC:US-XNAS-MCHP` |
| prospective_temporal_holdout_candidate | semiconductor_channel | 6 | MPWR | `ISS:US-XNAS-MPWR` | `SEC:US-XNAS-MPWR` |

## Validation receipt

- Result: **PASS**
- 30 unique canonical issuer/security identities.
- 12 beta candidates across four proxies.
- 12 prospective temporal-holdout candidates across five proxies.
- AAPL/P&G absent from validation/holdout pool.
- Holdout event identities remain unassigned; body-inspected flag false for every row.
- Homebuilder family absent from holdout role.
- All source support and rights remain unqualified.
- Trial registration, classification validation and prediction validation all false.

## Admission boundary

This candidate becomes canonical only if the existing Research/Brain owner accepts the method/identity set, supplies a serialized writer/fence, binds actual event/revision IDs and source-rights eligibility before body inspection, and read-back proves the same registered record/hash. Until then it is a recoverable W0 preselection artifact only.

No UI, alert, model, ranking, sizing, trading, Prophet or production authority follows from cohort membership.
