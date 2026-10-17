# Commission 14 — completed hardening audit

**Date:** 4 October 2026 UTC. **Disposition:** research complete; recommendation ready for owner review. Production implementation, data procurement, portfolio changes and authority promotion have not been performed or accepted by this audit.

The full deliverable is [Issuer Credit & Capital-Cost Intelligence](ISSUER_CREDIT_CAPITAL_COST_MASTERPLAN_2026-10-04.md). This audit records how the attached draft was challenged and how the resulting recommendation changed. “Resolved” below means resolved in the research and future handoff; source defects remain in the existing production code unless an independently accepted implementation later repairs them.

## 1. Input and source custody

The supplied draft, `deep-research-report (11).md`, contained 8,574 words / 1,219 lines. Its SHA-256 is `5f8d92a7279667f30998a52aae7a4bfafe1ff881e04c4572f65a7481d349c45c`. The original was read and preserved. This package is a newly completed hardened commission.

| Estate | Exact source snapshot | Final protected source recheck |
|---|---|---|
| Mastermind | `a2646f458f9ff41ddcedd89b338be4a4349e6cd6` | `521720b09be2921e996d9396b522b1c4ca62041c` |
| Macro | `d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3` | `59a0789c0e5ffcce15e682b6f3880f3eacc6f6fc` |
| Terminal | `1c708450187755160e1a5889b69598a2fcb1f0d1` | Same |

Repository identities were resolved to `mastermindx-market-intelligence/Mastermind`, `mastermindx-market-intelligence/macro` and `mastermindx-market-intelligence/mastermind-terminal`. Research Vault is the existing Macro estate. The original commission header's `d1594f3...` was not used as current source truth.

Current Mastermind bootstrap and required source law were read. The canonical source workspace was acquired with operation `commission14-credit-hardening-20261004` and branch `sol/web-commission14-credit-hardening-20261004`. The publication footprint is exclusively this research directory. No protected-branch write, production pipeline run, data purchase or external message was part of the commission.

The evidence packet records 41 Macro source artifacts, 12 original Mastermind source artifacts, the Terminal overview, and the relevant section of the newly merged Mastermind Trend C1 preregistration, in addition to the bootstrap/source-law reads. The [source evidence](SOURCE_EVIDENCE.json) and [Macro manifest](MACRO_SOURCE_EVIDENCE.json) retain exact blobs, paths and limitations. Source links remain at the revision actually inspected; they are not relabeled as fresh fetches.

Complete final revision comparisons found one new Mastermind commit and two new Macro commits, with no changed file among the inspected credit/financing/identity/portfolio/source-law paths. Mastermind added Trend C1 preregistration. Macro changed China THS collection/CI and Trend records. A narrow review found no CCW, Capital Structure or F09 CI change and no W2/W3/W4 gate release. See [Macro final-head delta](MACRO_FINAL_HEAD_DELTA.json). Current CI must nevertheless be repinned by a later implementation owner.

## 2. Material finding disposition

Severity describes the risk to the research recommendation if the issue were left unresolved. It is not a live incident classification.

| ID | Severity | Finding | Research disposition / remaining implementation boundary |
|---|---|---|---|
| C14-01 | Critical | Existing canonical credit/capital-structure program and CCW alias were insufficiently reconciled | A/B/G/L now extend `capital-structure-intelligence`; no competing owner or snapshot |
| C14-02 | High | CCW already computes issuer bond YTM/g-spread and aggregated series | Census corrected; qualify existing source/measurement/history before buying or building another feed |
| C14-03 | Critical | A fund-held maturity wall measures sampled par, not issuer principal outstanding | E/F require distinct types/perimeters; refinancing calculations cannot consume the former as liabilities |
| C14-04 | Critical | Pure debt extractor chooses a later filing despite an earlier cutoff | Executed falsifier documented; P0A demonstrates an opt-in eligible-input adapter; legacy callers remain unmodified |
| C14-05 | High | Downstream future-filing rejection cannot recover an older discarded fact | Future adapter selects eligible source versions before calculation; missing clocks quarantine historical claims |
| C14-06 | Critical | Candidate registration terms can be confused with resolved debt instruments | Existing W2B/W3A semantics made explicit; shelf/registered amount is not issuance, capacity or debt |
| C14-07 | High | Current mappings and first-match names do not prove historical obligor identity | Data OS remains owner; historical relations require evidence and explicit gaps |
| C14-08 | High | Retention, direct-term extraction and candidate compilation have different clocks | E2 names each incumbent field and chronology; L adds a late-candidate fixture |
| C14-09 | High | Source PASS/health and committed dates could overstate current readiness | Separate discovery, retention, extraction coverage, generated output and consumer freshness |
| C14-10 | Critical | A directional context row can enter confluence; held-risk proxy replacement changes severity | Initial context stays outside reducers; consumer invariance and later accepted policy diff required |
| C14-11 | High | Existing V3 specification and snapshot names are not proof of complete live implementation | Reuse existing family/snapshot owner; no duplicate controller or unproved live claim |
| C14-12 | High | TRACE reporting, dissemination and delayed enriched fields have different availability | Current June 2026 regime, allocation/cap/lifecycle/field clocks and product splits documented |
| C14-13 | High | Current Companyfacts/Frames cannot supply assumed historical vintages | Accession/retained-generation evidence required; dimensional/custom debt terms acknowledged |
| C14-14 | High | Vendor long history is not original PIT history | S&P PIT metadata and LSEG recomputation/backfill warning preserved; sample proof and rights remain prerequisites |
| C14-15 | Critical | Bond-implied CDS or multiple transforms can be counted as independent information | Source ancestry and `balance_sheet_credit` independence boundary made explicit |
| C14-16 | High | CDS transactions are not a ready daily spread curve | Applicable payment, lifecycle, scope and timing requirements added; missing terms are not zero |
| C14-17 | High | Older lead-lag literature lacked a current conditional replication target | Added July 2026 paper abstract and OFR/NY Fed work; original rejection of universal leadership retained |
| C14-18 | High | Simple annual rate delta omits time, principal, reset, hedge and accounting effects | Period cash-interest bridge, feasibility states and checked examples replace a universal formula |
| C14-19 | High | Coverage/FCF/tax/valuation conventions can double count financing | Explicit cash/accrual, operating/financing, tax-shield and valuation-convention treatment |
| C14-20 | High | Covenant capacity can become false precision | Contract definition, adjustments, timing and conditional liquidity required; unknown remains unknown |
| C14-21 | Critical | Paid market layer can inherit gains from disclosed accounting terms | Matched B0/B1/B2 comparisons separate foundation from market-credit incremental value |
| C14-22 | High | Valid-row percentages and small engineering samples can masquerade as empirical proof | Every admitted row valid; coverage separate; clustered power/MDE and inconclusive state required |
| C14-23 | High | Full-sample residualization, immature labels and overlapping outcomes can leak | Past-only fitting, matured-label clocks, chronological holdout and issuer/date dependence specified |
| C14-24 | High | Failure can remove cash-interest labels and bias survivor forecasts | Informative-censoring/competing-failure audit and bounds added; stopped interest after default is not improvement |
| C14-25 | Medium | Reverse equity-to-credit predictability alone does not refute incremental credit value | H6 now allows bidirectional information; the conditional B2 increment is decisive |
| C14-26 | High | A broad P0 build could exceed current wave gates and owned paths | L issues only a future pure opt-in P0A helper/tests/docs; F09/CCW/default wiring held for exact later acceptance |
| C14-27 | Medium | Adjacent filing detector and financing/view projects could be duplicated | B6 explicitly dispositions `edgar_dilution.py`, #8308, #8397, #7119 and merged #8051 |
| C14-28 | High | Newly added sector substrate could be assumed era-correct because of its name | Final-head Trend C1 caveat added; historical controls require actual historical classification support |

All findings above are resolved in the report or converted into an explicit qualified gap/gate. None is represented as a production code repair performed by this research.

## 3. Completed executable research evidence

One synthetic case was executed against the exact fetched `engine/debt_maturity.py`, blob `cb5688451aa025156aed89566f9076729526d27e`. The invocation is `extract_maturity_ladder(facts, cik="1", as_of=date(2025, 6, 1))`. The payload contains an older filing dated 2025-02-01 with value 100 and a later filing dated 2026-02-01 with value 999 for `LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths`.

Observed result:

```json
{
  "selected_filed": "2026-02-01",
  "selected_accn": "future",
  "y1": 999,
  "status": "reported"
}
```

The complete synthetic payload is in `MACRO_SOURCE_EVIDENCE.json`. The result proves that the pure extractor alone does not enforce the requested historical eligibility cutoff. It does not prove a live downstream leak. Source inspection separately established that `capital_need.py` rejects future-filed inputs but does not restore the eligible old value after upstream selection. No production data, deployed consumer or predictive backtest was run.

The future P0A positive-path fixture is deliberately **not** claimed as completed here. It will require either proven source clocks or a fully timestamped synthetic envelope, and it must distinguish actual-system from hypothetical-public replay. The current research fixture has filing dates, not enough historical system receipts to invent an actual-system availability claim.

## 4. Independent review and resolved refinements

Three bounded specialist reviews read the report or their complete owner/source remit:

| Review | Verdict and scope | Incorporated refinements |
|---|---|---|
| Economic, temporal and empirical | Full A–L read; no fundamental economic/power/authority blocker | Bidirectional-information interpretation; informative failure censoring; accurate characterization of the original draft; caller-by-caller residual integration list |
| Sources, vendors and rights | Full report read; no core TRACE/vendor/PIT/rights contradiction | Applicable CDS payment wording, foreign SEC filers, TRACE yield/commission semantics, exact EET/IBVAL/Fitch references, adjacent filing detector and horizon-materiality state |
| Macro owner/source compatibility | PASS; no E/L owner or wave-gate blocker | Candidate compiler clock and late-compilation fixture; final protected-delta review |

These are research reviews, not implementation acceptance. The updated text preserves every material boundary the reviewers checked. No review asserts a vendor license, successful live runtime or tested equity alpha.

## 5. Completion and verification criteria

The final document contains substantive sections A–L, including the required source landscape columns, canonical temporal roles, deterministic/LLM split, integration map, empirical falsifiers, P0/P1/P2/defer/reject priorities and a bounded exact future commission. The research separates actual-system replay, hypothetical public replay and retrospective corrected analysis. Source absence claims are bounded; vendor claims are labeled; numerical examples and the illustrative power calculation were checked.

Publication checks validate JSON readability, reference resolution, local artifact links, absence of unresolved session citation tokens, exact source-blob identity for the falsifier, the research-only diff, and the pushed file bytes. GitHub publication is evidenced by the resulting commit/PR rather than a self-referential commit hash embedded in this file. Production test suites are not implied by document checks.

## 6. Remaining uncertainty and next decision

No lawful paid sample, original-vintage commercial archive, negotiated cost/rights agreement, current live freshness or actual consumer receipt was established. The July 2026 Hameed et al. paper was verified at abstract level only. No sector ranking or predictive alpha is established. Existing W2 proof obligations and W3/W4 holds remain as recorded by their current owner.

The recommended next decision is acceptance of **C14-P0A: offline historical-financing-input qualification**, as written in section L. Later default integration, data acquisition, empirical research and policy changes each have their own stated evidence and authority boundary. A useful factual financing capability may remain context-only if market-credit incremental value is null, uneconomic or unprovable.
