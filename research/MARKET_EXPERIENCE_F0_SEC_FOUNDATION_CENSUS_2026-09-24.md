# F0 SEC event foundation census — reuse, migrate, do not duplicate

Status: **FOUNDATION PRESENT / CANONICAL KEY MIGRATION REQUIRED**.

This census sharpens the Market Experience implementation path after discovering the existing broad
SEC Item-2.02 anchor and the existing Company Intelligence revision-chain/backfill machinery. It is
read-only evidence. It does not run an SEC backfill, move a production marker, admit a training
corpus, or create another earnings/event owner.

## Exact current source

Macro protected/default branch was read at commit
`836379db84f9e34354f54e2fb26cd2065d186034`.

Pinned objects:

| Owner | Git blob |
|---|---|
| `collectors/edgar_earnings_8k.py` | `19665592a256bb4ef8af6ebc2fdd0f74bfdf992f` |
| `data/edgar/earnings_8k_dates.parquet` | `e1fdf2c9717b02a98f6fe7cfab7e88e51bf912d6` |
| `data/edgar/earnings_8k_dates_manifest.json` | `a45bc80a3cea8b2cd554624cdeda19cb66d47b5d` |
| `scripts/refresh_event_workspaces.py` | `7d01aacb3bec29e42de799eeed480d16f930389b` |

Executable receipt:
`research/MARKET_EXPERIENCE_F0_SEC_ANCHOR_RECEIPT_2026-09-24.json`.

Audit:
`research/market_experience_f0_sec_anchor_audit.py`.

Tests:
`tests/test_market_experience_f0_sec_anchor_audit.py`.

Targeted audit suite: **11 passed, 0 failed**.

## Broad SEC anchor already exists

The committed Item-2.02 store contains:

- **98,975 rows**;
- **1,314 CIKs / 1,314 ticker labels**;
- filing dates **2004-08-24 through 2026-07-02**;
- 98,975 parseable filing dates;
- 98,975 parseable SEC acceptance timestamps;
- every row carries the exact Item `2.02` token;
- **1,143 CIKs span at least eight years**;
- **1,255 CIKs carry at least twenty rows**.

The collection manifest contains **1,315 entries**, all `status=ok`, with **zero missing SEC
older-file shards** recorded. Its collection window is
2026-07-05T10:14:01Z through 2026-07-05T10:47:38Z.

The manifest's summed `n_filings` is 99,758 while the committed parquet has 98,975 rows, a
difference of 783. The audit deliberately does **not** assign a cause to that delta. Current code
documents why the historical date-key dedup can destroy same-day amendments, but proving how many of
the 783 rows are amendments versus another cause requires a canonical-key re-fetch/reconciliation.

## The load-bearing schema gap

The committed parquet is still the legacy five-column shape:

`ticker, cik, filing_date, acceptance_datetime, items`.

The current collector contract already expects:

`ticker, cik, accession, form, filing_date, acceptance_datetime, report_date, items`.

This matters because:

- filing identity is exactly `(cik, accession)`;
- an `8-K/A` is a distinct filing revision, not another event;
- event grouping is `(cik, report_date)`, not ticker/date proximity;
- `form` distinguishes source-assigned amendment status;
- old `(ticker, filing_date)` dedup can collapse a same-day amendment.

Therefore the current broad store is a **high-coverage event-date/availability anchor**, but it is
not yet sufficient for exact revision-aware historical event reconstruction.

The current collector is already written to upgrade legacy rows when fresh keyed rows are supplied.
However, its resumability manifest marks the historical CIKs `ok`; a routine incremental run is
not evidence that the old rows will be rehydrated. A migration/reconciliation operation must be
explicitly admitted through the existing data owner. This F0 work does not run it.

## Existing Company Intelligence path also exists

`scripts/refresh_event_workspaces.py` already implements immutable Company Intelligence event
revision chains for the A5A homebuilder path and keeps:

- SEC acceptance as `source_available_at`;
- actual discovery/reconstruction wall clock as `observed_at`;
- exact accession and report-period identity;
- chronological predecessor selection within an event revision chain;
- fail-closed chain reads;
- immutable generation history.

A 2026-08-23 production incident is explicitly documented in source: before the discovery boundary
was correctly wired, a run scanned the homebuilders' SEC recent blocks back toward 2010 and
published roughly 170 historical event generations before the 25-minute job timeout. Those
generations are preserved as immutable history; the code was then hardened so first-ever discovery
is bounded to current/prior fiscal year and subsequent discovery advances only beyond the canonical
prior boundary.

That incident is **not** a template for an unbounded backfill. It is evidence that the existing
event contract can carry historical revisions and that uncontrolled historical discovery has
already failed operationally once.

## Revised architecture ruling

The previous working hypothesis — "build a historical SEC reconstruction path" — is now too broad.

The correct implementation is:

1. **Reuse the existing broad SEC anchor collector.**
2. **Migrate/reconcile its committed rows to the existing canonical
   `(cik, accession, form, report_date)` contract.**
3. **Reuse the existing Company Intelligence event/document/revision chain.**
4. Add only the bounded adapter needed to turn an admitted keyed SEC anchor + exact held release
   bytes into a current `event_workspace.v1` reconstruction.
5. Keep reconstruction truth explicit at the Market Experience / Market Memory consumer:
   `public_reconstruction`, with current acquisition/observation time; never claim that
   Mastermind possessed the source historically.
6. Do not change E3's Q&A-owned paths or open its sealed transcript holdouts.

No second event store, filing key, revision chain, source clock, publisher, or corpus registry is
needed.

## First vertical slice

Before any broad migration, use one permanently development-visible issuer/event to prove the
path in isolation:

- selection frozen from metadata before body inspection;
- exact CIK/accession/report-date from current SEC source;
- exact release body SHA;
- SEC acceptance as public availability;
- current acquisition time as observed/reconstructed-at;
- build through existing binding + Company Intelligence contracts;
- no consensus, transcript, or EquityDesk substitution;
- typed absence for missing rails;
- no production publication;
- no forecast/rank/size/trade authority.

AAPL may be used as this development case because its Company Intelligence evidence is already
development-visible and therefore cannot serve as untouched Market Experience evaluation evidence.

## What remains before training

The first trainable loop still needs:

- a rights-qualified universe definition;
- canonical historical security-to-issuer joins;
- Massive per-security coverage for the eventual window;
- canonical-key migration/reconciliation of the broad SEC anchor;
- exact source-body availability for selected SEC events;
- frozen cohort, missingness denominator, and temporal evaluation split before outcome inspection.

Compute remains secondary to these evidence/rights joins.

## Nonclaims

This census does not claim:

- that the 783-row manifest/store delta is caused solely by amendments;
- that 98,975 anchors have held release bodies;
- that the homebuilder incident produced a complete or unbiased historical corpus;
- that the broad SEC store was historically possessed by Mastermind at event time;
- that any stock cohort is admitted;
- that any forecasting value has been demonstrated.
