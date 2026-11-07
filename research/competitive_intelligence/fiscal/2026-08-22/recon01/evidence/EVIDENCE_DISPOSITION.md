# Run 01 evidence disposition — rights-safety repair

This file records what happened to every raw capture taken during Run 01, and why.
It exists so the run's conclusions stay auditable after the raw authenticated assets
were removed from canonical Git.

- Repair authority: the packaging ruling on PR #121 (2026-08-23).
- Governing doctrine: `research/SOL_EXECUTIVE_PRODUCT_ARCHITECTURE_AND_HANDOFF_MANUAL_2026-08-16.md`
  § 3 "Clean-room competitor parity doctrine" — in particular § 3.2 (do not copy
  restricted corpora, paid-seat data, proprietary text or protected assets) and
  § 3.3 (do not answer that constraint by throwing away the feature knowledge).
- Repair scope: packaging only. **No new Fiscal.ai access was made.** No replacement
  captures were taken, no Copilot prompts were spent, no account state was changed.

## Why nearly every full-frame capture had to go

Fiscal.ai is a data product. On almost every route the screen *is* the licensed
dataset: standardized multi-year statements, consensus estimates, compiled
institutional-ownership tables, third-party equity research, earnings-call
transcripts, investor-deck pages and fund-letter commentary. A "screenshot of the
UI" on those routes is a copy of the corpus, not a picture of an interface, so no
crop of them is rights-safe.

The exception is the class of states that contain no data *by construction*:
empty states, loading states, explicit no-match dialogs, a product failure showing
only public quote fields, and the run's own user-generated object. Those are
retained as tight crops.

## Classification

| Class | Meaning | Count |
|---|---|---:|
| A | Safe as captured, no edit needed | 0 |
| B | Safe after tight crop — retained | 5 |
| C | Proprietary/restricted content — removed | 23 |
| D | Unnecessary duplicate — removed | 2 |

Class A is empty on purpose: every full-frame capture carried either compiled
dataset content or the complete branded application shell, so none qualified
as-is.

## Retained evidence (class B)

Each retained file is a re-encoded crop of the original capture. Re-encoding
through a clean surface drops source metadata. Each was re-inspected after
cropping to confirm it contains no dataset content.

| Observation | Retained file | Shows | Why it is rights-safe |
|---|---|---|---|
| OBS-016 | `screens_sanitized/OBS-016-screener-criteria-loading-crop.png` | Screener criteria field holding the custom-metric name, plus the in-flight loading spinner | Contains a query string the run itself typed and a spinner; no company data is rendered |
| OBS-023 | `screens_sanitized/OBS-023-notifications-empty-state-crop.png` | Notifications dialog empty state and its two tabs | An empty state contains no data by construction; the populated page behind it is cropped out |
| OBS-024 | `screens_sanitized/OBS-024-dashboard-listing-mismatch-crop.png` | The saved dashboard row that resolved to a non-US listing | Four public quote fields for one mega-cap issuer; this is the product-failure finding itself, not a corpus |
| OBS-029 | `screens_sanitized/OBS-029-custom-metric-persisted-crop.png` | Custom Metrics tab with the run's own metric row restored after reload | The only values shown are the run's own derived ratio, to one decimal |
| OBS-030 | `screens_sanitized/OBS-030-add-existing-metric-no-match-crop.png` | Add Existing Metric dialog: apply-to-all enabled, exact-name query, explicit no-match | A no-match dialog contains no data by construction |

## Removed evidence

All 30 raw full-frame captures were deleted, including the five that a retained
crop was derived from. The 25 that have no retained crop are listed in
`removed_assets.jsonl` with their original path, SHA-256 and byte length; the
other five carry their original SHA-256 on the observation record itself, as
`original_asset_sha256`. Either way every capture's prior existence stays
provable without distributing its content. The observation records are unchanged
in substance and continue to carry the factual workflow findings.

Grouped reasons:

- **Compiled financial dataset** (standardized statements, segment histories,
  consensus estimates, price targets, company-statistics panels):
  OBS-001, OBS-002, OBS-003, OBS-004, OBS-009, OBS-010, OBS-011, OBS-012,
  OBS-013, OBS-027, OBS-028.
- **Third-party documents and research** (equity research text, earnings-call
  transcripts, investor-deck pages, fund letters and letter-derived positioning):
  OBS-005, OBS-006, OBS-007, OBS-008, OBS-020, OBS-021, OBS-022.
- **Compiled ownership data, including named natural persons**:
  OBS-017, OBS-018, OBS-019.
- **Aggregated third-party news and research feeds**:
  OBS-025, OBS-026.
- **Duplicates of a retained crop** (no restricted content; removed only because
  they add nothing): OBS-014, OBS-015.

## Evidence discrepancies found during this repair

Classifying the captures required looking at them rather than trusting their
filenames. Three captures did not corroborate the observation that cited them.
These are recorded rather than silently corrected, and the accepted observation
text has not been rewritten.

1. **OBS-011 — direct contradiction.** The record states that after bounded
   waiting "no chart, table, rows or explanatory empty state appeared" and is
   filed `negative`. The archived capture
   (`af802bdaffc1e08e92c961c78a67d3ad8d056287fb8a9579b426367823142133`) shows a
   rendered consensus chart *and* a populated estimates table for that company.
   The observation's `status` is therefore changed to `disputed`; its claim text
   is left intact. The most likely reconciliation is that the surface hydrated
   after the capture was taken, which would make this a latency finding rather
   than a coverage finding — but that is not established, and Run 01 cannot
   settle it without a new run, which this repair is forbidden to make.
2. **OBS-016 — non-corroborating.** The record describes a broad standard metric
   catalog; the capture shows the request still loading. The claim is not
   contradicted, only unproven by this frame. The retained crop shows the loading
   state honestly.
3. **OBS-012 — non-corroborating.** The record describes as-reported issuer
   wording and granular sparse rows; the capture shows a single charted revenue
   series instead. The claim is not contradicted, only undepicted.

Discrepancies 1 and 3 are carried into `unresolved_questions.md`.

## What a reader loses, and what stays provable

Lost: the ability to re-read the competitor's rendered data from this repository.
That loss is intended.

Retained and still provable from text alone: every route and surface visited, the
user job each served, the interaction pattern, the context-transfer boundaries,
the gating/null/loading/failure semantics, the product insight, the observation
IDs, and the SHA-256 identity of each capture that was taken.

## History note

Removing these files in a follow-up commit does not erase them from Git history —
the blobs stay reachable at the pre-repair head `758741b9` for as long as this
branch exists. Purging them from history requires either a squash merge (so they
never enter `master`) or an explicit force-push rewrite of this branch. That is a
deliberate decision for the reviewer, not one this repair makes on its own.
