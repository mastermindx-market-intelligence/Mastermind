# Portfolio cohort — architecture and design reasoning

Read-only return to the canvas owner. Pins: Mastermind `1d0579c0540f5281e52faf069dd7dba2f480c7c6`; Macro `b5674d8ef898e503d6164922654f5ff89be9981c`.

## Coverage and limits

Nine files / thirty pages / 317 artboard metadata records were inspected directly. Eight representative Paper screenshots, eleven selected JSX exports and six selected tree summaries were read. This is not 317 visual audits. The JSON companion records every page, exact artboards and depth. No browser, runtime, source-repository or Paper mutation was attempted; only this scratch reasoning report was written. No resource was archived. All inherited uncertain/held effects remain with their original owners.

## Priority findings

### 1. D06: recover completed allocation designs before polishing the migration

`01M6Y1NJ2SKGG89DZ13E4NVAE2 / p-1-0`: `WB-0` contains only the S&P Vector heading and subtitle; the screenshot shows an otherwise empty 1440×900 canvas. `WG-0` contains a mobile status bar and heading only. These are incomplete references, not an allocation workflow.

The current-main [D06 implementation record](https://github.com/mastermindx-market-intelligence/macro/blob/b5674d8ef898e503d6164922654f5ff89be9981c/docs/d06-macro-20261104.md) explains the provenance: a capacity warning stopped the giant source file, and completed replacements superseded `743L-0 / 743M-0 / 743N-0`. The [verified export manifest](https://github.com/mastermindx-market-intelligence/macro/blob/b5674d8ef898e503d6164922654f5ff89be9981c/docs/pr-crops/d06-macro-20261104/paper/manifest.json) names the real completed designs in Terminal `01M3NSZGE8JWN2EZCSF0DT05RM / p-18-0`: `1XGS-0` Stage phone, `1XGT-0` S&P desktop, `1XGU-0` S&P phone.

Minimal repair: label the migrated placeholders incomplete and provide the exact completed destinations and source record; then reconcile/reuse the completed compositions through the parent’s normal exact-target reads. Do not invent allocation data or restore the placeholders as canonical. The completed destination was not re-read by this child; source manifest and current placeholder evidence are established. D06’s current source records and older verification remain historical evidence, not a new browser result here.

### 2. Bot Portfolio: repair stale migration identity and the incomplete builder handoff

`01M6Y3AT0XJBWTM3AVCMBJQ8TE / p-1-0 / 1-0` still lists twelve old `5Z* / 60*` canvas IDs. Footer `2B-0` still directs readers to old file `01M2WGNCX9475G79JRKJTCM08P / p-14-0`. Node `26-0` names a rewritten Opus brief without a usable location.

| Index text node | Current board | Destination |
|---|---|---|
| U-0 | 2C-0 | Today |
| X-0 | 77-0 | Holdings and risk |
| 10-0 | CI-0 | Performance |
| 13-0 | IC-0 | Decisions and orders |
| 16-0 | NS-0 | Opportunities |
| 19-0 | SG-0 | Research |
| 1E-0 | WM-0 | Learn |
| 1H-0 | 11E-0 | Today mobile |
| 1K-0 | 14D-0 | Portfolio mobile |
| 1N-0 | 17U-0 | Today light |
| 1Q-0 | 1CP-0 | Shared self-directed, Chinese 320 |
| 1T-0 | 1EI-0 | State atlas |

Replace visible navigation IDs with these local destinations; keep old-file provenance explicitly historical. Link the existing [architecture freeze](https://github.com/mastermindx-market-intelligence/Mastermind/blob/1d0579c0540f5281e52faf069dd7dba2f480c7c6/docs/superpowers/specs/2026-09-15-mastermind-portfolio-v3-risk-first-autonomous-manager-design.md), [S0 implementation plan](https://github.com/mastermindx-market-intelligence/Mastermind/blob/1d0579c0540f5281e52faf069dd7dba2f480c7c6/docs/superpowers/plans/2026-09-15-mastermind-portfolio-v3-s0-decision-snapshot.md), and [held implementation PR #673](https://github.com/mastermindx-market-intelligence/Mastermind/pull/673). The architecture remains SPEC_ONLY/production-inert; the PR’s current body reports a bounded read-only Decision Snapshot implementation, not a generally operating V3 manager.

The Today screenshot already distinguishes held cash, accepted target, queued work and settlement, with an explicit illustrative-data label. Preserve that. A new visual redesign is lower value than restoring the builder and navigation mapping.

### 3. Source labels need real, qualified destinations

Inspected JSX commonly exports styled labels without URLs. A blue or underlined label is not a proven link. Parent separately owns testing the supported Paper link mechanism.

| Exact target | Minimal source connection |
|---|---|
| PROPHET `10NB-0 / 10QQ-0`, p-D-0 | [D03 Phase 2A](https://github.com/mastermindx-market-intelligence/macro/blob/2e59365eeae7c5ba9e60e274e03dac83aacbebdc/research/design_candidates/production_design_20261102/D03_US_PROPHET_PHASE_2A.md). This exists at draft PR #10617 head, not inspected protected main. Keep draft qualification and ZE5-0/original Fabric uncertainty fences. |
| Terminal Options `16B-0`, p-3-0 | [D08 integration handoff](https://github.com/mastermindx-market-intelligence/macro/blob/2e59365eeae7c5ba9e60e274e03dac83aacbebdc/research/design_candidates/production_design_20261102/handoffs/D08-options.md). Pair with current owner files; its historical route census is not proof of today’s independent routes. |
| Separate Options mobile `1-0` | Owning desktop file `01M5EPQ16VBT7SBW2NQVX2RJG4`: p-2-0 W3, p-3-0 build, p-4-0 user help; same D08 guide. |
| Expectation `3UR-0 / QK-0`, p-2-0 | [Builder](https://github.com/mastermindx-market-intelligence/macro/blob/b5674d8ef898e503d6164922654f5ff89be9981c/scripts/build_expectation_surface.py), [template](https://github.com/mastermindx-market-intelligence/macro/blob/b5674d8ef898e503d6164922654f5ff89be9981c/templates/expectation_surface.html.j2), [existing UI evidence](https://github.com/mastermindx-market-intelligence/macro/blob/b5674d8ef898e503d6164922654f5ff89be9981c/research/alpha_intelligence/expectation_market_dynamics/EXPECTATION_SURFACE_UI_EVIDENCE_2026-10-21.md). |
| Market Memory `V1-0`, p-3-0 | [Authenticated shell builder](https://github.com/mastermindx-market-intelligence/macro/blob/b5674d8ef898e503d6164922654f5ff89be9981c/scripts/build_market_memory_page.py), [template](https://github.com/mastermindx-market-intelligence/macro/blob/b5674d8ef898e503d6164922654f5ff89be9981c/templates/market_memory.html.j2), [qualified draft D12 guide](https://github.com/mastermindx-market-intelligence/macro/blob/2e59365eeae7c5ba9e60e274e03dac83aacbebdc/research/design_candidates/production_design_20261102/handoffs/D12-memory.md). The guide’s old Paper destination is provenance, not the migrated current location. |
| Policy `MH-0 / RE-0`, p-2-0 | [Candidate upgrade record](https://github.com/mastermindx-market-intelligence/macro/blob/c742039f32d3ae73b557b8b2b5f6ff4df36b23c2/research/policy_monitor/POLICY_MONITOR_UPGRADE_2026-11-01.md) and [candidate numeric-disclosure template](https://github.com/mastermindx-market-intelligence/macro/blob/c742039f32d3ae73b557b8b2b5f6ff4df36b23c2/templates/_policy_monitor_dialog.html.j2), PR #10493. These two paths return 404 at inspected protected Macro b5674d8; do not imply merged/main capability. |
| Options Research Desk `U9-0`, p-1-0 | [Canonical options template](https://github.com/mastermindx-market-intelligence/macro/blob/b5674d8ef898e503d6164922654f5ff89be9981c/templates/options.html.j2), [existing workspace spec](https://github.com/mastermindx-market-intelligence/macro/blob/b5674d8ef898e503d6164922654f5ff89be9981c/research/options_estate/WORKSPACE_DESIGN_SPEC.md), and draft D08 guide. Retain current doctrine when older guide styling differs. |

The current-main `templates/gex.html.j2` and `templates/options_screener.html.j2` are moved-page redirects to `options.html#ticker` and `options.html#scanner`. Do not build separate new desks from old route-census descriptions. The migrated Research Desk’s current five-destination design must connect through the actual canonical Options owners.

## Already solved well: preserve, link, and verify implementation

- **PROPHET:** `10NB-0` already states eight unresolved interfaces, current draft lineage, source-only baseline, D23 save ownership and no newly approved reference. Keep rejected p-B-0 visibly rejected; p-A-0, p-7-0, p-8-0, p-4-0 remain useful rich-card/evidence/quote/screener references. No cosmetic replacement of uncertain `ZE5-0`.
- **Terminal Options:** `16B-0` and `16E-0` already specify coherent origin adoption, explicit unchanged/changed/unavailable identities, side-unknown totals, corrections/cancellations, unconfirmed legs, no volatility extrapolation, separate IV/spot clocks and receipt/revision boundaries. These are valuable current contracts, not prose to discard wholesale.
- **Expectation:** recent build work already identifies the denominator and state-restoration gaps. Current main confirms the template still claims matched-only counts while the builder calculates comparable observations before projecting identity; `_comparable_pairs` preserves same-key previous-valid pairing and equal known fiscal period. URL restoration is still ticker-only `?t=...#es-explorer`. Keep the P0/P1 implementation work; do not repeat the design repair. The current mobile screenshot is concise and its show-all/numeric-depth pattern is useful.
- **Market Memory:** `MX-0` correctly withholds the difference despite showing retained 111.5/111.4 values, because units/basis are not established. `V1-0` already distinguishes missing values, access, incomplete scan, source change, incompatible basis, true zero, and definitive version unavailability. Preserve original operands, day-precision vintages and unspecified cutoff.
- **Policy Monitor:** the mobile screenshot preserves dated narrative, unverified technical inputs, unavailable Fed guidance, missing projection comparison and separate coverage. The build contract already gives real anchors, native disclosure, focus return and exact chart/table parity. Connect the candidate source, without converting candidate evidence into current-main or served proof.
- **Options Research Desk:** the mobile view correctly distinguishes the selected completed session from older Brief/Flow/Scanner/Leaders dates. Preserve the per-index dates, source detail and clear Terminal destination; do not hide stale context or manufacture one freshness/stance score.

## Required states and meaningful implementation proof

| Family | Required verification |
|---|---|
| PROPHET | Ready/wait/unjudgeable, absent vs failed source, quote vs assessment vs plan clocks, exact candidate occurrence, insufficient compare selection, save pending/refused/unknown/readback, no invented entry authority. |
| Terminal Options | Qualified origin adoption and Back/Forward, missing selected company, unknown hash, no comparison without common contracts, correction/cancellation lineage, side-unknown retained totals, missing wing/spot, stale vol, unsupported watch kind, no price, revoked entitlement, manual one-shot re-arm, immutable receipt and assessment revision. Quote-observed and receipt-source timestamps must come from their distinct actual owner fields; the mobile fixture alone is not runtime proof. |
| Expectation | First capture, fiscal rollover, zero prior, aliases unavailable, missing observations, out-of-order fetches, selected tuple restoration, full source list reveal, exact numeric values, EN/ZH/theme parity. |
| Market Memory | Both exact operands and source version retained; offset/version through incomplete lookup; missing vs zero; unit/basis qualification before subtraction; access vs unavailable vs fingerprint mismatch; copy full provenance and exact return/focus. |
| Policy | Fully absent payload vs present unusable data, missing horizon gaps, dated commentary, unknown vs zero activity counts, shared access owner, keyboard section focus, native chart-value disclosure and dialog return. |
| Options Research Desk | Independent module clocks, current vs earlier completed sessions, missing Brief with useful dealer sibling data, unavailable pricing/expiry/spot, source-scoped retries, stable ticker/expiry/session on Terminal handoff. |
| D06 | Restore complete proven design lineage; preserve missing chart slots and true zero, independent Stage readers and failed-file retry, model/shadow separation, contributing clocks, analytical depth and inherited release holds. |
| Bot Portfolio | Bound book/currency/FX/marks snapshot, held vs accepted vs settled, stale/partial marks, owner change, unavailable return history, immutable correction and no duplicate order effect; do not equate S0 read-only capability with V3 target/execution authority. |

## Every cohort page: disposition and depth

`current` below means current inspected design location, not approved production authority. `reference` does not authorize archival or deletion. No page was declared archived. A node-specific uncertain-effect hold is recorded on PROPHET p-C-0.

| Family | Page | Disposition | Inspection depth |
|---|---|---|---|
| PROPHET | `p-D-0` · 00 · Start here · D03 build contract · DRAFT | current | Selected full JSX/text inspection |
| PROPHET | `p-C-0` · 01 · Opportunity studies · R7–R8 · DRAFT | current — ZE5-0 held | Metadata only |
| PROPHET | `p-E-0` · Build · Clarity preservation | reference | Selected tree/structure inspection |
| PROPHET | `p-1-0` · PROPHET | reference | Metadata only |
| PROPHET | `p-B-0` · REF · REJECTED · R6 text-row direction · R1–R4 | reference | Metadata only |
| PROPHET | `p-A-0` · 07 · R6 successor · Opportunity workspace · DRAFT | reference | Metadata only |
| PROPHET | `p-9-0` · 06 · R6 · Flagship candidate · Design draft | reference | Metadata only |
| PROPHET | `p-8-0` · REF · Prophet Quote + Assessment Reviews · R4.0–4.4 | reference | Metadata only |
| PROPHET | `p-7-0` · REF · Prophet Setup, Evidence + Playbooks · R3.1–3.9 | reference | Metadata only |
| PROPHET | `p-6-0` · 05 · SOURCE ONLY · Prophet US Live Baseline | reference | Metadata only |
| PROPHET | `p-5-0` · 04 · Shared Contracts + State Coverage | reference | Metadata only |
| PROPHET | `p-4-0` · 03 · Screener · Table, Grid + Compare | reference | Metadata only |
| PROPHET | `p-3-0` · 02 · R2 · Today, Setup + Plans | reference | Metadata only |
| PROPHET | `p-2-1` · 01 · Regional · Hong Kong + Canada | reference | Metadata only |
| Terminal Options | `p-1-0` · W1 · Sector origin → Exposure → Change · 2026-10-21 | current | Representative screenshot + content where listed; 1-0 |
| Terminal Options | `p-4-0` · User help · Methods & behavior | reference | Selected full JSX/text inspection |
| Terminal Options | `p-3-0` · Build · Origin & interaction contracts | reference | Selected full JSX/text inspection |
| Terminal Options | `p-2-0` · W3 · Flow → Volatility → Watch & review · 2026-10-21 | current | Metadata only |
| Options mobile | `p-1-0` · U08 · Watch & review · Mobile study | current | Representative screenshot + content where listed; 1-0 |
| Expectation | `p-1-0` · 00 · Start · Estimate revisions | current | Representative screenshot + content where listed; 2NZ-0 |
| Expectation | `p-3-0` · 01 · Study · Coverage + methods | current | Selected full JSX/text inspection |
| Expectation | `p-2-0` · 02 · Build · States + implementation | reference | Selected full JSX/text inspection |
| Market Memory | `p-1-0` · 01 · Revision evidence · Screens & states | current | Metadata only |
| Market Memory | `p-3-0` · Build · Record states & implementation | reference | Selected full JSX/text inspection |
| Market Memory | `p-2-0` · 02 · Record comparison · Proposed | current | Representative screenshot + content where listed; MX-0 |
| Policy Monitor | `p-1-0` · 01 · Policy Monitor · Implementation & states | current | Representative screenshot + content where listed; AQ-0 |
| Policy Monitor | `p-2-0` · Build · Evidence states & interaction | reference | Selected full JSX/text inspection |
| Bot Portfolio | `p-1-0` · Bot Paper Portfolio · V3 Upgrade · 2026-10-09 | current | Representative screenshot + content where listed; 2C-0 |
| D06 | `p-1-0` · D06 - Market structure, stages and model allocation - R1 | current | Representative screenshot + content where listed; WB-0 |
| Options Research Desk | `p-1-0` · Options · Research Desk · R1 · 2026-11-02 | current | Representative screenshot + content where listed; 6D-0 |

Full file IDs, current artboard mapping, inspection node lists, source read outcomes and qualification notes are in `portfolio-cohort-architecture-review.json`.

## Stop boundary

Parent owns all canvas edits, canonical documentation changes and any follow-up acceptance. This bounded cohort review is complete. The prior browser denial remains fenced; no browser attempt, runtime action or external mutation was made.
