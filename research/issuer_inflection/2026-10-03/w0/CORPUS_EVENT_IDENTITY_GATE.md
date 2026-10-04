# Corpus event-identity gate — current owner metadata is not yet accession-complete

**Disposition: METADATA COVERAGE PARTIAL / CANONICAL EVENT IDENTITY NOT ADMITTED.**

This is a metadata-only W0 qualification record. No filing body, exhibit, transcript, Q&A, outcome, model output, price or sealed holdout revision was read.

## Canonical owner law

Current Macro pin observed for this qualification:

`d4f32cfb3bc5d5041273294175ae1feba582e53b`

The Earnings owner has a frozen correction-safe filing identity contract:

- `engine/earnings_release/filing_key.py` blob `c1bf8319f3b24eae5661603c17bc4dc829c975b4`;
- one EDGAR filing is keyed **only** by exact `(CIK, accession)`;
- `JOIN_DATE_TOLERANCE_DAYS = 0`;
- filing date / acceptance-time proximity may never substitute for accession;
- an amendment is a different filing even when it belongs to the same event.

Current collector code `collectors/edgar_earnings_8k.py` blob `19665592a256bb4ef8af6ebc2fdd0f74bfdf992f` has already been upgraded to emit `accession`, `form` and `report_date` in addition to ticker/CIK/date/clocks.

## Committed store is still pre-upgrade

The actual committed metadata store on the same current Macro pin is:

`data/edgar/earnings_8k_dates.parquet`

- Git blob: `e1fdf2c9717b02a98f6fe7cfab7e88e51bf912d6`
- file SHA-256: `3076d611cda61455ea65c8aaf7bcebcc37c341330c4b37048ce89ecc79bd2ae4`
- rows: `98,975`
- unique tickers: `1,314`
- committed columns: exactly `ticker, cik, filing_date, acceptance_datetime, items`
- **no accession column**
- global latest filing date: `2026-07-02`
- global latest acceptance time: `2026-07-02T20:31:36.000Z`

So the owner implementation has moved ahead of the durable dataset. Current committed rows cannot produce the canonical filing key and cannot be upgraded by I3 using date/fuzzy matching.

## Frozen 30-name pool coverage

| Role | Candidates | Tickers present in legacy store | Missing | Rows | Latest filing metadata |
|---|---:|---:|---|---:|---|
| beta validation candidates | 12 | 11 | `CFG` | 886 | 2026-06-03 |
| prospective temporal-holdout candidates | 12 | 12 | none | 1,050 | 2026-05-21 |
| broad reserve | 6 | 5 | `EL` | 468 | 2026-06-11 |

This is **coverage only**. None of those rows is an I3 event assignment because every row lacks accession.

Prospective temporal-holdout rows are historical metadata and cannot be repurposed as holdout events: their future event must occur strictly after the frozen selection time and be identity/rights-qualified before body inspection.

## No alternate committed accession store found

A current repository search found no committed `data/**` earnings-wire / filing-key artifact carrying the missing accession identity. The only accession hit under `data/edgar` was unrelated `dead_name_delisting.json`.

The estate therefore has:

- broad historical date/acceptance metadata;
- upgraded owner code capable of emitting accession on a future/backfilled run;
- **no current committed accession-bearing earnings metadata store suitable for the frozen I3 corpus**.

## Required owner action before beta event assignment

The existing Earnings/SEC owner—not I3—must refresh/backfill through the upgraded collector or another already-owned accession-bearing metadata seam, then publish/read back an immutable metadata cut containing at minimum:

- canonical issuer/CIK;
- exact accession;
- form;
- Item 2.02 membership;
- filing date;
- source acceptance datetime;
- report date when present;
- owner dataset/source revision identity and recorded/admission clock;
- rights/source-family binding for the intended I3 research purpose.

For historical beta assignment, event-date PIT membership and event-time/source-qualified business-family evidence remain separately required. For prospective holdout assignment, only future events after the freeze are eligible.

I3 must not:

- synthesize accessions from filing dates;
- join on `(CIK, filing_date)` or a tolerance window;
- fetch filing bodies merely to discover identity;
- substitute `material_8k_events` rows that do not represent the earnings event;
- treat 28/30 legacy metadata presence as 28 qualified validation units.

Until the owner publishes an accession-complete metadata cut, every frozen corpus row retains `event_id=null`, `source_revision_id=null`, and source-event qualification false.

## Live successor candidate — #8392

Macro #8392 head `3ec016886c2fd359cacab5c3739dc2fc7fd76f26` is an **open owner candidate**, not admitted mainline source. Its exact parquet blob `ae24d76bc985a6baba998811da3b8cb84d831423` / SHA-256 `5309ece0cd66b33d69abb8055afa05333d00bcfb43ace87d7997b3655946446f` was inspected metadata-only through the authenticated repository API. It has 173,495 rows, all eight upgraded columns, zero empty accessions, zero duplicate `(CIK, accession)` pairs, and covers all 30 frozen I3 names.

That head materially demonstrates that the existing owner can close the legacy-store identity gap, but it is not yet an I3 source because #8392 is open, current-head CI/review are unfinished, and Macro main continues moving. I3 dependency comment: #8392 `5983380209`.

The candidate data ends `2026-10-02`, before the I3 freeze on `2026-10-04`; therefore none of its rows can be used as a prospective temporal-holdout event.

`CORPUS_BETA_PIT_MEMBERSHIP_WITNESS.md` uses only that candidate metadata plus the existing PIT membership owner. All 12 beta names are single-match S&P 500 members at their latest candidate filing dates. This closes index-membership qualification **for the witness only**. Historical business-family/archetype balance remains unqualified because the available sector/industry map is current/static rather than point-in-time. No event has been assigned.
