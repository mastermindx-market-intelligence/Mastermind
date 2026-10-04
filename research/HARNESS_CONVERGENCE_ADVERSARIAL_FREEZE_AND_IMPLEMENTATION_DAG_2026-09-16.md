# Harness convergence: Sol adversarial freeze review and implementation DAG

**Disposition:** DRAFT / RECORDS ONLY / CHUNK 6 / SOL SELF-ADVERSARIAL REVIEW / PRODUCTION INERT. This is not the required independent non-author review and grants no implementation, experiment, merge, release, provider, credential, routing, account, host or production authority.

**Planning operation:** `harness-convergence-dsh-teardown-20260916-sol-001`.

**Protected Mastermind / Skillpack:** `8ba7deedde164c90298d3e88785d98e02fa5e2d2`, `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap major 1.

**Current planning carrier before this review:** Mastermind PR #687 head `d9c1f2ab2354f9f5881a5e600982aa00aeda25c4`.

**Compared existing owners/carriers:** Agent Evaluation Fabric, #600 Fable orchestration-parity plan, #660 OCR-4A provider-neutral rich proxy, PF1/OCR-4 native-Claude program, #684 Claude permission/native-conformance work, existing ACP worker/native owner, OpenCode Go transport/effective-config work, Model Router/Capacity/Provider Control, Outcome Learning.

## 1. Review question

Attack Chunks 2–5 against the original outcome:

> Give Mastermind one governed heterogeneous agent operating environment that preserves strong native harness advantages, makes lower-scarcity models genuinely useful, measures what creates performance rather than guessing, and never creates a duplicate company control plane.

The review asks:

- Are we secretly building a new harness OS under another name?
- Can the proposed experiment actually identify model versus harness effects?
- Are “same tools/context” claims technically comparable?
- Can provider terms, native retries or ambient config invalidate the science?
- Are bounded workers being confused with sustained COO operators?
- Is evidence being mistaken for routing authority?
- Does any implementation wave duplicate an incumbent owner?
- Could a fresh session execute the wrong next step from these records?

## 2. Disposition

**Architecture survives with corrections.** No evidence discovered in this review justifies replacing `mastermind.worker_adapter/v1`, `mastermind.operator_harness/v1`, Agent Evaluation v1, Executive lifecycle, Model Router/Capacity, Agent OS, RuntimeBinding or provider-native session state with a new universal control plane.

The central architecture remains:

```text
Mastermind company control / admission / responsibility
  -> provider-neutral capability + context/materialization requirements
  -> sealed Worker v1 OR rich OHF v1
  -> provider/native or qualified generic execution engine
```

However, the model-vs-harness experiment is **not automatically identifiable** merely because two arms share a model name. The strongest corrections below must be incorporated before implementation.

## 3. Blocking findings before factor-attribution claims

### B1 — Fable reference may be a whole-system arm, not an isolatable harness arm

The current Fable experience may combine model, provider-private system instructions, native tools, session behavior, memory/context policy, helper behavior and UI/desktop orchestration that cannot all be independently frozen or observed.

Therefore:

- `F_REF` is always valid as a whole-system operational reference if its exact observed model/surface can be recorded;
- it becomes a **harness-effect arm** only when exact served model, model-visible method/context, capability/tool ceiling, relevant provider route and load-bearing environment identity can be held or proven equivalent;
- inability to prove that equality does not invalidate the overall program; it limits the causal conclusion.

**Required correction:** every experiment edge is explicitly classified `MODEL_EFFECT`, `HARNESS_EFFECT`, `INTERACTION`, or `WHOLE_SYSTEM`. An edge may not self-promote to a cleaner class after observing a favorable result.

### B2 — `environment_digest` alone is not environment attestation

A caller-generated digest of intended config would be forgeable evidence and would repeat the same error the rich OHF contract already avoids with requested-versus-observed separation.

**Required correction:**

```text
pre-run configuration binds environment manifest digest
+
owner-native runner/adapter evidence proves the realized manifest/generation
+
technical validity compares requested manifest to observed effective state
```

The model, task prompt and provider output cannot author the attestation. Missing observability remains `INVALID_CONFIGURATION` or an explicit unsupported profile rather than guessed parity.

### B3 — subscription entitlement cannot be moved across harnesses to make the experiment symmetrical

Current protected Mastermind subscription profiles contain supported-tool / interactive-only restrictions and remain autonomous-disallowed. A model being available under a purchased plan does not authorize that quota through DSH/OpenCode/custom API clients.

**Required correction:** cross-engine factor blocks use a transport explicitly lawful for both engines, normally direct API/PAYG or another reviewed provider route. Subscription surfaces may be evaluated only through their supported harness and may produce interactive-shadow evidence without becoming unattended capacity.

### B4 — hidden retry invalidates both effect safety and efficiency measurement

OpenCode has an outer session retry behavior beyond low-level SDK retries; DSH has explicit retry plugins/policies; provider SDKs may also retry. If one arm silently gets extra attempts, it receives both a quality advantage and an effect-safety risk that is invisible to the scorer.

**Required correction:** before Q1, every candidate publishes a retry/fallback characterization:

```text
where retry can occur
which failure classes trigger it
attempt ceiling
whether a request may already have produced an external effect
how retry is disabled/fail-stopped for the experiment
what owner-native evidence records actual attempts
```

Any ambiguous external effect remains `INVALID_EFFECT_UNKNOWN`. No hidden retry is counted as “one run.”

### B5 — same tool names are not sufficient parity

A “Read” or “browser” tool can differ materially in schema, workspace reach, symlink behavior, output truncation, network authority, approval flow and provider-native bypasses.

**Required correction:** factor-isolation arms require exact tool/capability schema digests plus enforcement semantics appropriate to the scenario. Native extra tools must be denied/disabled and observed, not merely omitted from model-visible names. If enforcement semantics materially differ, classify the comparison as whole-system or capability-profile comparison rather than pure harness effect.

## 4. Major findings / required design constraints

### M1 — native helper/fanout changes the treatment

Fable/Claude native helpers, Codex multi-agent, DSH subagents and OpenCode internal delegation cannot be casually left enabled in one factor arm and disabled in another.

For model/harness isolation:

- disable helpers or freeze an equivalent parent-bounded helper ceiling;
- record helper invocations/resources;
- treat independently admitted Executive children separately from native ephemeral helpers.

A whole-system COO comparison may deliberately include native helpers, but then helper quality is part of the system treatment.

### M2 — host is a confounder

MH1 now provides an authenticated remote Worker Broker transport, but multi-host evaluation should not be mixed into initial harness attribution.

For Q2 factor isolation, hold host/OS/runtime class constant where possible. Run multi-host robustness as a later blocked factor or dedicated recovery study. A host change that alters filesystem, network, hardware or local cache state invalidates a pure harness edge unless modeled as a factor.

### M3 — context equality must be semantic and byte-attributable, not token-count equal

Different tokenizers mean identical input bytes can consume different tokens. Artificially forcing equal token counts may require unequal content and bias the task.

Use the same immutable context/method artifacts and record:

- bytes/artifact digests presented;
- provider/model tokenizer usage when exposed;
- compaction or omitted-context events;
- context-window pressure.

Do not normalize away tokenizer differences; they are part of resource economics.

### M4 — repair can hide first-pass weakness

Harnesses differ in resume, steer, context retention and tool error recovery. If the experiment only measures eventual accepted outcomes, a weak first pass with extensive rescue can look equivalent.

Keep first-pass outcome and accepted-after-bounded-repair as separate evidence layers. Repair prompts, review topology and allowance must be preregistered and identical in intent. Effect-unknown work is never repaired through replay.

### M5 — reviewer independence can be illusory

A model family grading itself or a provider-native self-review is not independent evidence for subtle defects.

Use deterministic scorers first. For judgment dimensions, use independent provider/model family or qualified human review where practical, record grader identity, and keep disagreements. Do not shop among graders after seeing results.

### M6 — scarcity and cost need vector accounting

Included subscription quota, PAYG cash, frontier reviewer cognition, host time and Chairman intervention are different resources. A nominally free subscription run can be expensive if it consumes scarce weekly capacity or creates repair burden.

No universal USD/token score. Preserve the resource vector and let the existing routing/capacity owner make a lane-specific frontier decision after evidence.

### M7 — run order can be confounded by quota/cooling/provider changes

Provider load, quota windows, cache warmth and catalog/model updates can drift during a multi-day experiment.

Use blocked/counterbalanced order, exact observation time, provider/model generation evidence and no sample replacement. If a material provider version/model changes mid-block, stop or split the generation; do not pretend random order fixed a changed treatment.

### M8 — public corpus can be overfit

Three public cases per family are development evidence, not final qualification. Do not repeatedly tune a harness until it passes the public 18 and then claim generality.

Sealed holdouts, new experiment identity after exposure and prospective canary are mandatory. Candidate-specific exceptions discovered on a public case must be treated as implementation changes and frozen before holdout.

### M9 — a 24-task corpus is still not production reality

The corpus is designed to discriminate architecture and operating behavior. It does not prove every Mastermind workload.

The sustained-COO stage must include a real producer/consumer journey and prospective shadow/canary under current company owners. “Benchmark-qualified” is not `PROVEN_LIVE` production autonomy.

### M10 — Agent Evaluation organizational projection is stale

Macro’s current Agent Eval workstream wave table lags protected source reality. Starting implementation from that table alone risks recreating protected corpus/scorer/runner work.

The incumbent owner must reconcile its Agent OS record before a modifying implementation wave. GitHub source/evidence owns what exists; Agent OS owns organizational continuity. This planning operation does not edit Fable’s record.

### M11 — no-ABI-v2 ruling is evidence-based, not eternal

Current v1 contracts appear sufficient because:

- Worker v1 deliberately leaves provider-private realization below the floor;
- OHF v1 already carries rich requested/observed identity;
- Agent Eval configuration v1 + run evidence can bind the experiment.

If implementation proves a required immutable pre-effect fact cannot be represented through current profile/materialization/evidence owners without provider-private leakage or semantic distortion, return an exact falsifier. Only then consider a compatible extension. Do not use “future flexibility” as a reason for v2.

### M12 — DSH security maturity remains a release gate

DSH is useful as a challenger and source of patterns, but upstream itself describes the harness as experimental/developer preview rather than a security-audited production isolation boundary. A successful quality experiment cannot promote it to trusted production infrastructure without separate security/runtime qualification.

### M13 — OpenCode config merge remains a specific technical risk

`OPENCODE_CONFIG` alone is not an isolation boundary because native config sources merge. The evaluation bridge must prove the effective merged environment and outer retry/fallback behavior. A model-quality win cannot waive that requirement.

### M14 — #600 and this program must not become duplicate orchestration-parity programs

#600 already owns a Draft Fable orchestration-parity build plan under the existing fabric operation. Harness convergence evaluation is an evidence/input lane to that architecture, not a competing orchestration implementation.

Any later implementation DAG must route:

- Agent Eval corpus/scoring/experiment changes to Agent Evaluation owner;
- generic worker/OHF boundary changes to HF1/OHF owners;
- native Claude to PF1/OCR-4/current realm/capacity owners;
- OpenCode to its incumbent transport/worker owners;
- routing consequences to Outcome Learning/Model Router/Capacity;
- #600 retains its own orchestration-parity integration authority until current owner law changes it.

## 5. Architecture freeze after adversarial corrections

The following are frozen as **planning decisions pending independent review**:

1. **Common above, native below.** Mastermind unifies governance, required environment, evidence and result semantics; provider engines keep subordinate native session/tool-loop implementation.
2. **Two execution floors stay distinct.** Worker v1 for bounded/sealed work; OHF v1 for sustained rich operation. Do not fake persistence in one-shot wrappers.
3. **No universal runner.** Direct native Claude/Codex may remain preferred where their harnesses are stronger; generic engines compete for compatible lanes.
4. **No universal winner.** OpenCode, DSH, Claude, Codex and ACP qualify per task/profile; specialization is acceptable if company authority remains singular.
5. **One capability owner.** ExecutionCapabilityRegistry/profile owners express required capability; provider adapters realize/attest it. No second plugin/tool grant system.
6. **One context/method materialization identity.** Existing Job/Session Truth/Craft/Skill/practice sources produce an Attempt-bound materialization receipt; no worker memory database.
7. **Requested != observed.** Every production-capable harness must prove effective model/config/tools/workspace/session/environment before claiming parity.
8. **Evaluation is evidence only.** Agent Evaluation cannot route, promote, merge, release or create capacity.
9. **First-pass and accepted-result economics remain separate.** Repairs cannot erase weakness or effect uncertainty.
10. **Provider terms are hard gates.** A good result never authorizes unsupported plan usage.
11. **Native helpers are subordinate or Executive children.** No third child lifecycle.
12. **No hidden failover/retry.** Effect uncertainty remains sticky to the same operation/carrier.

## 6. Local implementation DAG — aliases only, not new company programs

These labels are planning aliases for dependencies. They create no Agent OS waves or assignments by themselves.

### A — evaluation substrate

**A0 Owner reconcile + independent review**
- incumbent Agent Eval principal reconciles current protected source / stale organizational projection;
- independent non-author review of Chunks 2–6;
- accept/repair/reject the factor graph, scenario registry and environment-manifest representation.

**A1 Corpus/scorers** — depends A0
- additive six-family/24-case corpus generation;
- deterministic load-bearing scorers + mutation tests;
- holdout sealing.

**A2 Environment identity** — depends A0
- environment manifest builder/validator under existing Agent Eval contract;
- requested digest + observed owner-native evidence comparison;
- no credentials/provider homes.

### B — backend conformance

**B0 Codex reference composition** — depends A1/A2
- prove current protected fresh-Sol/OHF path can consume new scenarios/scorers/environment identity;
- no new runner.

**B1 Native Claude pre-work proof** — independent existing PF1/OCR-4 owner + A2 consumer
- exact CLI/SDK/session/model/effective environment before work;
- if unavailable, no rich Claude factor arm.

**B2 DSH Claude bounded bridge** — depends A2 + DSH frozen one-shot profile
- same-model bounded edge only;
- no sustained-parity claim.

**B3 OpenCode sealed worker/effective-config proof** — existing OpenCode owner, then Agent Eval bridge
- real Worker-v1 path;
- effective merged config + retry/fallback proof.

**B4 DSH ACP rich conformance** — existing OHF/HF1 owner + A2
- frozen DSH profile;
- pre-work model/config/capability evidence;
- persistent session/cancel/close/reconcile semantics;
- no DSH company lifecycle/retry authority.

### C — experimental evidence

**C0 New preregistration** — depends required A/B nodes
- exact models/routes/harness generations;
- exact arm graph, scenarios, replicates, ordering, graders, resources, invalidation law;
- separate from historical E1.

**C1 Public pilot Q1** — depends C0 + fresh live authorization when provider turns occur
- catch gross invalidity and bad scorer/corpus assumptions.

**C2 Factor block Q2** — depends C1
- connected controlled edges / 2×2 blocks;
- no holdouts yet.

**C3 Holdout Q3** — depends C2 frozen finalists
- sealed one-per-family holdouts;
- fixed replicates; no early stopping/replacement.

**C4 Sustained COO Q4** — depends rich B1/B4/other qualified rich backends + C3 relevance
- long-run event/continuation scenarios;
- real parent/result consumption proof.

### D — consequence / product adoption

**D0 Evidence adjudication** — depends C2/C3/C4 as applicable
- Agent Evaluation emits immutable evidence;
- Sol/Fable architecture owner interprets within claim ceiling.

**D1 Prospective owner-native shadow/canary** — Outcome Learning / Model Router / Capacity / provider owner
- no evaluator-owned route mutation.

**D2 Existing harness convergence implementation** — only after owner decision
- provider-neutral sealed capability/profile/attestation deltas through existing HF1/capability owners;
- lane-specific engine adoption; no new platform.

**D3 Production proof**
- real input -> selected capacity -> real harness -> real tools/work -> accepted result -> actual parent/consumer -> visible outcome -> reconciliation.

## 7. Proof requirements by dependency

| Dependency | Minimum evidence | What it must not be confused with |
|---|---|---|
| A1 | corpus digests, hidden-solution law, deterministic scorer discrimination | model quality |
| A2 | requested manifest + owner-observed effective-state mismatch falsifiers | config prose |
| B0–B4 | exact binary/package/model/session/tool/config/effect/cleanup receipts | adapter importability |
| C1 | public pilot complete intended-run accounting | holdout qualification |
| C2 | paired factor evidence with invalid/degraded rows visible | universal causal percentages |
| C3 | sealed holdout confirmatory evidence | production route acceptance |
| C4 | sustained task + return/continuation/consumer evidence | one-shot benchmark score |
| D1 | prospective live shadow/canary under current owner | retrospective benchmark |
| D3 | producer-to-visible-consumer production path | CI/merge/source proof |

## 8. Independent-review packet

The next non-author reviewer should specifically challenge:

1. whether Fable reference factors are observable enough for any `HARNESS_EFFECT` edge;
2. whether the environment manifest can fit Agent Evaluation v1 without creating caller-forgeable evidence;
3. whether each proposed cross-harness provider/model combination is actually lawful under current plan terms;
4. whether tool/schema/effect parity is strong enough for factor claims;
5. whether hidden retry/fallback is fully bounded for OpenCode, DSH and provider SDKs;
6. whether the 24 scenarios discriminate real architecture rather than reward our preferred design;
7. whether holdout secrecy survives current source/reviewer workflows;
8. whether the implementation DAG collides with #600/#660/PF1/OpenCode/Agent Eval owners;
9. whether cost/scarcity accounting biases against included plans or frontier reviewers;
10. whether any source artifact is being labeled shipped/live without a real consumer.

A reviewer should return exact blockers/majors with source refs and falsifiers, not an overall numerical score.

## 9. Stop condition / exact continuation

This Sol self-review does not authorize A0 implementation. The planning package is ready for **independent non-author architecture/security/evaluation review**.

Until that review is consumed and the incumbent Agent Evaluation owner adopts or repairs the design:

- do not implement the 24-case corpus;
- do not modify Agent Evaluation contracts;
- do not install/run DSH for this experiment;
- do not change OpenCode/Claude/Codex routes;
- do not spend provider turns under a claimed harness-convergence experiment;
- do not update routing from these records.

If independent review accepts the architecture, the first modifying capability wave is A1/A2 under the existing Agent Evaluation owner, with routine implementation routed to the least-scarce eligible worker and Fable retained for the owner-level adjudication/integration decision.
