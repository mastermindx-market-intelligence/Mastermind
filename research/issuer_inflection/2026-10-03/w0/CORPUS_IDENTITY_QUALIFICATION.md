# Corpus identity qualification — metadata-only W0 evidence

**Result: PASS for canonical identity only. Source/event/rights/trial admission remains false.**

Frozen preselection method: `8fd1cfcfb9b175612d91ad2cad3a0dabec4414d4062859b07c0be393803be139`
Frozen candidate manifest: `72287739689c84adfcaba5978708b4b3a3b453b1d396190d5d59b35eac9fac48`
Qualification record SHA-256: `5d581797edbf27e680595df10d64a61e26403734584f97c5aad9f245407bba58`
Macro metadata pin: `0d0c1533368aba1cd5f5d1ca3b14df825f540e91`
Security master SHA-256: `ed45e4a4f9e17cc91da1a382ebeffbb1e73ae4d9fb2556036eb4efedb5b30158`
Issuer master SHA-256: `61738052362bdd939d686461d2bb19fcb7b01ce6fc2dc8fddd77d8e4ea44b61c`
Rights-registry blob on protected Macro main: `e59ce0a9f98e34e45165545f21a84596c23a6de4`; `sec_edgar` row absent.

## What was proven

- All 30 frozen candidate securities exist in the canonical security master.
- All 30 bind to the exact frozen issuer IDs.
- All 30 issuers are `active`, all security-side issuer states are `RESOLVED`, and each frozen ticker matches the canonical listing inception code.
- Every row has a canonical SEC CIK; issuer identity evidence comes from `sec_company_tickers`, snapshot `2026-08-18`.
- Role counts remain 12 beta / 12 prospective temporal holdout / 6 reserve.

## What was deliberately not done

- No filing, event, transcript, Q&A, model output, price, outcome or sealed-revision body was inspected.
- No event or source revision ID was assigned to any row.
- No prospective holdout event exists yet on this record; future assignment must be strictly after the frozen selection time and before body inspection.
- No source-support or rights qualification is inferred from possession of a CIK.
- `sec_edgar` is still absent from the protected-main rights registry, so public financial evidence rights remain unadmitted.
- No experiment/trial registry write occurred; `trial_registered=false`.

## Preselection-law limitation carried forward

Identity PASS does not validate the current industry map as historical eligibility evidence. The source-controlled selector now records exact proxy predicates and reproduces the 30-name current discovery pool, but any historical beta event must separately pass event-date PIT membership plus event-time/source-qualified business-family metadata. If that owner evidence is unavailable, historical assignment remains refused. The 30-name pool is not counted as a validation corpus or as 30 qualified issuer-event units.

## Next corpus gate

For beta candidates, the existing source owner may next bind exact eligible historical event/revision metadata and rights **before** body inspection. For prospective temporal holdouts, wait for a future eligible event after the freeze, bind its identity/rights first, and only then admit it. Exclusions must remain in the denominator and deterministic same-proxy replacement may occur only before body/outcome inspection.

| Role | Proxy | Ticker | CIK | Canonical issuer | Identity | Event/body |
|---|---|---|---|---|---|---|
| beta_validation_candidate | bank | BAC | `0000070858` | `ISS:US-XNYS-BAC` | PASS | unassigned / unread |
| beta_validation_candidate | bank | C | `0000831001` | `ISS:US-XNYS-C` | PASS | unassigned / unread |
| beta_validation_candidate | bank | CFG | `0000759944` | `ISS:US-XNYS-CFG` | PASS | unassigned / unread |
| beta_validation_candidate | industrial_backlog_proxy | AME | `0001037868` | `ISS:US-XNYS-AME` | PASS | unassigned / unread |
| beta_validation_candidate | industrial_backlog_proxy | AOS | `0000091142` | `ISS:US-XNYS-AOS` | PASS | unassigned / unread |
| beta_validation_candidate | industrial_backlog_proxy | CAT | `0000018230` | `ISS:US-XNYS-CAT` | PASS | unassigned / unread |
| beta_validation_candidate | saas_proxy | ADSK | `0000769397` | `ISS:US-XNAS-ADSK` | PASS | unassigned / unread |
| beta_validation_candidate | saas_proxy | APP | `0001751008` | `ISS:US-XNAS-APP` | PASS | unassigned / unread |
| beta_validation_candidate | saas_proxy | CRM | `0001108524` | `ISS:US-XNYS-CRM` | PASS | unassigned / unread |
| beta_validation_candidate | semiconductor_channel | ADI | `0000006281` | `ISS:US-XNAS-ADI` | PASS | unassigned / unread |
| beta_validation_candidate | semiconductor_channel | AMD | `0000002488` | `ISS:US-XNAS-AMD` | PASS | unassigned / unread |
| beta_validation_candidate | semiconductor_channel | AVGO | `0001730168` | `ISS:US-XNAS-AVGO` | PASS | unassigned / unread |
| broad_reserve_candidate | consumer_price_mix_proxy | CLX | `0000021076` | `ISS:US-XNYS-CLX` | PASS | unassigned / unread |
| broad_reserve_candidate | consumer_price_mix_proxy | EL | `0001001250` | `ISS:US-XNYS-EL` | PASS | unassigned / unread |
| broad_reserve_candidate | homebuilder | DHI | `0000882184` | `ISS:US-XNYS-DHI` | PASS | unassigned / unread |
| broad_reserve_candidate | homebuilder | LEN | `0000920760` | `ISS:US-XNYS-LEN` | PASS | unassigned / unread |
| broad_reserve_candidate | homebuilder | NVR | `0000906163` | `ISS:US-XNYS-NVR` | PASS | unassigned / unread |
| broad_reserve_candidate | homebuilder | PHM | `0000822416` | `ISS:US-XNYS-PHM` | PASS | unassigned / unread |
| prospective_temporal_holdout_candidate | bank | FITB | `0000035527` | `ISS:US-XNYS-FITB` | PASS | unassigned / unread |
| prospective_temporal_holdout_candidate | bank | HBAN | `0000049196` | `ISS:US-XNAS-HBAN` | PASS | unassigned / unread |
| prospective_temporal_holdout_candidate | consumer_price_mix_proxy | CAG | `0000023217` | `ISS:US-XNYS-CAG` | PASS | unassigned / unread |
| prospective_temporal_holdout_candidate | consumer_price_mix_proxy | CHD | `0000313927` | `ISS:US-XNYS-CHD` | PASS | unassigned / unread |
| prospective_temporal_holdout_candidate | consumer_price_mix_proxy | CL | `0000021665` | `ISS:US-XNYS-CL` | PASS | unassigned / unread |
| prospective_temporal_holdout_candidate | industrial_backlog_proxy | CMI | `0000026172` | `ISS:US-XNYS-CMI` | PASS | unassigned / unread |
| prospective_temporal_holdout_candidate | industrial_backlog_proxy | DE | `0000315189` | `ISS:US-XNYS-DE` | PASS | unassigned / unread |
| prospective_temporal_holdout_candidate | saas_proxy | DASH | `0001792789` | `ISS:US-XNAS-DASH` | PASS | unassigned / unread |
| prospective_temporal_holdout_candidate | saas_proxy | FICO | `0000814547` | `ISS:US-XNYS-FICO` | PASS | unassigned / unread |
| prospective_temporal_holdout_candidate | semiconductor_channel | INTC | `0000050863` | `ISS:US-XNAS-INTC` | PASS | unassigned / unread |
| prospective_temporal_holdout_candidate | semiconductor_channel | MCHP | `0000827054` | `ISS:US-XNAS-MCHP` | PASS | unassigned / unread |
| prospective_temporal_holdout_candidate | semiconductor_channel | MPWR | `0001280452` | `ISS:US-XNAS-MPWR` | PASS | unassigned / unread |


## Canonical event-identity gate remains open

The existing Earnings source law fixes one EDGAR filing identity to the exact pair `(CIK, accession)` and sets date tolerance to zero. It explicitly says a filing-date join cannot prove source availability and would collapse amendments incorrectly.

Two existing internal metadata stores were inspected only for interface fitness:

- `data/edgar/earnings_8k_dates.parquet` has broad historical Item 2.02 coverage but its schema is only `ticker, cik, filing_date, acceptance_datetime, items`; it carries **no accession**. It therefore cannot produce the canonical filing key required for I3 selection.
- `data/edgar/material_8k_events.parquet` carries accessions, but the successful bounded beta-candidate check found zero Item 2.02 rows for all 12 beta candidates. That is a limitation of this material-event plane, **not evidence that the issuers have no earnings filings**, and it is not a reason to substitute another event.

A later attempt to combine the two planes for further diagnosis was platform-blocked before execution and was not retried through another carrier. No date/fuzzy join, synthetic accession, exhibit-body fetch, or event assignment was performed.

The next lawful event qualification must use the existing Earnings/SEC owner seam that exposes canonical accession plus source clock before body inspection. Until that owner metadata is available, every row keeps `event_id=null` and `source_revision_id=null`.
