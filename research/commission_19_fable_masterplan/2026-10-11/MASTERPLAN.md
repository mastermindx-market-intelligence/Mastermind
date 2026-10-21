# Commission 19: Institutional Company Intelligence
## End-to-end masterplan and Fable execution handoff

**Assessment date:** 2026-10-11 UTC. **Document version:** 1.0. **Existing program:** Data Intelligence Integration, Commission 19; MAS-263 and Mastermind issue #1243. **Requested execution structure:** Fable principal -> native Opus suborchestrators -> existing Fabric task operators -> optional subagent workers, or direct operator execution.

This is a new, source-grounded successor masterplan, not the missing original C19 package, an Executive Job, a worker launch, a custody transfer, a production release, or proof of model/market performance. Its scope is the whole existing C19 outcome. The authoring task is complete when this packet is usable and verified; C19 itself remains unfinished.

Read [FABLE_START_HERE.md](FABLE_START_HERE.md), then this document, [CURRENT_STATE_CENSUS.md](CURRENT_STATE_CENSUS.md), and [ORCHESTRATION.md](ORCHESTRATION.md). Suborchestrators receive only their assigned prompt, selected work packages and necessary evidence. Source IDs refer to [SOURCE_REGISTER.md](SOURCE_REGISTER.md).

## 1. The outcome worth completing

Mastermind should let an investor open an existing company dossier or Terminal research view and answer: **What changed, which business mechanism does it affect, what conditional financial consequence follows, how does that compare with valid expectations, what has the market actually done, and what could prove the interpretation wrong?**

The machine output is a source-bound, revision-aware research answer assembled from incumbent owners. The output must distinguish direct facts, comparable calculations, statistical estimates, economic assumptions, observed market response and unresolved hypotheses. It must be useful before every optional data family is present, without representing missing core evidence as a completed analysis.

The product should be capable of saying, for example: a company raised an explicitly comparable revenue-guidance range; the changed segment or volume assumption is documented; a stated margin scenario implies a reproducible operating-income range; the licensed pre-event consensus is unavailable, so no consensus-surprise claim is made; the observed price move is contextual rather than proof of causation; the next filing or company update can confirm or contradict the mechanism. This is an illustrative answer structure, not a real current security recommendation or measured historical result.

The stronger later capability is to connect qualified independent evidence across events, guidance, filings, holdings, borrowing, credit and operational telemetry. It must earn that extension through source and consumer proof, not a universal intelligence score. No numerical "percent already priced in" is required or permitted without a separately justified model and its evidence. The formulas and testable input semantics are in [FINANCIAL_AND_DATA_CONTRACTS.md](FINANCIAL_AND_DATA_CONTRACTS.md).

### What completion means

**Product capability:** an entitled user completes the actual research task in the existing company and Terminal surfaces using real source generations. Numeric consequences are reproducible; source/correction drill-down works; stale/partial/denied states are honest; a new issuer does not require a bespoke fake-data path.

**Scientific capability:** declared experiments can assess information and decision value against strong baselines with intact point-in-time and trial accounting. Negative and inconclusive results are valid outcomes. Infrastructure correctness does not establish alpha.

**Operational capability:** released code, active configuration, natural data updates, actual consumption, production monitoring and rollback are separately evidenced. A scheduled job is not assumed to exist because a document names one.

**Program completion:** every C19 recommendation and P0/P1 obligation is accepted, rejected or explicitly deferred for an evidenced reason under its existing owner. No missing original archive, live child, unresolved effect or unproved release silently disappears. One golden answer alone does not complete the program. [S01, S03, S32]

## 2. What the census changes about the previous proposal

C19 is not a blank slate. The previous recommendation was right about the breadth and principal-level difficulty, but the execution plan must start much closer to existing code.

The current `app/integrated_answer.py` already implements a read-only, default-off, nine-leg composer. PR #8596 is merged. Its financial leg is hardcoded to AAPL and fixed historical periods/cutoffs and surfaces query pointers rather than a complete financial explanation. Its capital leg is held, two context legs are fixed absent, and its remaining legs are not a validated event-to-driver model. This is an integration starting point, not a reason to build a second answer service. [S06, S07]

K3E EXP-1 is merged. It has a real bounded captured-expectation inspection contract; it deliberately does not create a normalized baseline. The older dossier's "off-main / 404" observation is historical. Do not rebuild EXP-1, but do not turn its source capture into comparable institutional consensus by renaming it. [S15, S23]

The I1 spec has a material identity mismatch: it maps H06/MAS-273 to FIF publication, whereas actual MAS-273 concerns MRI/RIC macro releases and expectations. It also treats acceptance of the financial query kernel as if it answered the larger real-data acceptance question. A new crosswalk must separate these capabilities without rewriting original records to hide the discrepancy. [S08, S09]

The existing trial ledger still has the same full-file Git blob as the previously demonstrated append-failure/retry defect. The debt selector and the MRI producer/reader also match the earlier inspected blobs. Accepted evidence can be reused instead of rerunning unchanged experiments; existing upstream repair/adapters and active writer collisions still require a targeted check. [S10-S14, S24, S31]

New isolated source-excerpt probes reproduce clock normalization and relative-freshness edge cases in the composer. They are not full-app, browser or production tests and are not a repair. The appendix documents the exact limitation. These findings should become discriminating tests in the current owner code. [S06; verification/composer_excerpt_probe_result.json]

## 3. Scope: depth without taking over excluded projects

Build and integrate C19's data/financial/expectation/evidence/consumer capabilities inside current source owners. Use the current source registry, identities, event workspace, FIF/Forensics, Earnings, K1/K2/K3E, capital/credit, quote/options, MRI/RIC, telemetry, evaluation and product surfaces where appropriate.

**Do not commission a rebuild of Mastermind OS, Executive OS, subagent Fabric, Prophet or GMI.** The requested orchestration consumes existing Fabric; it is not a mandate to repair the whole orchestration estate. The C4 economic-relationship research is retained, but this program consumes only already-qualified relationship references or requests a bounded dependency from its incumbent owner. It does not implement a new graph, retune GMI, mutate Prophet or reopen their studies.

Prefer a **direct issuer operating-driver first vertical**. This removes the need to finish an intercompany graph before obtaining a useful company answer. A source-backed supply relationship can later enrich a mechanism; a relationship label is not a measured exposure and a missing coefficient is not permission to invent one.

Do not add another warehouse, event store, source catalogue, universal identity system, canonical fact graph, thesis lobe, trial ledger, evaluator, auth system, quote manager, queue, router, memory store or publisher. Small versioned projections and adapters belong to existing owners; they must not acquire independent truth or lifecycle authority. [S01, S22-S32]

### Action-specific constraints

Ordinary in-scope diagnosis, reversible design, source edits and tests should proceed once the relevant source custody and tool permissions are clear. Do not require repeated Chairman approval for every technical choice, a new design ceremony, or an inactive historic owner to reappear.

Preserve actual rights restrictions, explicit release holds, live writer leases, uncertain effects and human-only controls. A permission denial cannot be bypassed by another tool or provider. An optional failed dependency blocks only the claims/actions that require it. No new paid feed, credential, account, contract, provider installation, global model setting or production activation follows automatically from this handoff.

## 4. Architecture: compose the answer, not a new platform

The logical path is:

```text
Existing sources and retained originals
  -> native identity / time / correction / use qualification
  -> native event, financial, expectation and context readers
  -> evidence references + deterministic company mechanism/scenario
  -> existing integrated-answer consumer, by reference
  -> Company Dossier / Terminal research experience
  -> existing observation, outcome and evaluation owners
```

These are responsibility boundaries, not new services.

### 4.1 Native source truth

Each accepted input identifies its actual owning source generation and meaningful entity/metric/period. The relevant clock vector is preserved rather than collapsed into one `as_of`. The owner supplies original/corrected ancestry, source completeness and source-use status. The data registry records declared metadata; a registry entry does not prove a real read.

The required evidence depends on the selected replay view. Operational-as-known needs what the system possessed and admitted; source-as-known reconstruction needs historical source availability; recorded-decision replay needs the consumed packet; latest-revised computation is labeled as such. Do not demand unavailable clocks unrelated to a declared view, and do not borrow a clock from another view to manufacture eligibility.

### 4.2 Semantic qualification

Use existing identifiers, metric definitions and fiscal/share/accounting conventions. A same-native-subject financial query can be useful before a cross-type security bridge exists. A security-level composition must use the admitted bridge and actual evidence; a CIK/ticker/string match is not enough.

Expectations must bind issuer, metric, immutable target period, currency, unit, accounting/share basis, source population and availability. A changing relative horizon is not the same target. Consensus movement can reflect analyst changes, entry/exit, stale expiry or revisions; without contributor identity, do not attribute it to continuing analysts. Guidance is a distinct channel. Macro actual, expected revision, survey consensus, nowcast and market pricing are also different types. [S23, S24, S31]

### 4.3 Economic mechanism and calculations

The first model should be as small as the evidence permits. A mechanism packet should answer which operational variable changed, why the event bears on it, when a consequence could be recognized, what input is observed and what is assumed, and which direct company disclosure could refute it.

Deterministic code owns arithmetic, dimensional checks, basis alignment and threshold behavior. Existing fitted models own their estimated parameters with model-time lineage. Language models may extract evidence spans, suggest alternative mechanisms and write grounded explanations, but not supply unsupported factual magnitudes, exposure weights, rights, arithmetic truth or calibrated probabilities.

Useful scenario forms include volume x realized price, customer/segment mix and gross margin, operating expense sensitivity, financing cost under specified debt terms, or a directly comparable company-guidance change. A revenue scenario does not require a fully diluted EPS denominator; an EPS scenario does. Revenue recognition, maximum contract value, backlog and cash receipt are separate. Do not choose a complicated formula merely because a large fleet is available.

Avoid assigning likelihoods just to make a scenario table look finished. Conditional cases and explicit sensitivity are valid. Historical causal identification is a separate empirical question; economic plausibility and time order alone do not establish it. [S22, S24]

### 4.4 Evidence composition and corrections

K1 represents references and declared relationships; it does not certify statistical independence. Keep multiple supported claims and their common origin visible. Corrections and withdrawals append and invalidate affected derived claims; they do not create extra corroboration or erase the old answer.

Bind the actual consumed bytes/generation at the read boundary. Hashing a later reread is not consumption evidence. An answer snapshot should reference the existing snapshot/decision owner rather than create a new integrated warehouse. Snapshot PR #673 remains an occupied implementation dependency to reconcile, not absent work to recreate. [S25, S26, S34]

### 4.5 Product composition and failure modes

Extend the incumbent composer with a versioned owner-approved contract. The following are **presentation concepts**, not an instruction to invent a new global schema: event change; supporting evidence; company mechanism; observed versus assumed drivers; comparable baseline; conditional financial effects; observed market context; source overlap; contradictions; unknowns/falsifiers; source and serving clocks; actual consumer identity.

For each material output claim, specify required inputs. Optional ownership/borrow/theme/context must not keep a directly supported company observation invisible; conversely, absence of a necessary revenue exposure or fiscal match prevents the associated numeric claim. Mark the whole answer partial when its core argument is incomplete. Do not set a single confidence percentage by renormalizing available components.

Use source-specific freshness policy against an explicit request/reference time. A dated quarterly financial fact is not stale merely because a fast market quote is newer; a quote is not fresh merely because all other sources are older. Distinguish economic period, source update frequency and expected release schedule. The current four-day, newest-leg comparison is not sufficient for the C19 product.

When clocks are unknown, preserve their precision and provenance. Do not stamp `composed_at` into a missing source clock. Do not allow future source dates to advance the whole page's information cutoff. The event current alias is an identity selection, not automatic proof of freshness. [S06]

## 5. The finished user experience

### Company Dossier

The entry panel answers the company question before exposing machinery. A compact headline says what changed; the next section explains business consequence, evidence and assumptions. A financial bridge shows the calculation and sensitivity only where qualified. A separate comparison explains company guidance, analyst baseline and observed market response without pretending they are interchangeable.

Evidence drill-down opens the exact source revision/span, not a different current document. The user can distinguish an original release, later correction and a changed interpretation. The page can show uncertainty without becoming a wall of warnings. A missing optional family is a compact availability note; a missing critical fact visibly bounds the conclusion.

### Terminal

The same company answer and source generation appears in an existing ticker/research workflow. Terminal does not regenerate a rival narrative. Symbol switching cancels or fences stale responses; auth and cache identity include the user/tier/entitlement dimensions required by existing contracts. Quotes and company evidence expose their own clocks.

### Change workflow

Use current reactive/event publication owners for refresh. Only a material new source or assumption change needs expensive recomposition; a price tick or duplicate article does not. A correction updates the current answer while preserving prior recorded decisions. Existing alerts remain separately authorized; no live strategy signal or outbound marketing system is introduced.

### Mandatory user-path verification

Verify signed-in full access, permitted public/teaser behavior, denied access, partial/stale evidence, source outage, ticker change race, correction and replay on the real deployed paths. Inspect the response generation and the browser rendering, not screenshots alone. Desktop and narrow mobile views must be legible and accessible. A full frontend rewrite is not part of this mission. [S06, S26, S33]

## 6. Program sequencing and nonblocking dependencies

The detailed DAG lives in [WORK_PACKAGES.md](WORK_PACKAGES.md) and `WORK_PACKAGES.json`. It includes 34 packages mapped to the existing 20 issues; it is a planning artifact, not a new runtime queue.

### M0: recover, preserve and freeze the next interfaces

WP00 recovers the existing C19 parent/custody/effects. WP02 resolves acceptance identities and freezes the next small interfaces. WP01 preserves every original report and missing-source obligation in parallel. Do not turn M0 into a second month of censuses or wait for a missing original ZIP before inspecting an independently authorized current consumer.

A useful first admission wave is O1 native truth/identity, O3 expectations/macro, O7 synthetic evaluation integrity, and O8 composer/consumer contracts, subject to actual capacity and disjoint write scopes. This is a sequencing recommendation, not an asserted concurrency allowance. O2/O4/O5/O6 activate as their source contracts and consumers become useful; logical seats need not all be live simultaneously.

### M1: qualify truth and measurement

WP03-WP08 plus WP13/WP14 establish the real native financial path, identity, evidence semantics, durable evaluation, health receipts and financial input correctness. They can advance independently where path scopes are disjoint. The actual native positive is mandatory; a pile of refusal tests cannot replace it.

### M2: construct useful intelligence components

WP09-WP12 produce qualified expectation and event inputs. WP15 creates a direct issuer operating mechanism. WP16 hardens the existing composer. The old Macro release mismatch is a separate MAS-273 deliverable, not mislabeled financial-publication acceptance.

### M3: make it a real product

WP17 connects claim-bearing evidence and calculations. WP18/WP19 deliver the dossier and Terminal paths, with dark UI work overlapping earlier source qualification. WP20 supplies correction-aware refresh through current owners. WP21 adjudicates the full P0 obligations, including parallel macro/accounting/capital tasks rather than hiding them behind a successful company demo. WP22 tests a second qualified issuer/mechanism without selecting on realized returns.

### M4: deepen the information advantage

WP23-WP30 qualify institutional holdings, short/borrow, options/quote grain, physical/operational telemetry, company KPI bridges, financing actions, one regional equivalence and conditional paid-data decisions. Their entry gates are specific truth/consumer requirements, not a blanket demand to finish every unrelated P0 first. Their final dispositions must be useful and evidenced; deferring everything to make a status board green is not acceptable.

### M5: establish measured value and durable operation

WP31 evaluates incremental information and prospective utility. WP32 proves release, active configuration, real use, resource limits and recovery. WP33 closes the whole original outcome or leaves an explicit owned external frontier. Natural outcome accrual may require future observations; write and verify the actual existing owner/return path rather than claim this chat is a daemon.

## 7. The eight native Opus suborchestrators

| Seat | Domain | What it owns intellectually | Work packages |
|---|---|---|---|
| O1 | Temporal truth, identity, evidence | Native versus cross-type qualification; original/correction replay; declared overlap | 03, 04, 05 |
| O2 | Events and operating mechanisms | What changed economically; direct issuer models; second-case generality; read-only C4 consumption | 12, 15, 22 |
| O3 | Company and macro expectations | Comparable baselines, guidance, MRI compatibility and conditional consensus diligence | 09, 10, 11, 30 |
| O4 | Financial, capital and credit | Retained debt inputs, direct share facts and qualified capital consequences | 13, 14, 28 |
| O5 | Holdings, borrow and microstructure | Measurement grain, legal planes, immutable capture and consumer interpretation | 23, 24, 25 |
| O6 | Telemetry and regional evidence | Physical-to-KPI reasoning, issuer bridges and honest regional equivalence | 26, 27, 29 |
| O7 | Evaluation and adversarial science | Durable accounting, numerical integrity, exposure and incremental-value tests | 06, 07, 31 |
| O8 | Product integration and real-path proof | Consumer contracts, freshness, actual use, UI, Terminal and release evidence | 08, 16-20, 32 |

Fable retains WP00-WP02, WP21 and WP33: original intent, difficult cross-owner decisions, capacity allocation, integration and final acceptance. Independent review is provided by a separate eligible reviewer/operator that did not author the artifact; a coordinator reviewing its own team's assertion is not automatically independent. Every seat receives a ready prompt in `prompts/`.

## 8. Research rigor and financial boundaries

The program must explicitly distinguish source accuracy, information usefulness, predictive skill and a trading decision. A useful research explanation can be valid before a trading edge is demonstrated. Likewise, excellent predictive statistics cannot compensate for leaked future data or an unlicensed source use.

Before outcomes are inspected, freeze the estimand, target/horizon, universe and exclusions, temporal mode, feature/source/label versions, baseline, costs, meaningful-effect threshold, dependence structure and trial/exposure identity. Preserve prior exposed-holdout restrictions. A new file, agent or program label cannot make already-seen outcomes unseen. Modern model knowledge can contaminate retrospective reasoning even when a retrieval timestamp looks old.

Measure component truth and user utility first: extraction errors and missingness; comparable-baseline coverage; calculation correctness; evidence-trace accuracy; correction handling; actual task completion; alert burden where separately authorized. Then assess incremental information on identical keyed support against simple source-only and incumbent baselines. Use issuer/event/date-aware uncertainty and source-family/descendant-aware ablations. Do not count thousands of rows or syndicated headlines as independent events.

Where an evaluation touches returns, use appropriate out-of-time validation, purging/embargo when overlap demands it, realistic transaction/liquidity assumptions, multiplicity accounting, and clear null/inconclusive dispositions. Forecast error, financial consequence accuracy, return association and decision utility are different endpoints. No model-generated score grants ranking, sizing, entry/exit or autonomous capital execution. [S01, S11, S25]

## 9. Rights, data acquisition and economic decisions

A qualified use identifies the relevant retention, transformation, internal/display, redistribution, model inference/embedding/training and correction rights. These are operation-specific; absence of a generalized permission flag is not proof that every narrow existing use is forbidden. Conversely, public technical access is not blanket permission for all downstream uses. Use the established owner evidence and escalate only the exact unresolved use.

Do not let hypothetical premium feeds become the critical path before native evidence is qualified. A purchase candidate must show the precise historical gap and useful consumer, actual delivered original vintages and corrections, applicability/coverage, allowed use, total recurring and integration cost, and comparison with the cheapest adequate baseline. A no-buy result can be the correct outcome. Fable does not acquire new spend authority through this packet. [S23, S27-S31]

## 10. Execution discipline and token efficiency

Use the requested hierarchy, not a flat fleet of frontier models repeatedly rereading the estate. Native Opus seats own bounded domain judgment and continuity; Fabric operators own task execution; workers are optional where a separable task genuinely reduces operator work. One well-specified small task should usually be performed by its already-admitted operator.

Share a compact stable mission contract and exact source pointers. Send only affected deltas after a review. Keep raw logs, full reports and test output in source artifacts, with concise verified summaries at the parent. Preserve accepted evidence and reopen only changed dependencies. Use existing source/workspace isolation and version-aware custody; do not edit one shared worktree from several children.

The goal is **accepted capability per total resource use**, not merely low Fable token count. Record available per-level input/output/cache tokens, monetary usage where observable, wait versus active work, repeated source reads, review/rework rounds and accepted deliverables. Do not infer absent provider telemetry or invent a fixed percentage saving. The parent remains productive during independent operator work and does not burn turns on unchanged polling.

Native profile and public documentation support the design, but neither proves the selected session has the exact tools, permissions, capacity or installed version. Verify the actual native child, its explicit Opus selection, fable-mode invocation, existing Fabric tool access and the operator's permitted worker mechanism before relying on that edge. If the child cannot perform a permitted dispatch, return the exact packet to Fable for the existing authorized carrier; do not build a new dispatcher. [S16-S21]

## 11. Current effect and archival obligations

The previous C19 parent is `01a108b6-7f12-76a2-9123-2b49492f654c`, operation `c19-program-recovery-20261004-01a108b6`. The original request `req-4a8daf76317cfe92f436991444c58281` for `c19-mas269-exposure-custody-20261004-01a108b6` remains a specific reconciliation obligation. A read-only call in the preceding census returned refused/not_found, not accepted execution or proof of harmless replay. Do not resubmit it, invent a new key or transfer it by declaring a new Fable chat. The new reconciliation tool is available; the obsolete blanket claim "the tool is missing" must not be perpetuated. [S04]

Historical routing constraints of the adjacent #1202/#1258 buildout do not silently veto the current live request for native Opus coordinators in C19, and the new request does not relax denied effects or change another program's rules. Preserve active source owners and actual operator limits.

The missing original full C19 package remains MAS-282. This new masterplan preserves and extends evidence; it is not original-byte recovery. The bounded searches did not locate C6 or the original ZIP, which is not proof of universal absence. A future source pointer must establish identity before a recovery claim. These archival gaps remain visible while safe independent work proceeds. [S01, S05]

## 12. Acceptance and closeout

Use [ACCEPTANCE_MATRIX.md](ACCEPTANCE_MATRIX.md) and the original C5 forty-case and C9 Q01-Q20 catalogues. The new matrix supplements them; it does not shrink them. Every tested fact is bound to the exact source/contract and actual evidence scope. A passing fixture, live API, deployed flag and accepted financial model prove different things.

Fable must not stop at a report, review request, passing unit suite, PR, source merge, first golden example or saved checkpoint while safe useful in-scope work remains. On a genuine external wait, save the exact candidate, evidence, effect state, return owner and next action; continue independent ready work. Long-running observation requires an actual durable executor and return path, not text that promises future activity.

At final delivery, state what the user can do, evidence supporting it, what remains unproved, any active children or reserved actions, and the next specific step. Update existing GitHub/Agent OS/Linear owners; do not create another operational memory or lifecycle system. The full C19 result must be coherent enough that a new principal can continue without replaying all historical conversations.
