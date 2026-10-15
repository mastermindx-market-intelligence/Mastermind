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


## October 15 adversarial review: complete consumer admission

Independent read-only security review identified and reproduced a P1 bypass in the first guarded release: a replacement feed could assert `live=true` and `risk.state=stressed`, or omit the live field, and reach a forced Brain reconsideration. The fast de-risk path also independently consumed that same unverified stressed label as a hard confirmation **before** the watcher applied its read guard. That could cause a shrink-only pending paper-target effect even while the watcher later returned `tape_unavailable`. The reviewed repairs now use the **same** `data_layer.overnight.qualifies_live_risk` boundary in the watch tripwire, the materiality helper, directive generation and the overnight-only part of fast de-risk. Macro Risk Officer, dealer gamma, credit, theme and distribution protections remain active on their own original evidence.

### Distinguish a market value from authority to use it

`risk_read(groups)` remains pure arithmetic, including legitimate zero and unknown when no numeric evidence exists. It is **not an admission verdict**. `qualifies_live_risk(observation)` independently requires literal `live=True`, a closed source-quality envelope, explicit permitted-use/identity/venue flags, typed original receipt/vendor IDs, timezone-aware observation clock within the five-minute input window, known unduplicated instruments, finite bounded values for every display/risk group, and the exact recomputed risk result. The data-quality booleans alone are **not authorization**. The existing Data OS/host must authenticate the **complete observed body** against its independently retained receipt (including instrument returns and usage rights). Its current consumer-facing host hook, `_host_live_source_admitted(observation)`, deliberately returns `False` in production. Synthetic tests may inject a host verdict to verify the positive path, but this grants no real use entitlement.

The autonomous watch may bypass a **materiality threshold** with `force=True`, never the qualification gate. A manual, qualified calm review is described as a manual reconsideration rather than falsely asserting the market moved materially since the last decision. Automatically triggered material reviews describe the actual current threshold and derive all instrument labels from the canonical universe, not optional vendor names. Stale, future, nonfinite, duplicate, malformed and contradictory observations cannot reach the model prompt.

### Dashboard and model tool are also consumers

The public `/api/overnight-tape` response and the existing `get_overnight_tape` MCP tool call `overnight.public_tape(overnight.tape())`. Any unverified asserted-live packet is **downgraded to unknown/non-live and has its groups removed**, even if its JSON says stressed, verified or rights-admitted. Canonical original Yahoo EOD session bars remain available only as sanitized **historical orientation** with `EOD_NOT_LIVE`, a retrieval-clock label, canonical instrument display names and `risk=unknown`. A genuinely host-qualified live observation may pass through, but no such source is installed now. Unexpected endpoint errors remain static/sanitized with HTTP 503 and no-store; all normal dashboard responses also use no-store.

### Verification and next real integration

The first hostile-source red suite detected 18 unsafe cases. Independent review then reproduced the separate fast-de-risk bypass, malformed supplemental/giant values, wrong optional names, forced-calm prompt misstatement and a quality-only host receipt check. Each has a focused red/green regression. The local aggregate reached **166 passing tests, zero failures/errors/skips** across overnight source admission, data classification, source display, original watch, model tool, risk governor, fast de-risk and dashboard with the pinned Macro import dependency. A separate independent follow-up cleared the first 10-file qualification repair; final validation of public-read normalization is recorded separately. Exact source/test hashes and JUnit evidence belong in the existing `tests/fixtures/overnight-risk-truth/verification.json` receipt; do not sum overlapping selections into a false unique-test count.

**Activation remains unavailable:** October 15 Tiingo BOATS-bar files exist but their actual materialization receipts state Data OS identity and redistribution/backtest eligibility are not admitted. The original Yahoo source is daily, not live. Neither a source file, a subscription label, a synthetic fixture nor a model's invented receipt may change those gates. The commissioner can execute ordinary source repairs directly, but real data rights and production deployment/admission must be proven before restoring automated overnight redecisions. No installed provider, quote entitlement, live capital order or portfolio mutation has been performed.
