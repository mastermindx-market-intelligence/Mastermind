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

## 13. Material recovery amendment — use the existing VPS service-inference bridge

The deeper targeted provider census recovered **Mastermind PR #1147**, operation `vps-fabric-llm-convergence-20261001-sol-001`, at current published head `b832ee7d67f7a5060d7088dcb5a257328728f041`. This is the existing non-CEO VPS-to-Executive/Subagent-Fabric foundation. It supersedes any interpretation of F1 above as a new bridge design. Reuse its existing client, service identity, sink admission, host binding, transport, I/O contracts and same-operation reconciliation. Do not copy them into another service or create a second load balancer.

The PR description and `docs/VPS_INFERENCE_SERVICE_FOUNDATION.md` lag its latest published I/O/transport commits. The decisive cumulative frontier is issue comment `5966698046`, with current source verified at b832. It distinguishes three states:

| State | Recovered work | What is not proven |
|---|---|---|
| Published source | Non-CEO `svc-vps-inference`, READ/RESEARCH A0 ceiling; service client and host-owned route binding; pure request/result/ref/document contracts; 60 KiB service-only ingress frame ceiling | Installed service, credentials, qualified workers, actual dispatch and Bot consumption |
| Retained uncommitted candidate | Eight-path request-wiring patch, SHA-256 `9ff757d2b9348f71926a6f3aacdfd49f790d70f40759f2118b388fb4fd1cead5` | A full-green committed wiring candidate; one fixture edit was explicitly refused and remains held |
| Unbuilt/unproven integration | Operation-bound direct result projection, installed service mount and host execution, call-site migration and streaming | Any claim that VPS reasoning is already Fabric-converged |

The current source-custody owner lookup found no registered sol-lane workspace for #1147 and no matching worktree in this shared Git repository. That is not evidence that its retained dirty patch disappeared or that a replacement writer may overwrite it. Preserve the original patch/refusal frontier and reconcile its original source before reuse. Do not recreate the refused fixture change through another tool, account or worker. A historical author's name is not a live lease, but an unlocated dirty candidate is not a clean cutover either.

### 13.1 Retire stale dependency gates, not real integration work

Two blockers still written into #1147 are stale:

- **#1112 merged October 3**, merge `4766adc84deae7efd6a4ced1fb727e77c224c766`. Its old open-PR shared-server custody is no longer a reason to wait. The actual service route still needs current-source composition, authentication and installation proof; the merge did not install that route.
- **#1041 closed unmerged October 6**, head retained as reference `b3816bb75fa328ec6df1f92a77e8377016efdc8e`. Its terminal disposition, comment `6009530697`, says protected V1 already supplies the aggregation-root/planner/work/review/repair graph needed by the relevant downstream program. Do not reopen or import its rejected depth-2/domain/schema/provider-accounting layer merely to unblock the Bot. Use the existing protected V1 owners and current role-correct ingress requirements instead.

The H4 downstream note on #1147 (comment `6012088566`) separately requires role-correct principal admission. A Bot service principal is not a CEO or a COO. Preserve that separation while sharing the existing authenticated app and Runtime owners; do not solve service admission by borrowing a human CEO token or pretending every inference is a CEO commission.

### 13.2 Three workload classes, one shared execution estate

**Pure/background inference** — classifier, extraction, bounded JSON reasoning, summaries and related non-tool application calls — uses **one ordinary role-null READ/RESEARCH Executive Job**. The host supplies the reviewed source/workspace/quota/profile binding; Model Router supplies lawful suitability; Capacity and Runtime claim the worker; the common Supervisor owns execution and validation. A planner/reviewer/aggregation hierarchy for every small JSON call would waste frontier capacity and delay the product. The service cannot select credentials, host, worker or a custom command.

**Agentic PM/research turns** — bounded research with approved tools — use the existing governed COO/Operator/worker graph where that authority is actually admitted. Children remain read-only and return claims to the originating decision; they cannot inherit root book-submission tools. Existing original-parent, grant, budget, source and effect fences remain mandatory. No new hierarchy is required merely because a specialist uses a different model.

**Interactive UI reasoning and chat** require a separately proven streaming consumer. #1147's terminal-result client is not a drop-in replacement for `/chat` SSE. Keep streaming state, disconnect/cancel semantics, source identity and result consumption explicit. Do not cut over an interactive surface to a terminal-only route and call it feature parity.

### 13.3 Exact payload and result boundaries

The published `control_plane/executive_inference_io.py` at b832 contains these existing contracts:

- `mastermind.executive_service_inference_request.v1`: exactly `schema`, `system_prompt`, `input_text`, `max_output_chars`; **48 KiB canonical request limit**.
- `mastermind.executive_service_inference_worker_result.v1`: dedicated `answer`, plus exact Job/Attempt/Worker binding and COMPLETED status; **128 Ki characters maximum requested output** and **192 KiB total worker-result limit**.
- Existing direct result-reference and result-document schemas bind the answer to exact Job, Attempt, Worker and raw-result digest.
- Service frames may be at most **60 KiB**. Legacy CEO ingress remains **8 KiB**. The local status-response path is **32 KiB**, whereas the public MCP/read plane is **256 KiB**.

These are distinct ceilings, not interchangeable token budgets. A Unicode response can satisfy a character limit and still exceed its byte limit. A full 262,144-byte V3 snapshot does not fit inside the pure-inference request. Select explicitly scoped, bounded evidence sections and include their immutable snapshot/claim identity in the authorized payload; never silently truncate the snapshot or lose coverage denominators. Tool-enabled research may use a separately admitted read capability for additional sections.

Do not overload the generic `JobPayload.summary` as the model answer or force a full prompt through the 4,000-character business objective. The retained wiring candidate binds the closed inference payload into existing immutable JOB_CREATED provenance; it does not add another prompt store. Status remains small and returns an exact result reference. Actual answers belong on the existing `executive_fabric` read plane through the direct service-inference view, not a fourth service tool, arbitrary child selector or result database.

### 13.4 Capacity and failover acceptance

The October 3 #1147 runtime report observed a stale AVAILABLE worker projection whose provider-readiness receipt was failed/expired, and a VPS using Claude fallback because Codex was unavailable. Those are dated observations, not current health claims. The later October 11 Executive read showing one AVAILABLE worker does **not** independently prove that provider readiness, service eligibility or fallback parity has since been repaired.

A cutover must therefore prove current service-eligible capacity, not just a registered slot or installed binary. Require an actual economical-worker result and an actual justified frontier result through the same admitted service/agentic estate, followed by validated consumption at the originating Bot decision. Verify cost attribution, admitted budget, latency, cancellation/late-result handling and an allowed degraded path. Do not cut over the only working legacy reasoning path to a single unqualified worker or add a hidden direct-provider fallback behind the Fabric client.

The targeted source census also recovered #715 (`9539c9647cdff5621e523c57c367b0403f276a57`) and #668 (`9a524adaa7624e497170f0869bad23bd98e65fcc`). #715 repairs false-green failed `submit_book` results and demonstrates why forwarding a tool error containing quota/auth keywords can cause an unsafe waterfall replay. #668 removes pool-ranking ledger scans from health availability. They already own relevant `cli_bridge`/`codex_bridge`/waterfall/test paths; this renewal does not duplicate those edits.

Adversarial acceptance must include both returned and interrupted tool-capable turns: a quota/auth-looking error after possible tool effects cannot authorize another provider or key attempt. Review inner SDK/key rotation as well as the outer provider waterfall. A string classifier, a missing tool list or a changed provider is not effect reconciliation. This is an explicit open safety-review obligation, not a claimed new repair in #1357.

### 13.5 Revised direct integration sequence

1. Recover #1147's published source and original retained wiring/effect frontier; keep the refused edit held. Do not rebuild that work in #1357.
2. Reconcile against current protected V1, removing the stale wait for closed #1041 and merged #1112 without removing real source/identity/installation gates.
3. Complete the existing request binding and direct result-view composition under those existing owners; retain 48/60/32/192/256 KiB boundaries and exact result identity.
4. Enroll the service-to-service identity through the existing Auth0/admin owner, with the distinct service scope and subject. Human tokens, new secret stores and CEO impersonation are prohibited.
5. Prove freshly qualified worker/frontier capacity and resilience for this exact service profile. Do not interpret Runtime AVAILABLE as sufficient readiness.
6. Migrate pure/background call sites first, agentic PM loops next, and interactive streaming separately. Preserve paper books, decision generation, source lineage and rollback evidence through each cutover.
7. Accept only after installed exact-version proof, authenticated consumer journeys and real decision-to-result-to-paper-outcome evidence. Neither #1147 nor #1357 alone completes this commission.

Current #1357 implementation status: snapshot contracts/store/inspector and calendar source repairs are built and locally tested; source capture, authenticated web integration, Fabric cutover and production acceptance remain incomplete. This amendment and the validation record are the current navigation points; the earlier census remains an explicitly dated source baseline.

## 14. Actual M2 Fabric discovery and browser/API capability delta

The earlier Executive-only runtime census was incomplete. A bounded process-path observation found three processes referencing the standing `ext/host_queue.sh` below:

```text
/Users/chriswong/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08
```

Observed PIDs at discovery: 2084, 2092, 93121. The current host reported `Mac14,14`. The existing `ext/state/glm_flash_routing_repair_20261003.json` is present at this root and its SHA-256 exactly matches the prior recorded `5ff2a5d604cfaba28146c1ff8c9fc9eb2b134d1b0345c9ff188e97b968c3e5f8`. These are concrete runtime-location and historical-receipt findings, not proof of fresh provider eligibility or Bot service admission.

The inspected standing queue script describes per-host `REMOTE_QUEUE_<host>.txt` consumption through `remote_lane_v8.sh <host> <label>`, host load/free-space/AC/concurrency gates, and existing duplicate/active-lane checks. The inspected v8 entrypoint resolves its host from the existing `hosts.json`. This is a separate existing operational path; one AVAILABLE worker in Executive is not a census of this whole estate. The target remains convergence with existing owners, not replacing or adding to this queue. Do not route a Bot request into a label queue, pick credentials/hosts, or claim a current worker capacity merely because these scripts exist.

A subsequent combined read of other selected Fabric script/receipt fields was refused. That exact operation remains held and was not replayed. The source-capture write, original #1147 wiring/fixture boundary and #633 enrollment uncertainty also remain unchanged. A future accepted service composition must verify this actual Fabric's current grant, route, result and return contracts in addition to Executive's service boundary. No worker was launched and no queue/host/provider state was changed.

The independent evidence consumer has advanced beyond the earlier CLI-only status: the real application now mounts an operator-protected GET `/api/decision-snapshot` and a responsive `/decision-evidence` shell. This consumes existing immutable records; source capture remains absent. The focused router avoids editing the overlapping main dashboard SPA or #1293's `app/web.py`. Existing auth is reused, not replaced. The new JSON route is explicitly excluded from the shared response cache, with a causal authorized-then-unauthorized read test. A separate causal test caught the full-envelope size overrun and now enforces the 64 KiB section response limit including metadata.

Verification categories remain separate: real FastAPI/application/cache/authorization tests with temporary evidence; browser rendering tests with intercepted synthetic responses; source-only mounted capability; and still-unproven production/operator-session/source-capture/Fabric/market acceptance. The browser has no credential entry, credential storage, source mutation, model call or order control. It shows blocked, missing and corrected evidence honestly instead of inventing live intelligence.

## 15. Recovered source and task-aware admission — superseding the unlocated-wiring blocker

The original #1147 workspace and retained request-binding patch have now been located, reconciled and published on their ORIGINAL carrier. The match was exact: b832ee7 source plus eight dirty files / 35,723 bytes / patch SHA256 9ff757d2b9348f71926a6f3aacdfd49f790d70f40759f2118b388fb4fd1cead5. Its actual root is the older `/Users/chriswong/Documents/Cluade/.worktrees/vps-fabric-llm-convergence-20261001-sol-001`, backed by Cluade/Mastermind. Earlier GitHub-path searches did not cover it. Two cwd matches were an old read-only grep pipeline, not an active source writer; no process was killed or reassigned.

Original-carrier commits: b1958754 preserves the exact retained patch; 608ab814 history-preservingly composes protected1f5befa4 with citation-coordinate-only conflict resolution; **09719bb76d19cfd8bccb28a8759540acbafb0c81** implements/reviews task-aware inference request binding. This supersedes the earlier unlocated/original-wiring-not-published state. It does NOT clear the one previously refused fixture edit or the independent #1357 snapshot/source-capture denials.

The service I/O owner now supports closed request v1 and task-aware v2. V1 has unchanged normalized fields and routine route. V2 adds exactly named `task_kind`, not a model/provider/account/host selector. The existing ModelRouter maps evidence extraction to routine research and comparative analysis to elevated research. The canonical sink rebuilds host constraints from the actual fingerprinted request, preventing a stale routine binding from admitting a comparison task. Contradiction adjudication resolves to the existing frontier-lead classification and is refused from the ordinary service-Job lane; the separately admitted governed-judgment consumer remains required. No new worker queue, host chooser, risk engine, lifecycle or credential plane exists.

Source test/review states are distinct: original recovered source136pass/1heldfail; protected-base composition234pass/1heldfail; task-fit source257pass/1heldfail, including23new task-fit cases. The held `test_direct_emitter_cannot_bypass_sink_guard` omits the required request payload and fails at an earlier refusal; it was not edited or deselected. Independent read-only consequential review found no actionable defect in the exact seven-file task-fit increment, using source and pure injected probes; it did not independently prove installed host/Router/auth/Capacity/provider behavior. Review evidence is in #1147 `tests/fixtures/vps_inference_task_fit/`.

### Consumer proof across the two existing source owners

The Bot encoder at **67d7c2a8799ddab24146ab610f22e40af8d1c355** exposes explicit `task_aware=True` while retaining default-v1 encoding. This changes only the inference wire builder; the previously refused zero-evidence and snapshot repairs remain unchanged. Cross-PR integration with service09719bb7 is conflict-free tree **3540d69ab01a0a3bae3ffc19f10d7191c95581a9**.

The existing standalone source-admission canary was advanced to that exact tree and passed **10 cases**. Actual imported Bot encoder, service client, canonical ingress/sink/principal and temporary SQLite Runtime preserve a **26,560-byte** v2 evidence packet under exact snapshot/context identity. Comparison's elevated task fit now reaches actual Job constraints (`standard.research`), while extraction retains routine first-lawful aliases (`fast.research`, `standard.research`). It proves duplicate/conflict/restart and lost/tampered reply behavior without resubmission, provider-selector pre-transport refusal, no false finished answer for a queued Job, and zero ordinary Jobs for a frontier judgment request. The historical eight-case v1/gap canary is retained separately, not overwritten into a success claim.

These are SOURCE-ADMISSION results: transport and host authorization are fixtures, no live network service/OAuth/provider/worker is run, and no direct returned-answer path is proven. The real Runtime is temporary, not the installed Executive. The failed broader Bot unit command was not replayed; the new source canary is tied to newly published producer/service revisions and does not clear existing RED tests. Artifacts: `tests/fixtures/bot_service_admission/source_admission_v2.json` and `task_aware_source_proof.json`.

Remaining critical gates: admitted repair of the reproduced snapshot/zero-evidence defects and old service fixture; actual source capture; installed role-correct service identity/mount and host selection; current provider capacity; real worker plus governed frontier execution and operation-bound returned-answer consumption; active Bot call-site migration including streaming; then separately authorized browser/natural-paper-session/forward-evaluation proof. A working preparation/admission path is substantial integration progress, not the completed autonomous trading system.

## 16. Direct-answer consumer and authenticated service profile — source-built, producer held

Service head **b14d1c0e515778c71af291df7f7a93408a01cfbd** adds an exact direct-answer consumer on the original #1147 owners. A result-reference v2 separates the original raw provider-result hash from the canonical structured-content hash, and the document validator recomputes the latter. Default v1 reference behavior is preserved. This supplies content integrity, not evidence that the source is truthful or an actual worker ran.

The client retains the original operation/objective/request, reconciles its admission receipt, checks the fingerprint, and reads only the status-selected content-bound Job/Attempt/Worker reference. Both the reference and validated receipt are isolated from callback mutation. Original-request or answer/reference substitution, unknown/stale/partial output and read cancellation cannot turn into submission, replay or claimed acceptance. The method returns a complete NOT_PROJECTED direct view; no numeric capital or execution authority is created.

The existing three-tool service MCP profile and ASGI App support a distinct closed `view=service_inference` selection alongside legacy aggregation. Identity is rechecked before status/result access and after the read. A foreign reference is rejected before answer access. The App does not create Runtime or read arbitrary files to obtain a missing result. Its underlying read gateway and canonical Runtime direct-result producer still lack this view, so an installed old backend refuses rather than fabricating a completed answer.

Actual source tests now include41direct-answer and19authenticated-profile cases, all passing; the latter run the real Python client and ASGI JWT/enrollment machinery with synthetic signed tokens and injected backend results. The full selected service scope is319pass/9fail: eight cases describe the unbuilt Supervisor request/prompt/schema seam and one is the older held fixture. The separate Bot correctness failures remain open. Independent review first exposed a mutable-receipt P1, reproduced and repaired, then returned no actionable finding for the final seven-file slice. It used source and pure injected probes, not independently observed production auth or providers. Initial/final review, source hashes and exact JUnit counts are preserved under service tests/fixtures/vps_inference_direct_return.

The Supervisor admitted-request reader edit was explicitly safety-refused and remains absent. No alternate implementation, model switch or result-store workaround was used. The existing Runtime completion owner must eventually bind actual request, current Attempt, successful process/collection/assignment evidence, canonical content and raw-byte provenance before a direct read can be regarded as execution proof. Its bounded observation and the existing read-plane transport must also reconcile the16KiB wrapper/32KiB socket/192KiB I/O/256KiB public ceilings without truncating answers. These are concrete remaining production-path gates, not another broad architecture commission.

The current source composition of Bot1d7c04b0 with serviceb14d1c0e is conflict-free tree4de9a95f07633ff27bbd51f5d928acb1c3d60584. Composition is not installation or provider execution. The ten-case earlier task-aware source-admission proof retains its original refs; it is not promoted to a live-result claim. No workers, providers, queue items, credentials, portfolio orders or production deployment settings changed in this increment.

## 17. Read-only research claim consumption over validated service answers

The original decision, not the remote worker, owns whether an answer is consumed. Add a pure application projection from the previously validated direct-answer view to closed, bounded candidate evidence claims. The projection verifies exact original operation/reference/fingerprint, snapshot/context identity, explicit selected-row references, qualified source receipts, counterevidence and falsifiers, with no numeric target/position/order authority and no new ledger. Unknown/partial/omitted domains must remain visible; repeated evidence artifacts are not independent observations. Output is an inspectable CANDIDATE packet, never an automatic portfolio action or an assertion that an LLM statement is true.

The direct service answer remains unconsumable until #1147's authentic Supervisor/Runtime completion writer and installed read transport are proven. Unit tests use synthetic, explicitly labeled client-validated results; they prove only deterministic boundary behavior. The existing brain/research_desk.py retains dossier/research ownership. This packet is a single-decision transient evidence projection, not a second memory, promotion or lifecycle registry.
