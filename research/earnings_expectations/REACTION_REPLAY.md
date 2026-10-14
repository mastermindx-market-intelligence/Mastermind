# Deterministic earnings event reaction replay — research-only

**Source:** `reaction_replay.py` · **Consumer:** `replay_casebook.py` · **Tests:** `test_reaction_replay.py`, `test_replay_casebook.py` · **Real SEC acceptance evidence:** `sec_acceptance_2026.json` · **Nine source packets:** `sourced_event_packets/`.  
**Owner/carrier:** additive research tooling within Mastermind PR #1407, not a replacement for the Macro Earnings/Event, Alpha MAS-118/MAS-271, Prophet, or `scripts/backtest_event_priors.py` owner. No production/data-collection/publishing authority.

## Delivered machine capability

Given an economic issuer/fiscal event, either **verified earliest publicly available earnings-release timestamp** or an explicitly weaker **corroborated after-close public-release window**, explicit exchange regular-session clocks and split-/dividend-adjusted issuer/market/sector closes, report first-session issuer, stock-minus-market and stock-minus-sector returns; plus H5/H20 drift from the *first affected regular-session close*. Decimal return 0.02 = 2%.

Refuse or preserve typed absence for intraday-close contamination, exact regular-close boundary, missing price bars, absent source or adjustment, unobserved as-of date, missing calendar, incomplete horizon, invalid/duplicate sessions, nonfinite prices and unverified release time. A modeled H5 is descriptive, *not* an executable fill.

### Run offline

```sh
cd research/earnings_expectations
python3 -m pytest -q test_reaction_replay.py test_replay_casebook.py
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

**59/59 offline tests passed** with Python 3.13 / pytest 9. Code and tests were verified by Git blob against tested local sources. Tests include after-close, premarket, intraday, weekend, UTC winter/summer clocks, missing benchmark, cutoff leakage, unsupported sources, and refusal to accept an SEC-only clock. Synthetic structural fixtures are supplemented with **nine actual retrospective adjusted-close source packets**, independently checked for arithmetic; this does not prove data licensing, current vendor freshness, a live backtest, causal attribution, or Terminal operation.

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
