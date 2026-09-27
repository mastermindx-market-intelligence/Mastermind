# Subagent Fabric Routing Audit — 2026-09-26

**Disposition:** source audit + production-inert calibration patch.  
**Protected source pin:** `4c6b206d3fb7fbc6d077faf61ae361bedf259925`.  
**Skillpack:** `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap major 1.  
**Runtime proof ceiling:** current Executive V2 reader returned `backend_unavailable`; no live routing-frequency or quota-burn claims are made here. External subscription profiles remain non-autonomous / production-unarmed.

## 1. Chairman job

Make heterogeneous worker selection economical and robust enough that attended and future autonomous orchestrators do not burn frontier capacity on routine bounded work merely because the parent program is important, the task is delegated, or a generic `subagent` slot happens to name a strong model.

The target is not "always choose the cheapest model." The target is:

```text
hard authority/capability gates
-> exact bounded-task complexity
-> least-scarce qualified model class
-> Capacity-owned availability/quota/economics ranking
-> Executive-owned claim
-> accepted-result / validation / repair evidence
-> evidence-based escalation when required
```

No new router, queue, quota ledger, retry plane, provider controller, lifecycle, or worker identity system is warranted.

## 2. Audit result

### A. Signal inflation is a real source-level risk

The legacy `WorkRequest` contract has only `task_kind`, `risk`, `ambiguity`, capability requirements and worker exclusions. `critical` risk or `high` ambiguity immediately returns `frontier_lead`.

That is safe only if signal producers use the terms narrowly. A producer that translates "business critical" into `risk=critical`, or "large repository / long prompt / many files" into `ambiguity=high`, forces frontier routing before Capacity can consider an economical worker.

Business impact already exists separately on Executive Jobs and already drives review requirements in the COO cycle. It should not be recycled as a model-strength input.

### B. Durable COO planning and legacy routing speak different dialects

The current COO execution-plan wire carries per-step `business_impact`, `review_required`, `cost_class=small|default`, authorities, validation, placement and prerequisites. It does not carry calibrated task complexity, execution risk, ambiguity or a frontier witness.

The legacy router uses `task_kind/risk/ambiguity`.

Both paths are individually closed, but there is no shared difficulty contract between them. Therefore a planner can emit a schema-valid stronger placement without preserving why that bounded step required stronger cognition.

### C. `subagent` is currently overloaded as a model class

Subscription provider profiles currently expose `routine`, `hard`, `fast` and `subagent`.

`subagent` is topology, not task difficulty.

Before this patch the Alibaba profile mapped:
- routine -> qwen3.8-max
- hard -> qwen3.8-max
- fast -> qwen3.6-flash
- subagent -> qwen3.7-max

The Claude-compatible worker exports that static mapping into `CLAUDE_CODE_SUBAGENT_MODEL`. This means the word "subagent" could itself become an implicit upgrade to a Max-class model.

The GLM profile already had the sounder shape: routine/fast/subagent -> GLM-5.3-Flash and hard -> GLM-5.3.

### D. Current provider data had already drifted

Current public model surfaces have moved since the catalog's 2026-09-13 verification:
- Alibaba now exposes qwen3.8-flash as the current fast multimodal/coding model, including Token Plan and Codex/Anthropic-compatible use.
- xAI/Cursor now expose Grok 4.7 for difficult, long-running frontier work.
- MiniMax M3 remains the current MiniMax workhorse/frontier-operator model; its useful efficiency lever is reasoning/thinking policy rather than a separate Flash sibling.

A stale catalog makes otherwise-correct routing semantics less useful.

## 3. Calibrated task-fit contract

Use the following conceptual dimensions. They may be projected into existing receipts first; a future runtime schema extension belongs to the incumbent Model Router / COO-plan owners.

| Dimension | Meaning | Must NOT mean |
|---|---|---|
| business impact | consequence of wrong/delayed result | model difficulty |
| execution risk | authority, reversibility, security, destructive/operational effect | product importance |
| ambiguity | unresolved requirements/architecture/acceptance or contradictory evidence | repo size / prompt length |
| task complexity | reasoning difficulty of this exact bounded mission | parent-program prestige |
| topology | parent/worker/subagent/reviewer/coordinator | capability tier |
| capability | tools, modalities, context, environment required | "use strongest" |

Calibrated complexity classes:

| Class | Typical work | Model-class ceiling before evidence |
|---|---|---|
| C0_MECHANICAL | deterministic transforms, fixtures, narrow extraction, formatting, bounded test updates | fast |
| C1_ROUTINE_BOUNDED | ordinary implementation/research/debugging with frozen objective + acceptance | routine |
| C2_COMPLEX_BOUNDED | difficult debugging/refactor/research, multi-step or multi-file reasoning with frozen architecture | hard / strong workhorse |
| C3_FRONTIER_JUDGMENT | unresolved architecture/contract, cross-system tradeoff, materially conflicting evidence, non-decomposable long-horizon coordination | frontier/principal allowed |

C3 requires a concrete frontier witness. "Important", "production", "large repo", "long context", "subagent", "writes code", "frontier quota is unused", or "I have not decomposed this yet" are not witnesses.

## 4. Provider-class interpretation

These are suitability hypotheses, not activation or account-selection authority.

### GLM
- C0/C1: GLM-5.3-Flash.
- C2: GLM-5.3 when its observed accepted-result uplift justifies the additional scarcity/burn.
- C3: GLM-5.3 is eligible only if the exact mission is genuinely frontier-like and the realm is qualified; principal continuity is a separate question.
- Current profile already follows the right routine/subagent shape.

### Alibaba / Qwen
- C0/C1: qwen3.8-flash.
- C2: qwen3.8-max when stronger reasoning is actually required.
- Generic subagent default must follow routine, never Max merely because the child is a subagent.
- A hard child can still select Max after the child itself is classified C2/C3.

### MiniMax
- MiniMax-M3 is the current best general MiniMax model in this pool.
- Do not manufacture a nonexistent Flash tier.
- Once the incumbent harness can prove a model-supported reasoning toggle without weakening attestation, C0/C1 should prefer the lower-latency/non-thinking mode and C2/C3 can use thinking/reasoning when warranted.
- Until then, use task-fit + measured native burn/accepted-result evidence; do not infer a separate cheap model that the provider does not expose.

### Grok / Cursor
- Grok 4.7 belongs in difficult/long-running C2/C3 work, not the default routine pool.
- Cursor's own current guidance positions its fast Composer family for everyday work and Grok 4.7 for harder/longer work. This is the same structural split Mastermind should preserve.
- Grok availability must never cause an undecomposed C0/C1 mission to self-promote.

## 5. Routing algorithm tightening

Keep existing owners and make the selection lexicographic rather than one opaque weighted score:

1. **Authority / safety / capability hard gates.**
2. **Bounded-task classification.** Decompose before classifying where possible.
3. **Model-class ceiling.** C0 fast; C1 routine; C2 hard/workhorse; C3 frontier allowed with witness.
4. **Capacity ranking inside the lawful ceiling.** Use current provider realm, quota/headroom, provider policy, expected native depletion, host/harness fit and independence constraints.
5. **Stable Executive claim.**
6. **Outcome evidence.** Validation pass, independent review where required, repair rounds, latency, accepted parent consumption and observed native burn.
7. **Escalate only on evidence.** A failed validation, repeated bounded repair, new ambiguity or a newly proven capability gap may justify moving one mission up a class. Do not escalate an entire program by association.

Strict Pareto dominance / staged comparisons are preferred over collapsing unlike units into one universal score.

## 6. Builder vs reviewer strength

Business impact should usually increase **verification rigor**, not builder model strength.

Examples:
- Critical but deterministic config migration: C0/C1 builder + independent strong review + exact validation/rollback evidence.
- Routine low-impact edit: C0/C1 builder, lightweight review if policy permits.
- Hard ambiguous architecture correction: C3 principal/architect first; then bounded implementation children fall back to C0-C2.

This avoids paying frontier prices merely to obtain confidence that should instead come from independent proof.

## 7. Telemetry needed for closed-loop calibration

Extend existing routing/claim/result evidence rather than creating a router ledger. For each meaningful mission, preserve enough fields to derive:

- requested task kind
- C0-C3 complexity
- business impact
- execution risk
- ambiguity
- topology
- frontier witness or NONE
- first lawful suitability tier
- selected exact model/provider realm
- accepted/rejected result
- validation pass
- repair count / escalation count
- latency
- provider-native depletion observation when available
- reviewer independence and verdict for consequential work

Useful cohort metrics:

- **frontier-overrouting rate:** C0/C1 missions assigned a frontier-class worker
- **down-tier success rate:** C0/C1 accepted without escalation
- **evidence-based escalation rate:** escalation after a real failure/gap rather than before execution
- **repair-adjusted useful throughput:** accepted results per native provider depletion unit
- **false-economy rate:** cheap-tier missions requiring enough repair/escalation to lose the initial economic advantage
- **signal disagreement rate:** planner/parent classification differs materially from post-result evidence

Do not promote a model globally from one aggregate score. Agent Evaluation should establish cohort evidence; Model Router/Capacity consume reviewed evidence under their existing authority.

## 8. Patch in this carrier

This branch makes a narrow, production-inert first correction:

1. Chairman routing law now separates business impact, execution risk, ambiguity, complexity and topology; introduces C0-C3 and frontier witnesses.
2. Executive routing docs explicitly forbid business-impact / repo-size / topology inflation into `risk` or `ambiguity`.
3. Subscription profile validation pins v1 default class to routine and refuses a generic subagent model that differs from routine.
4. Alibaba Token Plan maps routine/fast/subagent to qwen3.8-flash and hard to qwen3.8-max.
5. Provider economics catalog adds current qwen3.8-flash and Grok 4.7 entries.
6. Regression tests pin the new invariants.

## 9. Deliberate non-goals / remaining owner work

Not changed here:
- no production provider arming or credential/enrollment change;
- no #947 MiniMax route seam edits;
- no #1013 attended orchestrator-bundle edits while that active carrier is under review;
- no new COO execution-plan schema;
- no live Capacity ranking arithmetic;
- no retry/failover behavior;
- no automatic thinking-toggle claim for MiniMax;
- no production performance claim while the Executive reader is unavailable and external provider realms remain unproven.

Next incumbent-owner evolution, after this source calibration is accepted:
1. have the attended orchestrator and COO planner emit the same calibrated task-fit evidence;
2. let Model Router map it to a ceiling/tier while Capacity ranks only qualified candidates;
3. run a shadow cohort across C0-C3;
4. accept provider/model promotion only from validation/repair/native-burn evidence.
