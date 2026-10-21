# Canonical product/readiness census — Earnings Expectations research

**Observed:** October 14, 2026 (US Pacific session; public sources observed overnight UTC). **Scope:** bounded read-only source/production checks supporting Mastermind earnings expectations PR #1407. This memo is implementation evidence, not production release acceptance.

## Three independent owner gates

| Capability / owner | Tested fact | Production implication |
|---|---|---|
| Existing Macro K3E/EXP-1 expectation source | Real native K3E source **software** was invoked with its own synthetic record fixture: structurally supported EPS 2.5, but normalized baseline **null**, status `UNESTIMABLE`, with rights and issuer/basis/period semantics unadmitted. | No normalized historical sell-side expectation vintage pair; media-reported post-event numbers and company guidance cannot substitute for it |
| Existing Tiingo price-data owner | A real source-owner EOD materialization receipt reported 8,455 rows but **all three** `pit_backtest_eligible`, `redistribution_admitted`, `dataos_identity_admitted` flags were `false`. `inspect_tiingo_manifest` returned `NOT_ADMITTED` with typed denial reasons. No vendor bars copied. | Do not calculate/source-admit historical P5/P10/P20 or H5/H20 from that archive until the owner qualifies licensed, PIT-compatible price data |
| Canonical Earnings Intelligence OS publisher and reader | Public current-event `GET /api/event-workspace/AAPL` returned HTTP 200, schema `event_workspace_public_glance.v1`, canonical `evt_cik0000320193_2026q3_results`, owner generation `6ab0665a0783750f665b1b25`. The same public endpoint returned explicit 404 `event_workspace_not_covered` for GOOGL, MSFT, AMZN. | No verified currently published product glance for the three research issuers. This is current-generation coverage, not proof about all historical generations or internal dossiers |

## Source-owner immutable manifest cross-check

Direct read-only GET of the existing public R2 marker `https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev/company_intelligence/event_workspaces/manifest.json` returned HTTP 200 and **`event_workspace_manifest.v3`**, generation `6ab0665a0783750f665b1b25`, `event_count=5` and five workspace-file keys. The marker and corresponding immutable generation manifest had identical canonical JSON bytes. None of those five keys contained the CIKs for Alphabet `0001652044`, Microsoft `0000789019`, or Amazon `0001018724`. One key contained Apple `0000320193`.

The AAPL `event_workspace.v1` object at that exact generation was fetched once; its **byte length** and **SHA-256** matched the generation-manifest declaration, with event identity `evt_cik0000320193_2026q3_results` and `authority=context_only`. This verifies one bounded marker/immutable/object chain through its observed bytes. It does not establish an authorized account's authenticated Terminal journey or any availability for the three absent issuers. It also does not grant source approval to the research adapter.

## Why this matters for the research PR

The original research packet names `CIK:1652044` and `2026Q2`; the canonical event native identity is `evt_cik0001652044_2026q2_results`. Research labels must not quietly mint a second event. The new `event_workspace_binding.py` uses these values only as a **candidate**. It requires the *existing owner reader* to supply an explicitly matching and context-only event workspace plus immutable-generation receipt. It cannot independently authenticate the supplied raw bytes, so its result clearly states `owner_verified_by_this_helper=false` and `source_owner_identity_admitted=false`.

Current public coverage fails for all three research issuers. Therefore a user-facing Terminal integration that purports to show canonical GOOGL/MSFT/AMZN 2026 event workspace citations would be **premature**. A non-canonical parallel event store/score would be worse. The research casebook still functions as an explicitly retrospective, research-only CLI with nine observed next-session returns and synthetic P/H windows.

## Exact next bounded producer/consumer sequence

1. Existing Earnings OS event publisher qualifies and publishes one canonical issuer event (first candidate: `evt_cik0001652044_2026q2_results`) through its current marker-last immutable workspace process, preserving real document and event identity, correction lineage, source rights and `context_only` flags. No work in this PR may duplicate that producer.
2. Independently verify that the native `read_event_workspace({event_id: ...})` returns the same published generation, then verify the existing `/api/event-workspace/GOOGL` and actual Terminal/dossier user path. The public glance alone strips the original receipt and is not suitable input to `--native-event-workspace`.
3. In parallel, C19 MAS-271/Alpha SRC-A1/EXP-1 qualifies an actual rights-bearing issuer/quarter/metric/two-vintage expectation pair or issues typed noncomparability. Preserve `NOT_ADMITTED` until then.
4. Price-data owner qualifies admissible historical adjusted market/sector/issuer close histories (or another licensed provider) and calendar provenance. Only after that execute pre-registered P5/P10/P20 and H5/H20 evaluations with a representative chronological holdout.
5. Earnings OS/Terminal consumer can then add grounded multi-factor expectations, company guidance, capex and market-reaction explanations without creating a separate publication plane, universal market-belief score, or Prophet sizing/gate authority.

**What has not happened:** No license upgrade, archived-bar export, source-owner normalization, external production write, Terminal feature deployment, profitable-prediction validation, or claim of independent PR approval.

## Actual public AAPL owner receipt through the new research binder

A separate read-only probe fetched the public `event_workspace_manifest.v3` marker, compared its canonical content with the immutable generation manifest, fetched the listed AAPL `event_workspace.v1` object, and confirmed byte-length plus SHA-256 equality with the immutable file entry. It then constructed a minimal **in-memory** CIK/fiscal-quarter/ticker research input and a receipt carrying those inspected source hashes. `bind_native_event()` returned `IDENTITY_MATCHED_OWNER_READER_RECEIPT_DECLARED` for `evt_cik0000320193_2026q3_results`, generation `6ab0665a0783750f665b1b25`. Its output correctly retained `owner_verified_by_this_helper=false`, `source_owner_identity_admitted=false`; the one-off probe script, not the binder, performed the external-byte checks. No raw workspace or R2 object was committed.

This is read-only proof for **AAPL only**. It does not make GOOGL/MSFT/AMZN currently covered, qualify historical consensus/price rights, or establish a live Terminal user workflow.

**Temporal admission hardening:** the read-only event binding now explicitly distinguishes current owner identity from historical availability: `historical_event_availability_verified=false` always, with `owner_generation_postdates_research_asof` when the current generation and research cutoff can be compared. Future generations cannot be treated as features known before publication; earlier generations still need independently proven historical availability. The updated 230-case research suite passed locally. No new production owner receipt was issued by this change.
