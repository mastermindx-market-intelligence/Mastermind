# Bot autonomy and Fabric renewal — architecture amendment and census

Date: 2026-10-11. Operation: `bot-intelligence-renewal-20261011`.
Source basis: Mastermind `cbc7503536b6853ec7c35c2192abdfaccb87b561`.
Status: CANDIDATE / SOURCE ENGINEERING IN PROGRESS / PRODUCTION UNCHANGED.

This is an amendment and implementation-recovery map for the protected September 15 Portfolio V3 architecture, not a replacement investment system or an additional control plane. The current commission requests a comprehensive Bot upgrade, including economical worker and frontier-model access through the existing Subagent Fabric. It authorizes ordinary source engineering and tests. It does not establish provider eligibility, data rights, live capital authority, or deployment approval.

## 1. Outcome and acceptance

The target is one inspectable autonomous paper investment desk: trustworthy market evidence, adaptive research, an accountable portfolio manager, deterministic portfolio construction and execution safeguards, and learning from prospective outcomes. A premium dashboard must expose what the system knows, what it does not know, what changed, what it did, and why.

Completion requires all of the following, separately evidenced: accepted source; exact-version installation; authenticated browser journeys; real eligible worker and frontier executions; validated results consumed by the originating decision; duplicate/restart/failure-injection proof; natural-market paper settlement and accounting reconciliation; and prospective out-of-sample evaluation. A plan, source module, mocked test, green CI, queued Job, or model catalog entry is not the completed system. No performance or profitability guarantee is made.

## 2. Census method and limits

The audit distinguishes protected implementation from historical claims and live proof. Package-root inventory found 15 Bot modules, 52 Portfolio modules, 87 Brain modules, 19 Loop modules, and 10 application modules; these counts measure source coverage, not operational readiness. Exact source files and selected current PRs were inspected. Historical ownership is not evidence of an active writer.

The Executive connector returned `backend_unavailable` before sending its read request on October 11. Submission readiness, active worker custody, and the production Fabric generation therefore remain unobserved. Several independent shell reads were refused before dispatch, including an all-open-PR path-overlap census and a public health probe. These refusals have not been replayed through alternate carriers. They are action-specific, not evidence that every tool, provider, or the deployed site is down. Local source reads, the isolated workspace, and other commands worked. Release requires the remaining collision and runtime checks; no denied operation is bypassed.

## 3. Current capability and owner map

| Capability | Protected implementation/evidence | Assessment and disposition |
|---|---|---|
| Portfolio identity | `portfolio/registry.py` | US `autonomous`, `china`, `hk`, and `self_directed` are active in source. Flagship, Heavyweight and ETF books are archived. Keep history; do not resurrect competing US allocators. Source state is not a live scheduler receipt. |
| US decision boundary | `brain/decision_submission.py`, `bot/autonomous.py` | Model supplies names and ordinal intent; trusted code owns numeric targets and preserves ambiguous omissions. Retain as the execution boundary. |
| Paper accounting | `portfolio/paper_account.py` | Existing transaction/recovery, target validation, pending-target, settlement, fills and NAV owners. Reuse; never create another execution ledger. |
| Shared provider pool | `brain/provider_waterfall.py` | Codex first, then Macro-owned Claude OAuth candidates; auth/quota-only fallback. This is provider availability failover, not task-complexity-aware Fabric research dispatch. |
| Model economics | `config/agents.yml`, `brain/client.py` | Source maps every Codex role, including scout and analyst, to Sol/xhigh. Backend selection is explicit and does not silently enter a metered API. Recover differentiated research without silently downgrading PM judgment. |
| Native children | `brain/codex_bridge.py`, `brain/cli_bridge.py` | Codex has active-book and typed-read-only child fences. Claude fallback removes `Task` until inherited tool isolation can be proven. Agent profile files alone do not prove usable delegation. |
| Executive/Fabric substrate | Existing Executive Runtime, routing policy, capacity and worker adapters | Reuse existing lifecycle, suitability, capacity, claims, result seals and return paths. Runtime readiness is not established by this audit. No new worker launcher or queue. |
| Research desk | `brain/research_desk.py`, intake and intelligence modules | Rich existing dossiers and falsifiable proposals; deterministic ingestion. Audit fail-soft paths and evidence independence. A large prompt is not a proven research protocol. |
| Risk diagnostics | `portfolio/safety.py`, `risk_sizing.py`, `held_risk.py`, `firm_exposure.py` | Useful deterministic primitives already exist. Static basket stress history is not a strategy backtest. Held-risk coverage and stale states must remain visible. |
| Market-risk truth | Existing Macro risk envelope / Grey Deer consumer boundary | Consume its versioned risk truth. Do not derive a competing regime/risk score in Bot. |
| Decision snapshots | September 15 S0 plan; prescribed `decision_snapshot*.py` absent from the protected Portfolio package | NOT_BUILT at audit basis. Recover this first: reproducible evidence must precede adaptive model authority. |
| Learning | `portfolio/forward_evaluation.py`, `shadow_books.py`, `brain/experiment_registry.py`, `loop/holdout.py`, `loop/pbo.py`, `loop/promote.py` | Reuse existing experiment and attribution owners. Do not confuse modules or calendar age with reliable sample mass. Detailed cohort and production proof remain open. |
| Overnight Self-Directed | PR #1293 | BUILT_NOT_PROVEN candidate, not deployed acceptance. BOATS entitlement, display/non-display rights, operator auth and natural-session proof remain separate gates. |
| Browser authorization | PR #1293 documents a bearer-required order POST versus an uncredentialed UI POST, and account/auth helper mismatch | High-priority current-source verification and repair lane. Subscription entitlement is not operator identity. Do not place operator secrets into browser storage or weaken middleware. |
| Public product/runtime | Existing FastAPI and single-file dashboard | No authenticated live browser or deployment-version proof was obtained here. Never portray a source census as complete production acceptance. |

## 4. Recovered plans and current dispositions

1. **Portfolio V3 architecture and S0 plan, PR #658:** merged September 15. Retain the risk-first architecture and sequential experiment program. The documents explicitly describe SPEC_ONLY, production-inert work. Their merger did not build S0. Reuse their schemas, owner map and first vertical rather than invent V4.
2. **Systems review docket for Fable:** retain the findings about silent failures, evidence contracts, scheduler semantics, decision packets, observation mass and failure injection. Reconcile its early new-control-plane/multi-book suggestions against the now-existing Executive and V2/V3 owners. Do not rebuild solved infrastructure or restore redundant books because an old roadmap named them.
3. **Rotation-reader PR #548:** still open/draft, head `2e30afd72d5f8be5f39a15d0f21c223aa77835f4`. Its non-lossy rotation context is an owned dependency, not permission to rewrite those same files. Snapshot coverage explicitly remains partial until the accepted reader is consumed.
4. **Outcome Learning PR #398:** still open/draft, head `d79d2ec3537d8eb060055731a7c3cebee0c543eb`. Recover and assess its contracts/evaluator/CLI against existing forward-evaluation owners. Do not duplicate it or claim the title's “complete vertical” means production acceptance.
5. **Astra client-to-Fabric PR #633:** still open/draft, head `d347248b119379ab12f62e7f749d8dcc5ccd3f9d`. This is an attended engineering-client integration, not the Bot portfolio service's production research router. Preserve its original Auth0 DCR EFFECT_UNKNOWN; no retries, new client, marker deletion or alternate carrier. Its block is not automatically a dependency for every Bot integration path.
6. **Capacity observation PR #994:** open/draft, head `fd8602b5230e208a1892d684bf072c33741f16cd`. Reconcile its candidate with already-present capacity observer source before making installation claims. An open PR does not mean every related module is absent.
7. **BOATS PR #1293:** open, head `a4d4d6d44c7ab31a237b46970858106a1f276888`. Preserve the Self-Directed book, paper-only marketable-limit semantics, BBO checks and separate license flags. Do not mix it into the US autonomous-policy comparison.

These records are recovery targets, not proof that their historical authors still hold live custody. Exact current writer/effect checks remain necessary before integrating their paths.

## 5. Target flow and non-duplication boundaries

```text
Existing licensed Macro / Terminal / first-party portfolio evidence
    -> immutable point-in-time Decision Snapshot
    -> opportunity and research-priority selection
    -> bounded research tasks with snapshot, deadline and capability requirements
    -> existing Executive admission + Model Router suitability
    -> existing Capacity / provider eligibility / atomic worker claim
    -> read-only specialists -> sealed evidence claims
    -> original decision's accountable PM consumes accepted claims
    -> existing risk truth + risk-first constructor + bounded alpha tilt
    -> deterministic feasibility / priceability / turnover / safety checks
    -> existing paper pending-target and settlement owner
    -> reconciled positions, fills and NAV
    -> existing forward evaluation / outcome learning / experiment owners
```

The adaptive research graph is an application workload, not a new lifecycle service. The Bot may describe the work and receive typed results; it may not choose credentials, impersonate another account, lease a worker, invent retries, or mark a Job complete. Macro retains its shared provider control and accounting; Executive retains Job/Attempt/Worker state; Agent OS retains durable organizational continuity; GitHub retains implementation evidence.

The PM is one accountable decision role, not a mandatory permanently running frontier model. A decision cycle may need zero LLM calls when nothing material changed. Research children cannot submit books, place orders, alter account files, raise risk limits, change policy, or promote a model. Their output is evidence, never a vote or numeric capital authority.

## 6. Task-aware intelligence and load balancing

Separate task complexity, business consequence, authority, latency, cost, provider health and model suitability. High financial consequence increases validation rigor; it does not make every extraction a frontier task.

| Task | Default method/tier | Escalation evidence |
|---|---|---|
| Freshness, clocks, deduplication, session status, exposure and fill reconciliation | Deterministic code, no model | Data ambiguity becomes an explicit gap; a model cannot certify a missing quote. |
| Filing/news fact extraction, source attribution, dossier updates, counterevidence retrieval | Qualified economical research worker | Schema failures or difficult source interpretation after bounded repair. |
| Earnings/credit/supply-chain analysis, cross-asset comparison, complex technical hypotheses | Qualified standard/complex research worker | Material contradictory evidence or unresolved cross-system mechanism. |
| Portfolio-relative thesis, regime conflict, exceptional risk and uncertainty adjudication | Qualified frontier judgment when required | Concrete C3 witness, not merely “important” or “subagent.” |
| Portfolio sizing, constraints, order validation, kill switch | Deterministic trusted owners | Never delegated to a model. |

Use the existing router's first lawful suitability tier, then let Capacity rank eligible candidates in that tier. Model names are resolved from current qualified registry entries, not hardcoded from chat memory. Worker/frontier capability, installed harness, model catalog, credential validity, autonomous admission and proven real execution are different states.

A research request needs semantic fields for root decision, immutable snapshot and cutoff, bounded question, required evidence domains, complexity witness, allowed read tools, output contract, deadline, hard cost/turn allowance and independence exclusions. These are application requirements to map into the existing admitted request/profile contracts, **not a new runtime ingress schema**. No provider or broker keys belong in the packet.

Reserve budget before starting work through the current accounting/admission owner. Include review and repair cost. Unknown price/quota is not free capacity. Cost accounting failure cannot grant unbounded new metered work. Bound concurrency by independent useful questions, provider/host slots and the shared root grant; nested coordinators do not multiply capacity. Cancel or expire only through the existing owner and after effect reconciliation.

Priority should consider current exposure, event imminence, data freshness, decision sensitivity and expected information gain. The research queue is the decision's bounded work set, not another company-wide priority queue. Initially use deterministic, inspectable scheduling; any learned value-of-information policy must first win an isolated prospective experiment.

Fallback is permitted only under the incumbent operation's effect rules. A provider timeout after a tool or submission may have executed is not “try the same thing on a different model.” Preserve the exact attempt, inspect its result/effect and reject late results whose decision/snapshot/cutoff no longer matches. The UI distinguishes proposed, admitted, queued, started, returned, validated, consumed and acted-upon.

## 7. Evidence, research and investment quality

Every claim names its source, source generation, observed/known/as-of clocks, evidence family, scope, horizon, uncertainty, contrary evidence and falsifier. An LLM confidence score is not a calibrated probability. A news article, a dossier and three agents quoting that article are one evidence family, not five independent confirmations.

Research is comparative: current holdings, finalists, rejected alternatives and cash receive comparable scrutiny. Start specialists from independent bounded questions before showing the PM's preferred answer. Use adversarial review where a contradiction could change the decision; do not pay a permanent committee to rubber-stamp every cycle.

A technical setup is a testable hypothesis conditional on instrument, market session and regime, not a universal signal. Entry confirmation, thesis failure, risk stop, time stop and profit realization are different mechanisms. Cycle failure may justify an exit only under a preregistered, validated policy; an untested prompt cannot introduce a new generic exit veto into the active V2 cohort.

## 8. Risk and execution architecture

The deterministic risk path must remain serviceable during a model or Fabric outage. Monitor stale data, account/fill inconsistencies, constraint breaches and explicit emergency conditions independently of research latency. An unavailable AI produces a degraded/abstain state, not permission to add risk or flatten every holding.

Reuse the V3 risk-first base allocation, bounded relative views and feasibility projection. Required risk dimensions include gross/net and cash, single-name and issuer concentration, sectors/themes/relationship clusters, factor and correlated event exposure, liquidity/spread/capacity, borrow where applicable, tail scenarios and drawdown. Constraints require named owners and versioned inputs; no invented covariance or silently zeroed missing exposure.

Make the allocation waterfall inspectable: prior holding -> risk anchor -> bounded alpha tilt -> constraint adjustment -> executable target -> filled holding. Explain both the requested intent and the effective action. Cash has a reason: opportunity scarcity, risk reserve, stale evidence, liquidity or deliberate defensive posture.

Preserve the existing paper transaction and settlement journals, compare-and-swap fences and idempotency. Reconcile partial/late fills and pending targets before accepting another decision. A displayed target is not a fill; a simulated fill is not a live order. Preserve instrument identity, splits/dividends, native-currency accounting, exchange calendars and regular/extended/overnight session provenance. Overseas and overnight mandates remain separately qualified.

## 9. Product experience

Extend the current application; do not replace its storage or routing to obtain a new appearance. The default workspace should answer a decision, not expose an unstructured pile of signals.

- **PM Today:** current paper book, decision age/cutoff, market posture, change since prior cycle, selected action/abstention and unresolved risks.
- **Opportunities:** ranked research candidates and rejected alternatives, source coverage, catalyst/horizon and what would change admission.
- **Research and Fabric:** actual task graph, question, evidence family, requested versus observed model, status, latency and measured cost; no fabricated worker activity.
- **Portfolio and risk:** explainable target-to-held waterfall, factor/cluster exposures, scenario losses and explicit coverage degradation.
- **Execution:** pending/accepted/filled/rejected states, paper label, price/session provenance and reconciliation incidents.
- **Learn:** cohort-frozen attribution, calibration, counterfactuals, promotion/demotion eligibility and open incident replays.

Use the existing identity plane for read/operator separation. Public subscription membership must not confer trade/operator capability. User or retrieved text renders as text, not HTML; validate closed query parameters, object identity and response size. Do not expose secrets, raw private model reasoning, provider homes or account identifiers in an operations panel.

## 10. Evaluation and promotion

Run three separate scorecards: investment skill, system safety and operational/economic efficiency. A faster or cheaper model may still degrade evidence quality; a profitable period may be market beta; an honest safe system can still lack alpha.

Use point-in-time universe membership and information availability, corporate-action-safe prices, realistic spread/slippage and session rules, purged/embargoed walk-forward evaluation where labels overlap, and an untouched confirmation cohort. Record all tested policies and selection decisions. Use existing PBO/multiple-comparison machinery; report uncertainty and effective independent observations rather than only headline Sharpe or win rate.

Disentangle selection, construction, timing, execution, costs, cash and factor exposure. Compare the V2 book, risk-only constructor, worker-only research, adaptive research and full V3 challenger sequentially, not by tuning everything simultaneously. Model routing earns promotion from accuracy/calibration, valid evidence, counterevidence discovery, decision utility, tail-risk behavior and cost per accepted useful result. A higher-tier model does not receive authority because of its brand.

Observation checkpoints (including the original V3 20/60/126/252-session reviews) schedule review; they never automatically establish sample sufficiency or promotion. Live-capital execution remains outside this commission.

## 11. Implementation order and gates

| Wave | Consumer-visible outcome | Required proof / boundary |
|---|---|---|
| R0 — recovery | One current plan/census with retained and superseded dependencies | Exact source refs, honest runtime unknowns and current effect/custody reconciliation. |
| S0 — evidence | Immutable snapshot, explicit composition, read-only inspector | Original September 15 S0 contracts; future-data exclusion, correction lineage, bounded reads and zero V2/provider/account effects. |
| F1 — research bridge | Bot research request maps to existing Executive/Fabric admission and returns to the original decision | Actual reviewed request/profile mapping; no new queue; read-only child confinement; duplicate/restart/late-result tests; real worker and frontier canaries. |
| R1 — claims | Independent specialist claims and comparable candidate dossiers | Provenance, family deduplication, calibrated uncertainty and adversarial falsifiers; no sizing authority. |
| P1 — shadow construction | Risk anchor, bounded alpha tilt and explainable feasible shadow target | Existing risk/settlement owners, perturbation stability, capacity/cost constraints and active V2 byte-equivalence. |
| X1 — execution quality | Reconciled paper lifecycle and event/risk response | Natural sessions, outage/partial-fill replay, operator authorization and explicit source/version proof. |
| L1 — learning | Prospective attribution and economic routing experiments | Recover #398 where compatible, preserve untouched cohorts; no self-promotion. |
| U1 — integrated product | Authenticated complete user journeys across all panels | Desktop/mobile browser proof, empty/stale/error/partial/corrected states, accessibility and server-side scope checks. |

The foundation can be built while live Fabric proof is blocked. No source implementation should silently arm models or alter the active portfolio in order to demonstrate integration. Shared-file collisions and release gates remain held until observed and reconciled.

## 12. Current continuation and no-redo

Verified: compatible protected Skillpack pin; isolated workspace acquired for this operation; source census and current exact PR states above; strategic state loaded through its canonical loader; pytest is available. The strategic state explicitly prohibits autonomous production deploy, live-capital execution and duplicate control planes.

Next: implement and test the recovered S0 contract in new isolated source files, then advance the remaining source-capture/storage/API dependencies when their exact contracts and write surfaces are verified. Keep the broader Fabric integration as a separate vertical so a source-only adapter is never mislabeled as real worker execution. Do not repeat the prior full-plan archaeology or denied tool actions. Do not touch #633's DCR marker, #1293's workspace or any existing account/settlement data.

No worker has been dispatched by this operation. No autonomous wake or background execution is claimed. No production, credential, licensing, trading or deployment setting has been changed.
