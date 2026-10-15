# Deterministic earnings event reaction replay — research-only

**Source:** `reaction_replay.py` · **Consumer:** `replay_casebook.py` · **Tests:** `test_reaction_replay.py`, `test_replay_casebook.py` · **Real SEC acceptance evidence:** `sec_acceptance_2026.json` · **Nine source packets:** `sourced_event_packets/`.  
**Owner/carrier:** additive research tooling within Mastermind PR #1407, not a replacement for the Macro Earnings/Event, Alpha MAS-118/MAS-271, Prophet, or `scripts/backtest_event_priors.py` owner. No production/data-collection/publishing authority.

## Delivered machine capability

Given an economic issuer/fiscal event, either **verified earliest publicly available earnings-release timestamp** or an explicitly weaker **corroborated after-close public-release window**, explicit exchange regular-session clocks and split-/dividend-adjusted issuer/market/sector closes, report first-session issuer, stock-minus-market and stock-minus-sector returns; plus H5/H20 drift from the *first affected regular-session close*. Decimal return 0.02 = 2%.

Refuse or preserve typed absence for intraday-close contamination, exact regular-close boundary, missing price bars, absent source or adjustment, unobserved as-of date, missing calendar, incomplete horizon, invalid/duplicate sessions, nonfinite prices and unverified release time. A modeled H5 is descriptive, *not* an executable fill.

### Run offline

```sh
cd research/earnings_expectations
python3 -m pytest -q test_reaction_replay.py test_replay_casebook.py test_management_guidance_cases.py test_media_witnesses.py test_expectation_owner_adapter.py test_owner_inspection_consumer.py test_tiingo_manifest_inspection.py test_pre_event_windows.py test_capex_guidance_cases.py
python3 reaction_replay.py /path/to/source_verified_input.json
python3 replay_casebook.py --format markdown
python3 replay_casebook.py --format json
```

Runtime uses Python standard library only (`zoneinfo`); `pytest` is used in tests. JSON is read and result JSON written to stdout, no automatic network calls, file writes, rank signals or trade instructions. CLI returns exit code 2 with a typed refusal on malformed inputs.

### Required input contract

```json
{
  "event": {
    "event_ref": "canonical-issuer-event-id",
    "issuer_ref": "CIK:...",
    "fiscal_target": "issuer-fiscal-quarter",
    "first_public_source_ref": "immutable-source-reference",
    "first_published_utc": "2026-07-30T20:01:00Z",
    "first_publication_clock_status": "VERIFIED_FIRST_PUBLIC_RELEASE"
  },
  "evaluated_asof_utc": "2026-08-31T22:00:00Z",
  "sessions": [
    {"date":"2026-07-30","open_utc":"2026-07-30T13:30:00Z","close_utc":"2026-07-30T20:00:00Z"}
  ],
  "price_series": {
    "issuer":{"adjustment":"split_dividend_adjusted_close","source_ref":"approved-price-source","bars":[{"date":"2026-07-30","adjusted_close":100.0}]},
    "market":{"adjustment":"split_dividend_adjusted_close","source_ref":"approved-market-source","bars":[{"date":"2026-07-30","adjusted_close":100.0}]},
    "sector":{"adjustment":"split_dividend_adjusted_close","source_ref":"approved-sector-source","bars":[{"date":"2026-07-30","adjusted_close":100.0}]}
  }
}
```

This is a **field-shape illustration**, deliberately too short to calculate a return: a complete input needs the true previous session, the first affected session and enough future sessions. No sample value is market evidence. The implementation uses `first_published_utc` and requires its release-proof status, but the sample is intentionally incomplete.

## Verified tests

**230/230 offline tests passed** with Python 3.13 / pytest 9. Code and tests were verified by Git blob against tested local sources. Tests include after-close, premarket, intraday, weekend, UTC winter/summer clocks, missing benchmark, cutoff leakage, unsupported sources, and refusal to accept an SEC-only clock. Synthetic structural fixtures are supplemented with **nine actual retrospective adjusted-close source packets**, independently checked for arithmetic; this does not prove data licensing, current vendor freshness, a live backtest, causal attribution, or Terminal operation.

## Nine SEC timestamps — not first-publication proof

`sec_acceptance_2026.json` has 9 verified filing-detail Accepted display timestamps for three earnings events apiece at Alphabet, Amazon and Microsoft. All `first_publication_utc` values intentionally remain null and `first_publication_clock_status` remains `SEC_ACCEPTANCE_ONLY`. Do **not** infer UTC from the SEC page’s displayed clock without verifying its timezone. These records are source evidence, not eligible replay packet clock values.

Example: Yahoo's syndication of Amazon's BusinessWire Q2 2026 release is dated July 30 **4:01 p.m. GMT-4**, while the SEC 8-K filing index displays acceptance **16:06:23** the same day. The filing clock therefore cannot be equated with initial publication. Sources:
- https://uk.finance.yahoo.com/news/amazon-com-announces-second-quarter-200100298.html
- https://www.sec.gov/Archives/edgar/data/1018724/000101872426000024/0001018724-26-000024-index.html

The BusinessWire minute-resolution timestamp independently establishes a reported public release by that minute, but does not prove no earlier disclosure or the precise second. Preserve clock precision/uncertainty.

## Next owner-preserving integration

1. **Earnings Event** owner supplies verified first-public-release clock, economic issuer and correction lineage. SEC acceptance remains a separate fact.
2. **Price data** owner supplies consistent adjusted prices and real exchange sessions from authorized historical sources, plus a named sector comparator.
3. **MAS-118** research consumes replay labels as independent event-window fixtures within the incumbent event-prior harness; no second production engine or new truth store.
4. **MAS-271 / C19** expects the existing SRC-A1/EXP-1 owner to qualify real EPS/revenue same-fiscal-target, same-basis two-vintage inputs, or return a typed unestimable result. This module cannot invent Street consensus.
5. Only after real admission and chronological controls should the preregistered B2-vs-C1 expectations-ratchet hypothesis be graded. No Prophet signal/gate/size promotion without its separate authority.

**Current data limitation:** bounded M2 home search found no `expectation_observations.parquet`; this says nothing about volumes or hosts outside that search. Some mounted Tiingo raw EOD files were located, but no complete admitted normalized analyst history was verified. No genuine comparable analyst estimate vintage pair was published. **Production status remains BUILT_NOT_PROVEN for this offline research helper; no Terminal user-path proof.**


## Corroborated after-close window mode and observed nine-event research replay

The input illustration above describes the **strict exact-first-public-release mode**. The separate weaker mode uses `first_publication_clock_status = "AFTER_CLOSE_WINDOW_CORROBORATED"`, `first_published_utc = null`, explicit `after_close_session`, source-stamped `observed_public_by_utc`, `public_by_source_kind` (issuer wire or press reprint) and two distinct `after_close_evidence_refs`. It must corroborate dissemination **between regular close and next open** and refuses SEC acceptance as sole time evidence. Output states `first_published_utc: null`, with `clock_quality: SESSION_WINDOW_CORROBORATED_EARLIEST_RELEASE_UNKNOWN`. The module validates structural clock consistency but **does not fetch the links or establish true earliest publication itself**. No intraday execution-time inference is permitted.

The nine `sourced_event_packets/*.json` inputs document **three earnings events per issuer**: Alphabet (GOOGL, sector XLC), Microsoft (MSFT, XLK), Amazon (AMZN, XLY), across Jan–Feb, April, and July 2026. Winter session clocks are 14:30–21:00 UTC and spring/summer 13:30–20:00 UTC. Two adjacent retrospective adjusted close prices are supplied for issuer, SPY and sector benchmark. Data references are Yahoo Finance history pages; exact 2-day prices and public release witness links are in each JSON packet. The data are a public research excerpt, not the platform's existing historical data source or normalized source rights grant.

**Single-command machine/human consumer:** run `python3 replay_casebook.py --format markdown` for a nine-row comparative report; use `--format json` for machine-readable typed results. The nine rows have a measured first-session close-to-close reaction; H5/H20 remain **UNESTIMABLE** with two-session price packets. This is no historical predictive alpha test. The adjusted prices are retrospectively restated by providers; sector ETFs may contain the issuer itself and are not factor-neutral or leave-one-out. Vendor/source qualification and historical PIT consensus acceptance remain separate gates.

*Key observed contradiction*: Google Cloud growth accelerated from +63% in April to +82% in July, while GOOGL's first-session stock reaction flipped +9.96% to −7.13%. AWS +28%→+37% accompanied AMZN +0.77%→+15.32%; Azure +40%→+43% accompanied MSFT −3.93%→+15.51%. **These observations do not identify investor psychology or predict a trade**, but show why the earnings-growth metric alone is insufficient.


## First-party management-guidance contrast, distinct from Street consensus

`amazon_management_guidance_cases.json` and `test_management_guidance_cases.py` add two exact issuer-fiscal-target examples from Amazon's first-party earnings releases: Q1 2026 sales $181.5B vs its previously issued $173.5–178.5B range (prior midpoint $176.0B, +3.1250%), and Q2 2026 sales $200.6B vs its prior $194.0–199.0B range (midpoint $196.5B, +2.0865%). Despite *smaller* percentage exceedance of the management midpoint in Q2, the event-date stock return was larger than Q1. The data explicitly label forecast source type `MANAGEMENT_GUIDANCE` and accounting basis `AS_REPORTED_INCLUDES_FOREIGN_EXCHANGE`, with source links and an FX-comparability caution; they are not analyst consensus or a model-estimated market hurdle.

**Hosted CI inclusion:** the repository's enforced test discovery includes `tests/**` only. `tests/test_earnings_reaction_research.py` adds an isolated bridge to the three offline research suites, preserving the existing single `test` check context. A local simulated-repository CI bridge run passed (one wrapper test exercising all 62 research tests); the actual GitHub Actions job must still finish and report its own result.


### Joined guidance + observed-reaction output (source proof)

The read-only `replay_casebook.py` consumer now joins the two Amazon first-party prior-guidance observations to the correct Q1/Q2 stock reactions in **both Markdown and JSON**, with explicit `management_guidance_status` and `management_guidance_comparisons`. This is a typed management-guidance channel, with `point_in_time_analyst_consensus: NOT_ADMITTED`. Validation rejects invalid forecast source/basis, late guidance, mismatched event target or issuer, duplicate targets; missing guidance does not become zero. The five additional focused tests raised the current local count to **67**. When a guidance source is unavailable, returns remain available with an explicit unavailable guidance state. Test count is local; normal hosted CI is separately governed.


### Third evidence channel: media-reported cloud-growth consensus witnesses (NOT admitted PIT inputs)

`media_reported_expectations.json` holds seven small, properly cited numerical excerpts from dated financial reporting (Reuters/LSEG or Visible Alpha), matched to seven of the nine underlying source events; the other two remain absent, not zero. The separate S&P Global/Visible Alpha July 22 Alphabet Q2 preview indicates Q2 revenue consensus increased **$113.0B in February → $117.2B by July**, while EPS consensus fell **$3.43 → $3.32** (the older EPS vintage date is unspecified). Article publication timing or contributor-level vintages are not established as pre-event machine observations.

`replay_casebook.py --format json|markdown` now renders three distinct channels in one evidence response: (1) nine observed next-session adjusted returns; (2) two issuer management-guidance/actual comparisons; (3) seven article-quoted expected-versus-reported cloud-growth comparisons and one source-reported multi-metric revision narrative. The media channel is explicitly `PUBLIC_ARTICLE_WITNESSES_ONLY_NOT_ADMITTED_AS_PIT`, every `consensus_vintage_admitted` is `false`, and exact source links are included. It rejects wrong source authority, duplicate/mismatched fiscal targets, fake pre-event estimate timestamps and preview PIT promotion. **230/230 local research tests passed and the existing CI-discovery bridge exercised the full suite locally.** The article data cannot support backtest forecasting, redistribution beyond lawful quoted numerical facts or new market-belief authority without incumbent source acceptance.

## Read-only bridge to the incumbent EXP-1/K3E owner

The source-owner contract is **not** reimplemented in this research branch. `expectation_owner_adapter.py` consumes a previously produced `engine.k3e_expectation_surface.inspect_expectation_surface()` receipt from Macro, with its `semantic_payload`, `semantic_digest`, `query_identity` and immutable source/input pins. It verifies the owner schema, semantic digest, query identity, source revision, historical/as-of provenance, native identity-gate contract, status and rights. The current owner's `normalized_baseline.value = null` is faithfully projected as `NOT_ADMITTED`, with explanatory reason codes; raw candidate observations and Yahoo snapshots never become a forecast.

Example research-only CLI use after an authorized owner produces a K3E inspection receipt:

```sh
python3 replay_casebook.py --format markdown --owner-inspection /path/to/native_k3e_receipt.json
python3 replay_casebook.py --format json --owner-inspection /path/to/native_k3e_receipt.json
```

The receipt is *optional*. With no receipt, `native_expectation_owner_inspection = null`, not fabricated empty consensus. A requested missing/invalid receipt refuses; a future non-null normalized baseline under the old owner contract also refuses until that new owner contract is deliberately requalified. The bridge intentionally does not map a `ticker_compat` to an issuer's economic identity or bind a free-standing inspection to an event. It cannot grant publication/trading rights, replace MAS-271 qualification, or cause any collector/job changes.

Tests: `test_expectation_owner_adapter.py` exercises digest/input pin/cutoff/rights/refusal cases; `test_owner_inspection_consumer.py` proves Markdown and JSON output and fail-closed source handoff; the existing `tests/test_earnings_reaction_research.py` bridge executes all six research test modules in hosted CI. All **132 local research tests** passed in an isolated M2 Studio checkout of this PR after the bridge changes.

## Tiingo archived-bar inspection — explicit non-admission

An M2 Studio source-census located historical `adjClose` records for GOOGL, GOOG, MSFT, AMZN, SPY, XLC, XLK and XLY, spanning all nine target earnings dates. Their presence is a data-discovery result, **not a historical backtest/redistribution right**. The owner materialization receipt (schema `mastermind.tiingo.materialized_receipt.v1`) inspected during the 2026-10-13/14 research continuation contained these flags:

- `pit_backtest_eligible: false`
- `redistribution_admitted: false`
- `dataos_identity_admitted: false`

`tiingo_manifest_inspection.py` reads an existing receipt **without opening any price file** and returns only bounded, non-sensitive metadata and exact denial codes. It always says `historical_price_admission = NOT_ADMITTED`: even a hypothetical receipt with three true flags cannot silently grant research entitlement or license in a new application. No vendor bars, machine-local paths, blob hashes or source observations are included in GitHub. The rights and identity claims must first be qualified through the incumbent price-data owner.

```sh
python3 replay_casebook.py --format json --tiingo-manifest /path/to/owner_materialization_receipt.json
python3 replay_casebook.py --format markdown --tiingo-manifest /path/to/owner_materialization_receipt.json
```

`test_tiingo_manifest_inspection.py` covers false/malformed/missing flags, a hypothetical three-true source receipt without owner acceptance, no-price-export guarantees and both casebook output formats. The CI bridge includes it. **230/230 research tests passed locally on the isolated M2 Studio checkout** after this addition. This is NOT 132 live-market regression tests and is not a source-license certification.

## Research-ready pre-event windows (source sessions, not market calendar authority)

`reaction_replay.py` now computes three typed, deterministic pre-event anticipation windows `P5`, `P10` and `P20` from the last unaffected regular-session close backwards by exactly the supplied number of sessions, alongside the existing first affected reaction and H5/H20 drift. If the packet lacks full prior prices or enough sessions, each unavailable window records `INSUFFICIENT_PRIOR_SESSIONS`, `MISSING_ISSUER_CLOSE`, `MISSING_MARKET_CLOSE` or `MISSING_SECTOR_CLOSE` as appropriate, not zero or a fabricated trend. Pre-event windows can still be known after an after-close release even when the affected close has not yet occurred. Output includes `calendar_basis: SUPPLIED_SESSION_CLOCKS_NOT_INDEPENDENTLY_EXCHANGE_VERIFIED` because the supplied calendar is not independently authenticated by this helper. The nine currently public two-day case packets correctly have unavailable P5/P10/P20 and H5/H20.

`test_pre_event_windows.py` verifies P5/P10/P20 arithmetic, missing-source handling, no future leakage, no future-session labeling and casebook Markdown display using **synthetic fully populated bars**. A future source owner may supply PIT-qualified adjusted session histories, but the archival Tiingo materialization with false source-eligibility flags remains excluded.

## Company capex-guidance change as a fourth descriptive evidence channel

`alphabet_capex_guidance.json` and `test_capex_guidance_cases.py` reconstruct Alphabet's three FY2026 capex guidance ranges for the February Q4 2025 release ($175–185B), April Q1 2026 earnings call ($180–190B), and July Q2 2026 earnings call ($195–205B). Midpoint revisions were $180B → $185B (**+$5B**) → $200B (**+$15B**). The April company explanation included the Intersect acquisition; July highlighted accelerated infrastructure capacity delivery. Company-linked source and clock-status receipts are attached to each event. The casebook renders the ranges next to the corresponding GOOGL one-session reactions, but **does not** claim company guidance disclosed during an earnings call was known before the release, does not call it an analyst consensus, and does not make it an actionable signal.

Sources: [Alphabet Q4 SEC release](https://www.sec.gov/Archives/edgar/data/1652044/000165204426000012/googexhibit991q42025.htm), [Alphabet Q1 call reported transcript](https://www.fool.com/earnings/call-transcripts/2026/04/29/alphabet-googl-q1-2026-earnings-call-transcript/), [Alphabet Q2 call reported transcript](https://stockanalysis.com/stocks/googl/transcripts/657320-q2-2026/). Separate earnings-press-release versus earnings-call publication clocks remain typed and unknown to the second.

With these two new research families, **230/230 local tests pass**, and the repository's `tests/test_earnings_reaction_research.py` CI bridge runs all twelve in-place suites without introducing a second test scheduler. Hosted CI/review/production adoption are separate proof obligations.

## As-of price visibility: post-cutoff mutations cannot rewrite an earlier replay

Before the October 14 continuation, the replay checked *all* supplied adjusted-close rows before applying the as-of cutoff. A malformed or duplicate row for a future session could therefore turn a previously valid earlier replay into a refusal, even though that future price was not observable at the evaluation instant.

`reaction_replay._bars` now accepts the externally supplied session-calendar close times and `evaluated_asof_utc`. It excludes bars whose regular-session close exceeds that cutoff **before** inspecting their adjusted price values or duplicate records. An unfamiliar bar dated strictly after the cutoff's New York calendar date is likewise ignored; an unmatched past bar remains a hard `BAR_OUTSIDE_EXCHANGE_SESSIONS` refusal. Missingness and invalidity for *observable* sessions are still refused or reported by the original logic. No earlier as-of result can be changed by merely appending an invalid, duplicate or arbitrarily high price to an unobserved future session.

The new `test_future_bar_cutoff.py` adds 21 adversarial regression cases. Their original run failed in 17 cases, demonstrating real code exposure, then passed after the fix; the **230/230 complete offline research suite** and existing `tests/test_earnings_reaction_research.py` CI bridge passed on the isolated M2 worktree. The nine checked-in two-day public casebook packets produced byte-equivalent semantic results before versus after the change.

**Scope:** as-of close visibility is not a license or a guarantee that adjusted prices would have been historically knowable under later dividends/splits. The supplied session calendar is still externally unverified; actual analyst consensus and Tiingo backtest rights are still not admitted. This is a research-label integrity repair, not an alpha validation or live Terminal change.

**Live source-owner receipt proof, October 14:** the existing Tiingo EOD materialization receipt inspected through the checked-in `inspect_tiingo_manifest` function reports 8,455 source rows, but all three PIT-backtest, redistribution and canonical identity flags are `false`; result is `NOT_ADMITTED` with typed reasons. No underlying vendor bar was opened or exported for this check. This confirms that further real P5/H5/H20 observation work is specifically blocked by owner eligibility/rights, not by the mathematics of the replay helper.

## Canonical Earnings OS event identity binding (context only)

The existing Macro canonical owner is `engine.company_intelligence.event_workspace` and its `engine.neuralweb.company_intelligence_reader.read_event_workspace` consumer. That native consumer owns marker -> immutable generation -> hash-verified workspace reads. This research lane does **not** reimplement that reader, mint canonical events as truth, or publish its own event workspace.

`event_workspace_binding.py` derives a *candidate* event identity from a packet's economic CIK and fixed fiscal quarter, then validates it against a **supplied native read_event_workspace envelope**. Examples: `CIK:1652044` / `2026Q2` maps to candidate `evt_cik0001652044_2026q2_results`; `CIK:789019` / `FY2026Q4` maps to candidate `evt_cik0000789019_2026q4_results`. The adapter will not use the current ticker alone as identity.

It requires agreement on native event_id, issuer company_id, fiscal year/quarter, the research price-security alias being in the native issuer's listings, context-only/Prophet-denied authority, generation ID, hashes, and immutable-path receipt structure. A missing owner event is typed `OWNER_EVENT_UNAVAILABLE`. A structurally matching owner-reader envelope yields `IDENTITY_MATCHED_OWNER_READER_RECEIPT_DECLARED`, **not an independent bytes-verification or owner-identity admission**: the native reader must have actually authenticated the envelope. The adapter never follows or fetches the supplied URLs, never writes an event or rank, and does not export any full native workspace.

The existing `replay_casebook.py` can optionally inspect **one explicit research event** and one claimed source-owner receipt:

```sh
python3 replay_casebook.py --format markdown --native-event-ref 'earnings:CIK:1652044:2026Q2' --native-event-workspace /path/to/native_read_event_workspace_receipt.json
python3 replay_casebook.py --format json --native-event-ref 'earnings:CIK:1652044:2026Q2' --native-event-workspace /path/to/native_read_event_workspace_receipt.json
```

A missing event selection, ambiguous/missing cohort event, or mismatched owner payload is a typed refusal, not a best-effort ticker join. `native_event_workspace_binding` is `null` if no owner document is provided. The nine casebook events, source rights, performance labels and existing non-admitted analyst baseline remain unchanged. No live published event workspace was successfully read through the current sparse Macro checkout in this phase; consequently native end-user publication proof remains **unproven**.

`test_event_workspace_binding.py` and `test_event_workspace_consumer.py` add 52 synthetic/contract tests (issuer/quarter collisions, fiscal prefix, dual-class listing, bad generation, non-HTTPS/altered receipt paths, forbidden Prophet authority, wrong event and missing owner). The CI bridge exercises all twelve research suites. **230/230 total offline research tests passed** on the isolated M2 Studio worktree.

### One bounded live-public identity binding check

In a separate October 14 read-only network probe, the public Earnings OS AAPL `event_workspace_manifest.v3` marker was compared to its immutable generation manifest, and the exact AAPL event object was byte-size/SHA-256 checked against its manifest file entry. A minimal research identity packet (`CIK:320193`, `2026Q3`, `AAPL`) was then bound to that verified source payload using `bind_native_event`: status `IDENTITY_MATCHED_OWNER_READER_RECEIPT_DECLARED`, canonical `evt_cik0000320193_2026q3_results`, generation `6ab0665a0783750f665b1b25`. The *probe script* checked bytes, but the offline binder itself correctly continued to set `owner_verified_by_this_helper=false` and `source_owner_identity_admitted=false`. No source owner permission, product install or trade authority was added.

The same immutable generation contains no GOOGL/MSFT/AMZN workspace keys; their public `/api/event-workspace/{ticker}` current-glance queries returned explicit `event_workspace_not_covered` (404). Therefore no live research-target binding or GOOGL Terminal workflow is claimed. This evidence is a bounded owner-compatibility proof, not end-to-end product acceptance.

**Historical owner generation distinction:** the canonical identity adapter now separately reports `historical_event_availability_verified=false` in all cases, and `owner_generation_postdates_research_asof=true|false|null` when an as-of clock can be compared. Even if the current immutable owner generation predates a requested backtest cutoff, the existence of its current marker does *not* verify its historical public availability at that cutoff. Seven new adversarial clock/refusal fixtures extend the offline suite to **230/230** local tests. This prevents a valid current event identity from silently becoming a point-in-time research feature.
