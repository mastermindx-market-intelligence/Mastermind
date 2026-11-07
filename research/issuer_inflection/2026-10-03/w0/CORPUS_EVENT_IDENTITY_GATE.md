# Corpus event-identity gate — owner metadata admitted, trial assignment still held

**Disposition: CANONICAL FILING METADATA SOURCE ADMITTED / EVENT ASSIGNMENT NOT REGISTERED.**

This is a metadata-only W0 qualification record. No filing body, exhibit, transcript, Q&A, outcome, model output, price or sealed holdout revision was read.

## Canonical owner law

The Earnings owner keeps the correction-safe filing identity contract:

- `engine/earnings_release/filing_key.py` blob `c1bf8319f3b24eae5661603c17bc4dc829c975b4`;
- one EDGAR filing is keyed only by exact `(CIK, accession)`;
- date tolerance is zero; filing-date or acceptance-time proximity never substitutes for accession;
- amendments remain distinct filings.

## Owner source has now landed

Macro #8392 merged as `d4e7c3788d674d43be57e0cbc017f858b832c9f1` from final source head `ae96a7f264df2d0a0fb0e3b3ef8739e04b060cc5`. Exact-head hosted CI `37227785366` and fences `37227785191` both concluded **success**.

Current Macro main observed for the accepted readback: `ae54a785984153d595de69a13c1dea4415557ed8`. Its `data/edgar/earnings_8k_dates.parquet` is exact blob `ae24d76bc985a6baba998811da3b8cb84d831423`, SHA-256 `5309ece0cd66b33d69abb8055afa05333d00bcfb43ace87d7997b3655946446f`. Read-only replay from that Git object proves:

- 173,495 rows; 2,765 unique tickers;
- exact columns `ticker,cik,accession,form,filing_date,acceptance_datetime,report_date,items`;
- zero empty accessions;
- zero duplicate `(CIK, accession)` pairs;
- latest filing date `2026-10-02`; latest acceptance `2026-10-02T20:24:12.000Z`.

The frozen 30-name discovery pool is now covered 30/30 in this accepted owner dataset:

| Role | Candidates present | Metadata rows | Latest filing date |
|---|---:|---:|---|
| beta validation | 12/12 | 948 | 2026-09-02 |
| prospective temporal-holdout candidates | 12/12 | 1,069 | 2026-09-30 |
| broad reserve | 6/6 | 558 | 2026-09-16 |

This closes the earlier **owner-source metadata availability** gap. The old five-column 98,975-row store remains historical evidence of why the gate was previously held; it is no longer current source truth.

## What this does not admit

No I3 trial event has been assigned. `event_assignments=0`, `source_revision_assignments=0`, `trial_registered=false`, and body reads remain zero.

For the 12 beta issuers, `CORPUS_BETA_PIT_MEMBERSHIP_WITNESS.md` deterministically selects the latest pre-freeze accepted metadata row (acceptance time, accession lexical tie-break) and proves one active S&P 500 PIT membership at that filing date. Those rows are now **canonical event-identity candidates**, not inspected validation examples.

Historical business-family/archetype balance remains deliberately unqualified. The estate's `collectors/sp1500_pit_sectors.py` explicitly states that every emitted sector label is as-of-now and `era_correct=False`; its receipt contract fixes `era_correct_count == 0`. Therefore I3 must not back-project today's sector/industry label onto these historical events.

Prospective temporal holdouts remain entirely unassigned: the accepted owner dataset ends `2026-10-02`, before the I3 freeze on `2026-10-04`, so none of its historical rows can become the future untouched holdout event.

## Remaining corpus gate

Before any beta body inspection or grading, the existing research owner must register the frozen event-selection artifact through the canonical experiment/trial plane, bind purpose-specific source rights, and preserve the limitation that historical archetype balance is unavailable unless a genuine event-time owner appears. An amended preregistration may treat the current proxy only as discovery metadata; it must not claim historical stratification that is not evidenced.

I3 still must not synthesize accessions, date-join filings, inspect bodies to discover identity, or count metadata rows as validation units.
