# C17 — one typed CPI release bundle

Partial MAS-264 dossier and MAS-273/H06 qualification. Verdict: **incumbent actual/forecast surfaces exist; economist consensus and an integrated event-reader path are not proven**.

## Original research and retained thesis

Preserve [C17, Mastermind #1234](https://github.com/mastermindx-market-intelligence/Mastermind/tree/7b92c866ddb20fc9f6e204c5c47edfeac1704f8b/research/commissions/commission_17_macro_expectations), head `7b92c866ddb20fc9f6e204c5c47edfeac1704f8b`, including `MASTERPLAN.md`, `AUDIT_AND_ACCEPTANCE.md` and `EVIDENCE_REGISTER.md`.

Retain the first CPI/payroll MRI qualification waves and their typed target/revision semantics. Survey consensus, disagreement, model nowcast and market pricing answer different questions. An official revision delta is not a revision surprise without a pre-release expected revision. FOMC/RIC pricing expansion is a separately qualified wave, not a prerequisite for the narrow CPI bundle.

## Current-source recensus and exact seams

All source below is Macro `9201f1602bfe47e05a63d61802fbed6f7f55a19d`.

| Existing surface | Observed contract and integration consequence |
|---|---|
| [`engine/release_actuals.py`](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/engine/release_actuals.py#L378), `normalize_publication`, `reconcile_receipts`, `canonical_actual` | Official host/parser/unit/hash/readiness qualification produces `release_actual.v1`, first-sequence target, official URL/hash and source-release/observation/verification clocks. Later same-key correction candidates retain ancestry and disable automatic scoring. Preserve first print rather than replace it. |
| [`engine/release_target_truth.py`](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/engine/release_target_truth.py#L194), `reconstruct_release_target` | Constructs a same-vintage level-based CPI target and labels the rounded value a proxy, not the official release. Date-scoped vintage selection cannot establish intraday availability. |
| [`scripts/build_release_forecast.py`](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/scripts/build_release_forecast.py#L4300), `build` | Assembles `release_forecast.v2` with an `upcoming` array, `display_only=true`, all-false score/size/trade authority, and `street_consensus=unavailable`. Latest artifact is `data/release_forecast/latest.json`; display copy is `site/macrodata/release_forecast.json`. |
| [`engine/release_market_context.py`](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/engine/release_market_context.py#L605), `compute_expectation_read` | Compares a model point to a median of available Cleveland nowcast, Kalshi and Polymarket inputs. This is display-only mixed-benchmark context, not economist consensus. |
| [`engine/event_window.py`](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/engine/event_window.py#L481), `_read_mri_surprise_dispersion` | Looks at `site/release_forecast/latest.json` and requires a top-level uppercase release section. That differs from the inspected producer's path and envelope. This bounded reader is display-only. |

RIC remains a separate owner for futures-implied policy context. Neither daily futures means nor risk-premium-containing pricing are substitutes for a CPI economist poll. No new macro regime engine or universal expectation score is proposed.

## Executed synthetic compatibility evidence

[probe_mri_compatibility.py](probe_mri_compatibility.py) verifies both supplied source files against fixed SHA-256 digests **before AST parsing or execution**. It then extracts only the producer's exact `latest` dictionary assignment, `_SITE_RELPATH` constant, and the exact reader function. Upstream values are explicitly synthetic. The probe executes no module top-level, full producer, collector or runtime pipeline, and makes no network calls. All data files and injected `lib.config.ROOT` are temporary; the prior module binding is restored.

Exact evidence is [SYNTHETIC_MRI_RECEIPT.json](SYNTHETIC_MRI_RECEIPT.json), `classification=assembly_only_synthetic_proof`, `passed=true`:

| Case | Observed result | Bounded conclusion |
|---|---|---|
| Exact producer assembly at extracted producer display path | Reader returns `None` | The reader does not look at that path |
| Same assembled payload placed at the reader's expected path | Reader returns `None` | Correcting the path alone does not resolve the envelope mismatch |
| Reader's own expected CPI shape at its expected path | Exact positive result with sigma `0.31`, spread `1.2` and synthetic expectation tag | Function extraction/config injection can reach and parse the intended positive branch |

Reader source SHA-256: `8757c8728b9ca566d2303853da69572c74a7ace61e1d810d66cbbb2f837581ae`, Git blob `55571a389c5f65d4a5aeb2a7051ab63bdd77796e`. Producer SHA-256: `5f3448c442481592940b314e6db4ce4b9994edc4b1c9d4446445bc81ee3ef0ec`, Git blob `35f8a1f29f8ae1986a9853683337e0752327f32b`.

Reproduce using the exact source files:

```sh
python3 probe_mri_compatibility.py --reader /absolute/path/to/event_window.py --producer /absolute/path/to/build_release_forecast.py
```

The native helper developed the isolated probe; the Program CEO inspected the actual producer assembly and reader, added byte-exact hash checking/failing-assertion exit behavior, and independently ran the published version. This establishes source assembly/read incompatibility for synthetic upstream inputs. It does **not** establish an actual served/deployed failure, absence of an external compatibility adapter, event-time availability, unit compatibility, or full producer integration. The positive control proves field extraction, not statistical meaning.

## Dispositions and bundle contract

| Disposition | Integration ruling |
|---|---|
| **RETAIN** | Existing MRI official-first actual receipts, correction ancestry, same-vintage proxy distinction, deterministic calculations and display-only authority. |
| **CORRECT evidence strength** | C17's static event-reader compatibility concern now has a reproducible assembly-only synthetic witness for separate path and shape mismatches. Real deployed behavior remains untested. |
| **CORRECT** | Legacy `expectation_read` is model-versus-mixed-benchmark context; its label is not an economist-consensus receipt. No silent in-place semantic rename is authorized. |
| **SUPERSEDE, scope only** | Any H06 packet that treats FOMC/RIC or paid survey expansion as required for the first CPI qualification. Those remain separately gated. |
| **REJECT** | A reconstructed same-vintage proxy relabeled official first print; intraday eligibility inferred from a date-only vintage; revision surprise without expected revision; pricing/nowcast substituted for poll consensus. |

The bounded answer should keep `official_first_actual`, official correction/revision, economist consensus, model nowcast and prediction-market/pricing observations typed separately, with their own target, unit, clocks and generation. These are explanatory roles, not new canonical schema names. Compute actual-versus-locked-consensus only with matching target/period/unit and a lawful pre-event lock. Otherwise return no admissible baseline. Actual-minus-nowcast may be a separately named comparison, never relabeled consensus surprise.

## Next implementation slice and acceptance

Reconcile exact MRI/event-window writer custody and existing compatibility candidates before changing source. First establish the intended canonical path/envelope and a full producer-fixture-to-reader test; do not fix only the path and call E01 complete. Preserve native versus standardized sigma semantics, and select the exact intended CPI target rather than the first conveniently matching item. A source fixture still does not establish real served consumption.

Then qualify one real permitted CPI bundle with receipt-generation and cutoff proof. Required refusals preserve the original C17 acceptance catalogue:

- Mismatched target, unit or period cannot produce numeric surprise.
- Missing pre-event economist baseline returns unavailable; absent, stale and rights-blocked remain separate.
- Date-only vintages cannot prove intraday eligibility; a later append must not alter a sealed earlier selection/digest.
- Original first print and later correction remain replayable without overwriting history.
- Revision delta without expected revision does not become revision surprise.
- A fresh producer with a stale reader is not integrated operational success.
- No corrected packet changes score/gate/rank/size/trade authority in this slice.

## Procurement, unknowns, falsifiers and supersession

No new feed is needed for the compatibility probe, and no vendor was contacted or bought. Qualified economist consensus entitlement, retention/correction terms, total cost, event-time coverage, actual source versions, natural-time consumer proof and incremental predictive value remain **UNKNOWN/NOT_TESTED**. Applicable rights must be resolved per source and use; public technical access is not blanket permission.

Falsifier of the compatibility concern: an exact current source or deployed compatibility path showing the actual producer generation reaches the intended reader with compatible target/unit/shape. Reconcile and reuse it if present. Defer a numeric consensus surprise while its baseline is absent; that null is preferable to semantic substitution.

Preserve C17 unchanged. This dossier advances only the named source-compatibility evidence and integration boundaries. It does not close MAS-273, admit new data, establish empirical value or authorize production changes.
