# I3 W0 corpus preselection — candidate, not registered

**Status: CANDIDATE_NOT_REGISTERED. No holdout body was read, no event was assigned, and no trial/exposure registry was written.**

This freezes a metadata-only issuer preselection under the existing #1183 / #1195 program. It is not a classification result, source-support claim, rights admission, issuer-archetype truth label, untouched-OOS claim or prediction cohort. The existing Research/Brain registry remains the only eventual trial owner.

## Immutable method evidence

- Method-before-selection SHA-256: `8fd1cfcfb9b175612d91ad2cad3a0dabec4414d4062859b07c0be393803be139`
- Candidate manifest SHA-256: `72287739689c84adfcaba5978708b4b3a3b453b1d396190d5d59b35eac9fac48`
- Freeze timestamp: `2026-10-04T05:35:05.807358+00:00`
- Security master: `data/reference/security_master.parquet` at Macro `37122b69fffa98cb160022c4831df0338ef3e7e3`, SHA-256 `ed45e4a4f9e17cc91da1a382ebeffbb1e73ae4d9fb2556036eb4efedb5b30158`; bounded Git comparison shows unchanged through Macro `01c9a44f6987c8c37f5a28ee50a51e74b83e4992`.
- Issuer master: same tested pin, SHA-256 `61738052362bdd939d686461d2bb19fcb7b01ce6fc2dc8fddd77d8e4ea44b61c`; unchanged through the same current-main comparison.
- Industry proxy source: `data/sp500_heatmap/industry_map.json` at Macro `01c9a44f6987c8c37f5a28ee50a51e74b83e4992`, blob `d33e40ae40040efd21fe1895cf3544a89d5b3637`.

Selection used only these metadata sources. It did **not** inspect filing/event/transcript bodies, candidate outputs, prices, future outcomes or validation labels.

## Frozen selection law

- Archetypes below are **sampling proxies**, not economic classifications. Metric/KPI applicability remains with the domain/source owners.
- Within each exact proxy, candidate ordering is ticker-lexical on the pinned industry map. The selected rows are a deterministic prefix, not a winner list.
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
