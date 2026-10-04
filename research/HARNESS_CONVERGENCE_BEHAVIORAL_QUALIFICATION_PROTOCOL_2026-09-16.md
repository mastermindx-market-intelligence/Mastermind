# Harness convergence: behavioral qualification and factor-isolation protocol

**Disposition:** DRAFT / RECORDS ONLY / CHUNK 4 / PRODUCTION INERT. This continues the Chairman-authorized multi-turn harness-convergence planning operation. It does not execute an evaluation, spend provider quota, change routing, install a harness, alter the Agent Evaluation corpus, mutate a capability profile, submit an Executive Job, or transfer the existing Agent Evaluation principal.

**Planning operation:** `harness-convergence-dsh-teardown-20260916-sol-001`.

**Organizational evaluation owner:** existing `WS:AGENT-EVAL-FABRIC` / Fable COO principal. This record is a design input to that owner, not a replacement workstream or commission.

**Protected Mastermind / Skillpack pin:** `8ba7deedde164c90298d3e88785d98e02fa5e2d2`, `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap major 1.

**Current Macro Agent OS observation:** `mastermindx-market-intelligence/macro@11485597cc53b3137346084aae4623cceed28a3f`.

**DeepSeek Harness source rechecked for this chunk:** `deepseek-ai/deepseek-harness@0d1f50007f9bca3f52b06e1c3074fa14d5fb0720`.

**Current planning carrier before this record:** Mastermind PR #687 head `2c60a5d861f3d0eb70c8faff67304951f697dbb4`.

## 1. Question and falsifiable outcome

The practical question is not “which model has the highest benchmark score?” It is:

> For Mastermind work, how much useful performance comes from the underlying model, how much comes from the harness/environment, how much comes from their interaction, and which exact model+harness configurations produce accepted company results at the best defensible quality-resource frontier without weakening governance?

The specific Chairman-relevant subquestion is:

> Is the current Fable advantage primarily frontier model intelligence, the native Claude/Fable operating environment, or their interaction; and can OpenCode, DeepSeek Harness, Codex, ACP, or another qualified engine make lower-scarcity models operationally competitive for bounded workers or sustained COO work?

A valid experiment must be able to falsify each of these hypotheses separately:

- **H-model:** changing only the model materially changes accepted task outcome while the harness/environment stays fixed.
- **H-harness:** changing only the harness/environment materially changes accepted task outcome while the exact served model stays fixed.
- **H-interaction:** the harness effect differs materially across models; model and harness contributions are not additive.
- **H-portability:** a candidate configuration can meet the same bounded or sustained operating profile with no governance regression and lower resource burden.
- **H-native-moat:** the current native Fable/Claude path remains materially superior even after another model is given an equivalent governed environment.

The protocol must not report a fake global “70% model / 30% harness” decomposition unless a connected crossed design and sufficient repeated observations actually identify those effects. When the design only supports local paired deltas, report local paired deltas.

## 2. Existing Agent Evaluation Fabric is the experiment owner

Do not build another benchmark service, leaderboard, task database, runner, experiment tracker, or policy writer.

Current protected source already provides the correct evidence architecture:

- `scripts/agent_eval/` immutable scenario/configuration/experiment/run/scorer/evidence contracts;
- the governed corpus and holdout discipline;
- append-only deterministic/model/human scorer passes;
- technical validity separate from task correctness;
- the OHF runner bridge;
- the fresh-Sol OHF runner, now protected through merged PR #162 / merge `d6eccb0d81c9db3d009eafa7b37ea97a4dc99bc8`;
- the sealed E1 preregistration, which remains a separate historical Skillpack experiment and must not be edited or repurposed.

The current Macro `WS:AGENT-EVAL-FABRIC` record still projects B2/B3/B4/C1/C2 as todo even though protected GitHub/source contains later capability. Treat that as a known organizational projection disagreement. This planning branch does not edit the incumbent Fable-owned Agent OS record.

The existing evaluation configuration schema is already close to sufficient for harness qualification. It binds:

```text
execution_surface
execution_surface_version
provider
model_requested
reasoning_effort
auth_realm_class
protected procedure/source
context packet/retrieval configuration
capability profile + tool schemas
sandbox/network/environment digests
randomness
```

and each immutable run separately records runner code provenance, requested/served model, process/native-session fingerprints, source/capability/tool/network observations, completion, effect, cleanup, evidence, resources and timing. Therefore Chunk 4 does **not** justify an Agent Evaluation schema v2.

Exact harness/runtime generation should be bound through the existing execution-surface identity plus a canonical environment manifest digest that includes the actual harness binary/package/version/digest, adapter generation, capability projection and relevant native configuration identities. Owner-native evidence must prove that manifest at run time. Do not add provider-home paths, credentials or arbitrary native config dictionaries to the evaluation configuration.

## 3. Experimental unit: one exact configuration, not a vendor name

The atomic treatment is an immutable configuration:

```text
(model requested + served)
× provider route
× harness / execution surface generation
× operating profile
× procedure/method generation
× context generation
× tool/capability generation
× workspace/source snapshot
× host class
× randomness/sampling settings
```

Changing any load-bearing component creates another configuration. “Claude,” “OpenCode,” “DSH,” “GLM,” “Fable,” “Codex,” or “MiniMax” alone is not an experimental arm.

The run must record the exact served model. Opaque Auto routing, silent provider fallback, model substitution, hidden direct-provider fallback, or unobserved harness version changes produce `INVALID_CONFIGURATION`, not a result for the intended arm.

## 4. Identification strategy: a connected comparison graph, not a Cartesian explosion

Do not attempt every model on every harness. Build a connected graph of controlled edges where each edge changes one principal factor.

### 4.1 Harness-effect edge

Hold constant:

```text
model
provider/model generation
reasoning effort where comparable
scenario + source snapshot
procedure/method/context
capability/tool catalog
sandbox/network/effect policy
host when technically possible
review/scoring path
```

Change only the execution harness/environment.

Example conceptual edge:

```text
same exact Claude-family model
native Claude/Fable path
        vs
DSH Claude-Code wrapper
```

for bounded one-shot task classes only. DSH's current Claude wrapper cannot be used to claim sustained-session parity because its documented surface is one fresh query/process per run with no continuation/resume/pooling/progress stream.

The highest-value version of this edge is the current Fable model itself **if and only if** the exact model is exposed on both compared surfaces at trial time and both paths can prove the same capability ceiling. Otherwise use another exact common model and do not infer a Fable-specific harness percentage from it.

### 4.2 Model-effect edge

Hold the exact harness/environment/profile constant and change only the requested/served model.

Examples of eligible future blocks after provider/profile qualification:

- multiple Claude-family models on the same native Claude path;
- multiple reviewed GLM/Qwen/MiniMax models on the same Claude-compatible sealed-worker path where subscription/terms and execution mode permit the trial;
- multiple exact API models inside one frozen DSH ACP composition;
- multiple exact API models inside one frozen OpenCode composition.

### 4.3 Interaction block

Where two exact models are lawfully available on two exact harnesses, run a 2×2 crossed block:

```text
               Harness A      Harness B
Model 1           A1             B1
Model 2           A2             B2
```

This identifies:

- local model effect inside each harness;
- local harness effect for each model;
- model×harness interaction.

A generic-engine block should preferentially use two exact API models that are supported by both OpenCode and DSH through explicitly authorized PAYG or otherwise lawful transports. Do not route a subscription plan through an unsupported custom client merely to create a symmetric experiment.

### 4.4 End-to-end system comparison

The current Fable reference path, Codex/Sol rich path, a future DSH rich path, OpenCode coding path, Grok ACP path or other systems may also be compared as complete systems. These comparisons answer:

> Can configuration B replace or augment configuration A for this task class?

They **do not** identify why the difference exists when model and harness both change.

## 5. Corpus: 24 governed tasks, six families, three public + one holdout each

Use an additive Agent Evaluation corpus generation under the existing C0 owner if the owner accepts this protocol. Do not overwrite current scenarios.

### Family A — `current_source_comprehension`

Primary use: research/current-truth recovery.

Scenarios should require exact source precedence, revision/currentness handling, disagreement detection, provenance, explicit unknowns and a useful decision-ready synthesis.

Failure examples: stale PR body treated as current truth; retrieved prose treated as authority; current owner missed; an unknown converted to false/zero; important contradiction omitted.

### Family B — `bounded_implementation_fence`

Primary use: coding/implementation.

Scenarios should require a bounded implementation or patch in a frozen disposable repository with deterministic validations, source/write fences and a real consumer.

Failure examples: narrowed product intent; unrelated refactor; duplicated owner; validation claim authored by the model; workspace escape; code compiles but intended behavior remains absent.

### Family C — `carrier_protocol_compliance`

Primary use: operation/effect/continuation correctness.

Scenarios should seed lost replies, duplicate delivery, stale continuation, cancellation, quota refusal or process-loss boundaries and require the correct same-operation behavior.

Failure examples: blind retry after `EFFECT_UNKNOWN`; cross-provider/account/host failover; false START/ACK; native process absence treated as remote-effect cancellation.

### Family D — `adversarial_review`

Primary use: independent review/security/product-intent review.

Each scenario contains a candidate artifact with multiple seeded defect classes: one obvious, one cross-file/system, one evidence/proof overclaim, one owner/authority violation and one product-intent narrowing. The reviewer must find material defects, avoid invented defects and produce a repair decision grounded in exact evidence.

Report seeded-defect recall and unsupported-finding rate separately. Never collapse them into one “review score.”

### Family E — `sustained_operator_continuity`

Primary use: COO/orchestrator qualification.

A multi-turn scenario requires: recover objective, decompose bounded work, consume one or more returned artifacts, distinguish routine worker work from principal judgment, preserve rejected decisions, respond correctly to a changed source condition, compact/recover context, and finish with exact next responsibility.

At least one scenario must include a subordinate-return cycle and one must include a mid-run process/session replacement or resumable continuation where the claimed rich profile supports it.

A sealed one-shot worker is **not penalized** for failing this family when it never claims a sustained-operator profile; it is simply ineligible for the portable-COO lane.

### Family F — `capability_isolation_and_recovery`

Primary use: effective-environment truth.

Seed extra native tools, tool-schema drift, unexpected MCP/plugin/Skill exposure, wrong model, native hidden retry, network widening, ambient config inheritance, provider fallback, cleanup uncertainty and context/session mismatch.

Most cases are hard validity gates rather than subjective quality tasks. The candidate must refuse or safely terminate according to the frozen profile.

### Corpus construction law

For each family:

```text
3 public development scenarios
1 sealed holdout scenario
```

for 24 scenarios total.

Use point-in-time internal snapshots or lawful public/licensed fixtures. Solution refs are hidden. Candidate-specific implementation details must not be included in scenario prompts. Holdouts remain sealed until the confirmatory phase; seeing a holdout requires a new experiment generation if a candidate is subsequently changed.

## 6. Two outcome layers: first-pass capability and accepted-result economics

A system that produces a plausible answer but needs repeated rescue is not equivalent to one that reliably finishes the job.

### 6.1 First-pass outcome

One admitted run, no repair. Measure:

- technical validity;
- task-specific deterministic scorer result;
- independent review result where required;
- first-pass accepted/not-accepted;
- latency/resource consumption;
- intervention count.

This is the cleanest model+harness capability measurement.

### 6.2 Accepted-result episode

A separate workflow-level episode may include a preregistered bounded review/repair allowance **only after a known-complete, effect-certain result**. It never retries an unknown external effect.

The repair protocol must be identical across compared arms. Each repair creates explicit new turn/run/evidence identity according to the existing owner; no hidden provider retry counts as a repair round.

Measure:

```text
accepted-result rate
first-pass acceptance rate
repair rounds
review findings
human interventions
principal frontier cognition consumed
worker/provider resource consumed
elapsed time to accepted result
```

Failed, invalid and abandoned episodes remain in resource denominators. “Cost per accepted result” must include their consumed resources rather than conditioning only on successful runs.

## 7. Hard validity gates before quality comparison

A run is not eligible for behavioral comparison unless the existing Agent Evaluation validity chain can establish the applicable items below.

Zero-tolerance gates:

1. requested and served model identity match the frozen configuration;
2. exact harness/execution generation is attested;
3. source/workspace/context/procedure generation matches;
4. effective capability/tool set does not exceed the frozen profile;
5. no unexpected MCP/plugin/Skill/native-helper/network capability;
6. no hidden provider/harness fallback outside the arm;
7. no unowned retry after an ambiguous effect;
8. effect state is known or the run is invalidated as `INVALID_EFFECT_UNKNOWN`;
9. cleanup/process-group/native-session settlement satisfies the scenario;
10. holdout/solution leakage is absent;
11. required owner-native evidence resolves and matches digests;
12. any human intervention is recorded rather than hidden.

Provider outage, unavailable subscription surface, or equivalent exogenous missing dependency becomes `DEGRADED_DEPENDENCY` when allowed by the scenario; it is not silently counted as model failure or removed from the denominator.

## 8. Score vectors; no universal winner

Keep dimensions separate.

### Common outcome dimensions

- correctness / contract satisfaction;
- completeness;
- currentness/source fidelity;
- authority/effect safety;
- evidence quality;
- no-rebuild compliance;
- product/useful-consumer completion;
- operational fluency;
- reviewability.

### Coding dimensions

- required behavior present;
- validation/tests actually pass through owner path;
- scope adherence;
- artifact quality;
- regression/repair burden.

### Research dimensions

- primary-source correctness;
- source coverage;
- disagreement/currentness handling;
- synthesis usefulness;
- unsupported-claim rate.

### Review dimensions

- seeded-defect recall by severity/class;
- unsupported-finding rate;
- evidence binding;
- intent/owner/production-proof detection;
- repair decision quality.

### COO dimensions

- objective preservation;
- decomposition quality;
- correct delegation boundary;
- return consumption;
- source-change adaptation;
- continuation correctness;
- stale-state rejection;
- false-completion count;
- Chairman intervention count;
- durable next-action quality.

### Resource vector

Never compare raw token counts as a universal cross-provider efficiency scalar. Record separately:

```text
input/output/reasoning tokens when exposed
provider calls
model billable cash where directly known
subscription quota/credit delta where observed
host/runtime elapsed time
first-token and completion latency when available
tool calls and invalid tool calls
context bytes/tokens presented
frontier principal tokens/calls used for review/repair
human intervention count
repair rounds
```

For subscription plans with no direct marginal price, report plan/quota consumption rather than inventing USD. Provider tokenizer differences stay explicit.

A configuration may be preferred for a lane only through hard gates plus a task-class-specific Pareto/non-inferiority decision by the existing owner. The evaluation fabric does not emit a global model rank.

## 9. Staged run plan to avoid wasting expensive frontier compute

### Stage Q0 — static and native conformance

No quality claims. Prove the candidate runner/bridge can bind exact configuration, model, harness generation, capability profile, evidence, cancellation/effect and cleanup semantics.

Any candidate failing Q0 does not advance to expensive behavioral runs.

### Stage Q1 — public pilot

Purpose: catch bad scenarios, broken scorers, impossible parity assumptions and grossly weak configurations.

Recommended shape:

```text
8 public scenarios
cover at least 4 families
1 run per arm/scenario
counterbalanced execution order
```

This stage is descriptive and may eliminate clearly unsuitable configurations. It is not a holdout result and does not select routing.

### Stage Q2 — factor-isolation blocks

Run only the connected harness/model edges required to answer the causal attribution questions.

For a 2×2 block:

```text
2 models × 2 harnesses
12 public scenarios (2/family)
2 preregistered replicates
```

Counterbalance arm order within each task/replicate block. Keep source/profile/host fixed where possible. If host cannot be held fixed, the comparison is no longer a clean harness effect and must be labeled accordingly.

This yields paired task-level deltas and model×harness interaction evidence without running every candidate everywhere.

### Stage Q3 — sealed holdout confirmation

Only configurations that remain scientifically relevant after Q2 enter holdout.

Recommended shape:

```text
6 sealed holdouts (one/family)
3 fixed replicates per finalist configuration
no early stopping
no sample replacement
```

A changed model/harness/profile/procedure after holdout exposure creates a new configuration/experiment generation. Do not re-label tuned reruns as the original confirmatory experiment.

### Stage Q4 — sustained COO qualification

Only exact rich-operator profiles participate.

Use the sustained-operator family plus cross-family long tasks requiring at least:

- multiple turns;
- one subordinate-return consumption;
- one source/current-state change;
- one context-pressure/compaction or process-generation event;
- one safe refusal/recovery boundary;
- a real accepted result and exact parent/consumer evidence.

A one-shot wrapper may still be an excellent bounded worker and should not be forced into this lane.

### Stage Q5 — prospective shadow/canary

Agent Evaluation evidence alone does not arm routing. Any route/policy consequence passes to the existing Outcome Learning / Model Router / Capacity owners for prospective shadow/canary and owner acceptance.

## 10. Candidate comparison blocks

These are **experiment candidates**, not authorization to run or claims that every route is currently lawful/live.

### Block C — native Claude vs DSH Claude wrapper

Purpose: isolate additional DSH wrapper/composition effect on a fixed Claude-family model for bounded tasks.

Requirements before run:

- exact model exposed on both surfaces;
- same native Claude CLI/SDK generation where the comparison intends only wrapper effect;
- same allowed tools/context/method;
- DSH ambient profile/plugins/retries disabled or attested to the same effective ceiling;
- one-shot task classes only.

If the current Fable model is available on both, include it. Otherwise do not infer Fable-specific harness share.

### Block G — OpenCode vs DSH generic engines

Purpose: choose generic engine(s) for non-native/API models and estimate model×harness interaction.

Use two exact models that can lawfully run on both engines through current authorized transports. Prefer direct PAYG/API entitlements where subscription terms would make a custom harness ambiguous.

Required parity:

- identical model generation/model ID;
- same source/context/method;
- same tool catalog and execution enforcement;
- same write/network profile;
- native retries characterized and neutralized/fail-stopped according to scenario law;
- exact effective config attestation;
- no direct-provider fallback.

Do **not** force one universal winner. OpenCode may qualify the sealed coding lane while DSH qualifies a richer persistent automation lane, or vice versa.

### Block S — same sealed harness, multiple models

Purpose: estimate model effect with harness held fixed.

Candidate substrates include the existing Claude-compatible subscription worker for its reviewed interactive/supported-tool surfaces and future qualified OpenCode/DSH sealed profiles.

Respect plan terms. An interactive-only subscription experiment remains interactive shadow evidence and cannot become unattended capacity through a good score.

### Block R — end-to-end rich-operator reference

Purpose: answer the operational replacement question.

Compare the current Fable reference path against any fully qualified rich contender such as native Claude/Opus, Codex rich, DSH ACP, Grok ACP or another later accepted path.

Because model+harness may both differ, interpret this as whole-system outcome evidence, not factor decomposition.

## 11. Analysis law

### 11.1 Primary summaries

For every arm and task family report:

```text
N intended
N completed
N VALID
N invalid by exact reason
N degraded by exact reason
first-pass accepted count/rate
accepted-after-bounded-repair count/rate
repair distribution
intervention distribution
resource vector
```

Never drop invalid/degraded runs from the top-line denominator.

### 11.2 Paired deltas

For each controlled edge, report per-task paired differences and distribution. Do not pool incomparable dimensions across task families.

For binary first-pass acceptance, show the discordant pair table. For continuous resources, show paired differences/ratios with task identity preserved.

### 11.3 Factor model only when identified

If a connected crossed block has adequate observations, a later statistical scorer may estimate task-blocked model, harness and model×harness terms. The first pilot is too small for strong causal or percentage claims.

The default conclusion language is local:

```text
On these tasks, with this exact model held constant, harness B changed first-pass acceptance by X paired cases and changed resource vector Y.

On these tasks, with this exact harness held constant, model B changed outcome by ...
```

Do not extrapolate a local edge into a universal provider/model superiority claim.

### 11.4 Blinding and leakage

Where feasible, independent graders receive artifact/output content with arm/model/harness labels removed. Deterministic scorers run first. A model grader must be from an independent model/provider family where practical and its identity is recorded.

Reviewer disagreements remain evidence; do not choose the friendlier grader post hoc.

## 12. Qualification decisions

### 12.1 Bounded worker qualification

A candidate may be recommended to the existing routing owner for a defined bounded task class only if:

- all hard safety/effect/capability gates pass;
- holdout task correctness meets a preregistered minimum/non-inferiority requirement;
- invalid/degraded behavior is visible and acceptable for that lane;
- accepted-result resource burden is on a defensible frontier;
- provider terms/auth/capacity/runtime qualification is separately satisfied;
- a prospective shadow/canary succeeds under the existing owner.

### 12.2 Portable COO qualification

In addition to bounded-worker gates, a portable COO configuration must prove:

- sustained multi-turn/session behavior through the claimed rich contract;
- correct subordinate-result consumption;
- exact continuation/resume/process-generation behavior;
- no stale context takeover after succession;
- correct source-change adaptation;
- zero unauthorized/duplicate effects in the tested recovery cases;
- no false completion on seeded unfinished work;
- a real parent/consumer actually receives and uses the accepted result;
- acceptable Chairman intervention burden.

A high coding score cannot compensate for failing continuation/effect governance.

### 12.3 OpenCode vs DSH selection

Do not ask “which engine wins?” Ask:

- which engine qualifies for sealed coding;
- which qualifies for research/review;
- which qualifies for persistent rich operation;
- which produces lower accepted-result burden for exact supported lanes;
- which has fewer unobservable ambient/retry/config behaviors;
- whether retaining both creates useful specialization without creating duplicate company authority.

## 13. Minimum implementation delta in Agent Evaluation

If the Agent Evaluation owner adopts this protocol, the expected implementation is additive:

1. Extend the governed corpus with the new scenario families/cases and immutable manifest generation; do not mutate current C0 cases.
2. Add task-specific deterministic scorers using the existing append-only scorer-pass contract.
3. Add compatible runner bridges for newly qualified backends; do not create a new experiment lifecycle or runner service.
4. Bind harness/runtime generation into the existing configuration `execution_surface*` + `environment_digest` identity and prove the corresponding owner-native environment manifest during each run.
5. Reuse existing experiment/arm/pair/replicate identities and validity/evidence machinery.
6. Use the existing fresh-Sol runner as one runner/bridge path; do not fork it.
7. Hand any route consequence to Outcome Learning / Model Router / Capacity rather than writing routing from the evaluator.

A new Agent Evaluation schema version is justified only if a required immutable pre-run fact cannot be represented through the existing configuration/scenario/evidence contracts without semantic distortion. Chunk 4 found no such fact yet.

## 14. Current capability / proof ceiling

This record is research and experimental design only.

Observed current facts used:

- protected Mastermind advanced to `8ba7de...` through MH1 remote Worker Broker transport #650;
- PR #162 is now merged/protected (`d6eccb0...`), correcting the older reconciliation record that called its source unmerged;
- Agent Evaluation protected source already contains R0/C0/S1/OHF2/E1 preregistration machinery;
- Macro Agent OS workstream projection is stale relative to protected implementation evidence;
- current Fable orchestration parity remains a Draft plan on PR #600, not a proven universal baseline;
- DSH upstream remains at `0d1f500...` for this chunk.

No provider/model run, benchmark, human grading campaign, scorer execution, holdout read, source test suite, account read, routing change or production canary was performed by Chunk 4.

## 15. Exact next action

Chunk 5 should turn this protocol into an **actionable experiment registry and implementation handoff without running it yet**:

1. reconcile the exact current Agent Evaluation implementation and owner carrier;
2. map candidate model+harness arms to lawful current provider/plan surfaces;
3. select the smallest connected factor-isolation graph that answers the Fable model-vs-harness question;
4. define the 24 scenario briefs and required scorer dimensions at corpus level;
5. define exact environment-manifest identity for native Claude, Codex, DSH and OpenCode without widening company authority;
6. produce the bounded existing-owner handoff for Agent Evaluation, including implementation order, proof, stop conditions and explicit no-route-change boundary;
7. leave live provider execution for a separately authorized experiment/canary wave after corpus/scorer/runner review.
