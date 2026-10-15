# Overnight tape qualification — source truth, not synthetic market confidence

**State:** SOURCE FIX / NOT PROVEN LIVE. The active paper book and its existing scheduler/settlement authority are unchanged.

## Failure corrected

The legacy Yahoo downloader requested five days of **daily historical bars**, but its retrieval timestamp and any nonempty result caused the dashboard and overnight redecision loop to describe the source as a live overnight tape. Empty or invalid results also defaulted the deterministic risk label to `calm`. A daily close-to-close return is not proof that anything moved after the US close, and an empty risk read is not evidence of calm.

The repaired flow retains those daily session-change rows for **indicative historical orientation only** and explicitly returns `live:false`, `risk.state:unknown`, `source_quality.classification:EOD_NOT_LIVE`, and `as_of_kind:retrieved_at_not_source_observed_at`. It does not manufacture an intraday observation time. Separately supplied qualified nonzero or zero changes can still be classified deterministically by the pure `risk_read` function; invalid and nonfinite signals cannot vote for calm.

The overnight watcher preserves the existing pending paper target but returns `skipped:tape_unavailable` when the tape is explicitly non-live or its risk state is unknown. Even a forced reconsideration cannot recast the daily-history feed as fresh overnight evidence. The risk tripwire independently refuses an explicitly non-live tape. This leaves previous session changes visible for inspection without authorizing models, orders or allocations.

The dashboard's API catches unexpected provider errors with a **static sanitized** `overnight_source_unavailable` error, `risk.state:unknown` and HTTP 503, rather than publishing internal exception text or a false calm result. Ordinary successfully handled but absent data may return HTTP 200 with an explicit unknown state.

## Data-source availability is not entitlement

The commissioned session inspected two October 15 local Tiingo BOATS-bars materialization manifests on the M2. Both declared `dataos_identity_admitted:false`, `redistribution_admitted:false`, and `pit_backtest_eligible:false`. Their raw quotes or prices were **not** copied or used by the dashboard. The presence of locally stored parquet files grants neither public redistribution nor provenance, freshness, execution pricing or backtest rights.

Actual reactive overnight risk requires a separately evidenced intraday source: exact vendor venue and observation clock, bounded freshness, licensed display/usage rights, canonical price basis, and a source-to-consumer identity/receipt. Reuse the existing Tiingo/Data OS and market-calendar authorities. These conditions do not imply an addressable external owner session, but they **are real data/rights gates** and must not be set true by model inference or by changing a boolean.

## Verification and release boundary

Focused network-free tests cover offline unknown, crypto-only partial data, dramatic daily ES/VIX changes, malformed/nonfinite inputs, legitimate zero changes, stale-source force protection, API exceptions and error sanitation, and explicit daily Yahoo interval. The original overnight watch and paper-portfolio contract tests remain in scope. Exact source/test hashes and result are in `tests/fixtures/overnight-risk-truth/verification.json`.

**No provider deployment, order, paper-account mutation, secret, live source admission, licensed data redistribution or numeric portfolio target has been authorized or performed.** This patch deliberately prevents false live confidence while the real intraday feed is unqualified. A future feed activation must have independent browser/live-market and paper-session proof before automatic redecision is reinstated.
