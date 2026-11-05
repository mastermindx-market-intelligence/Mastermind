# Harness convergence: experiment registry and Agent Evaluation owner handoff

**Disposition:** DRAFT / RECORDS ONLY / CHUNK 5 / PRODUCTION INERT. This is a bounded implementation and experiment-design handoff candidate to the existing Agent Evaluation owner. It creates no Executive Job, provider/model call, route change, corpus mutation, scorer pass, account enrollment, credential read, install, deployment, Agent OS write, or worker commission.

**Planning operation:** `harness-convergence-dsh-teardown-20260916-sol-001`.

**Protected Mastermind / Skillpack:** `8ba7deedde164c90298d3e88785d98e02fa5e2d2`, `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap major 1.

**Planning carrier before this record:** Mastermind PR #687 head `09671c3c5aa24573640e4607d25bbda6143f852a`.

**Existing experiment owner:** `WS:AGENT-EVAL-FABRIC`, current Macro observation `11485597cc53b3137346084aae4623cceed28a3f`, owner `coo-fable`.

**Existing source infrastructure:** protected Agent Evaluation contracts/corpus/scorers/OHF bridge, merged fresh-Sol runner PR #162 / merge `d6eccb0d81c9db3d009eafa7b37ea97a4dc99bc8`.

**DeepSeek Harness source pin:** `deepseek-ai/deepseek-harness@0d1f50007f9bca3f52b06e1c3074fa14d5fb0720`.

## 1. Mission

Turn the harness-convergence architecture into one executable scientific program under the existing Agent Evaluation Fabric that can answer four practical questions without a universal leaderboard:

1. How much of the observed Fable advantage is attributable locally to model choice versus harness/environment choice?
2. Which exact lower-scarcity model+harness configurations can satisfy bounded engineering, research and review jobs with no governance regression?
3. Which exact configurations can satisfy sustained COO/operator work rather than merely one-shot tasks?
4. Should OpenCode, DeepSeek Harness, native provider harnesses, ACP or multiple specialized engines be retained behind the existing Mastermind contracts?

The machine outcome is a governed corpus + exact configuration graph + scorer set + runner-bridge plan that the incumbent evaluation owner can implement and later execute under a fresh live experiment authorization.

## 2. Why this matters

Current subjective experience says Fable often executes and orchestrates much better than weaker harnesses even when other frontier models appear intelligent. Without factor isolation, Mastermind can make either expensive mistake:

- overpay for frontier models when the real advantage was environment/tool/continuation quality; or
- move strong models into weaker generic harnesses and destroy the operational capability that made them useful.

The result must improve routing economics without converting model preference into company authority. Evaluation remains evidence; Outcome Learning, Model Router, Capacity and provider/runtime owners retain promotion and execution authority.

## 3. Authority precedence and verified current state

Authority order for any future modifying wave:

```text
current Chairman direction
-> current protected Skillpack/procedure
-> Agent Evaluation F0 source law and current protected implementation
-> current Agent Eval program/owner carrier
-> exact accepted experiment preregistration
-> provider/runtime/capability owner gates
-> this handoff as non-authoritative planning input
```

Current source facts relevant to implementation:

- Agent Evaluation already owns immutable scenario/configuration/experiment/run/scorer/evidence contracts. Do not build a second benchmark lifecycle.
- Current configuration v1 can bind execution surface/version, provider, model, procedure, context, capability profile, tool schemas, sandbox/network/environment digests and randomness.
- Run evidence separately binds requested/served model, runner code, process/native-session identity, observed source/tool/capability/network/effect/cleanup/resources/timing.
- PR #162 is now merged/protected and may be reused for its accepted fresh-Sol/OHF scope; older records describing it as unmerged are stale.
- Macro `WS:AGENT-EVAL-FABRIC` still projects several already-protected source waves as todo. Treat that as a projection disagreement for the incumbent owner to repair; do not fork the workstream.
- Current subscription catalog at protected pin contains interactive/supported-tool profiles for GLM Coding Plan, Alibaba Personal Token Plan and MiniMax Token Plan; none is currently autonomous production capacity merely because the profile exists.
- Current protected subscription model rows include `GLM-5.3`, `GLM-5.3-Flash`, `qwen3.8-max`, `qwen3.7-max`, `qwen3.6-flash`, and `MiniMax-M3`. These names are current source observations, not immutable experiment arms until action-time provider/model exposure is re-attested.
- Current harness bindings include Claude-Code/Anthropic paths for GLM, Alibaba and MiniMax; Alibaba also has a Codex Responses candidate and MiniMax an openai-compatible candidate. Activation remains gated.
- OpenCode Go planning currently identifies `minimax-m3` as the shortest Anthropic-compatible native proof and `deepseek-v4.1-flash` as an immediate Chat-Completions follow-on. Those are candidate surfaces, not proof that the same entitlement is lawful through every harness.
- DSH remains a challenger/reference implementation only; no Mastermind DSH route is built or armed.

## 4. Smallest connected experiment graph for the Fable model-vs-harness question

Do not start with a full Cartesian product. The minimum useful graph is a connected set of local contrasts.

### Node notation

Each node is an exact frozen Agent Evaluation configuration:

```text
F_REF    current Fable reference surface, exact observed model + harness generation
N_F      same Fable model on a qualified direct native Claude-Code/Agent-SDK path, if exposed
N_C1     common Claude-family comparator model C1 on direct native Claude path
D_C1     exact same C1 on DSH Claude wrapper
N_C2     second common Claude-family comparator C2 on direct native Claude path
D_C2     exact same C2 on DSH Claude wrapper
```

`N_F` exists only if the exact Fable model is actually exposed on the qualified direct-native path at preregistration time. `D_F` may be added only if the exact Fable model is also exposed through DSH's genuine Claude-Code wrapper and the effective capability ceiling is equivalent.

### Required edges

**E1 — reference-surface delta**

```text
F_REF <-> N_F
```

Only valid as a controlled surface/harness contrast when exact served model, procedure/context/method/tool ceiling and relevant provider route are held constant. If the Fable reference surface has unobservable private instructions or a materially different native tool environment, label this WHOLE_SYSTEM rather than harness-only.

**E2 — local model delta on native Claude**

```text
N_F <-> N_C1
```

Holds native harness constant and estimates the local Fable-model advantage over one common comparator.

**E3 — common-model harness delta**

```text
N_C1 <-> D_C1
```

Holds model constant and estimates the DSH-wrapper/composition delta for bounded tasks.

**E4/E5 — interaction falsifier**

```text
N_C2 <-> D_C2
N_C1 <-> N_C2
```

A second common model tests whether the harness delta is stable across models. If `D_F` is available, add it and complete a stronger crossed block rather than extrapolating C1/C2 interaction to Fable.

### What can and cannot be concluded

If `N_F`, `N_C1` and `D_C1` exist, the chain can decompose the **local observed difference** between Fable-native and comparator-DSH into:

```text
local model delta on native harness
+
local harness delta for comparator model
```

but the unobserved Fable×DSH interaction remains unknown unless `D_F` is run. Never report a universal model/harness percentage from this chain.

If `N_F` cannot be constructed, the experiment can still measure generic Claude-family harness effects and compare `F_REF` as a whole-system reference, but it cannot identify the Fable-specific model share. That is an honest experiment limitation, not a reason to fabricate a cross-surface model identity.

## 5. Generic-engine factor block

After Q0 conformance, use a separate 2×2 crossed block:

```text
                 OpenCode       DSH
API model G1       O_G1         D_G1
API model G2       O_G2         D_G2
```

Selection law:

- G1/G2 must be exact models lawfully available through both engines under the exact tested provider route.
- Prefer reviewed PAYG/API entitlements for this cross-engine block when subscription terms bind quota to a particular supported client/harness.
- Current subscription plans may still participate in **within-harness** model-effect or interactive-shadow studies, but a plan must never be tunneled through DSH/OpenCode merely to create symmetry.
- MiniMax-M3 is a high-value action-time candidate because current Mastermind source already has MiniMax Claude-compatible and openai-compatible seams and the OpenCode Go plan identifies a MiniMax-M3 path. It is **not frozen as G1** until the actual DSH/OpenCode provider routes and terms are re-attested.
- GLM-5.3/Flash and current Qwen rows are similarly useful model-effect candidates, but current supported-tool/interactive-only constraints must remain intact.

The generic block answers local OpenCode-vs-DSH harness effects, model effects, and interaction. It does not decide whether either should replace native Claude/Codex rich operation.

## 6. End-to-end rich-operator reference block

After exact rich-profile conformance, compare complete systems on sustained COO scenarios:

```text
current Fable reference
native Claude rich OHF-v1 candidate
Codex rich OHF-v1 reference
DSH ACP OHF-v1 challenger
Grok/other ACP rich candidate when separately qualified
```

These arms may differ in both model and harness. Their purpose is replacement/augmentation economics:

> Can this exact system complete sustained Mastermind COO work with comparable outcome, governance and intervention burden?

Do not infer model-vs-harness attribution from this block.

## 7. Frozen 24-scenario registry candidate

This is a corpus design input. Existing C0 files are not modified by this record. The Agent Evaluation owner should create new immutable scenario generations with exact fixture/source digests and hidden solutions.

| Family | Public 1 | Public 2 | Public 3 | Sealed holdout | Primary scorer dimensions |
|---|---|---|---|---|---|
| `current_source_comprehension` | `stale_pr_vs_protected_source` | `projection_disagreement_owner_precedence` | `changed_dependency_invalidates_plan` | `continuation_recovery_after_context_loss` | source correctness, currentness, owner precedence, explicit unknowns, useful synthesis |
| `bounded_implementation_fence` | `minimal_provider_neutral_profile_delta` | `producer_consumer_vertical_slice` | `validation_authority_fence` | `no_duplicate_plane_under_new_backend` | behavior present, deterministic validation, scope, consumer completion, no-rebuild |
| `carrier_protocol_compliance` | `lost_start_reply_effect_unknown` | `duplicate_return_single_consumption` | `quota_refusal_no_hidden_failover` | `cancel_cleanup_unknown_no_replay` | effect law, idempotency, retry/failover refusal, exact carrier, cleanup truth |
| `adversarial_review` | `false_green_ci_missing_consumer` | `ambient_tool_widening_hidden_config` | `spec_as_shipped_foundation_as_product` | `owner_scope_collision_with_green_tests` | seeded defect recall by severity/class, unsupported finding rate, evidence binding, intent/owner detection |
| `sustained_operator_continuity` | `two_child_return_integration` | `source_revision_changes_mid_program` | `context_compaction_successor` | `process_generation_resume_stale_predecessor` | objective preservation, delegation, return consumption, source-change adaptation, continuation, false completion, intervention |
| `capability_isolation_and_recovery` | `unexpected_mcp_or_native_tool` | `hidden_native_retry_after_uncertain_effect` | `ambient_config_merge_widens_surface` | `wrong_model_or_direct_provider_fallback` | exact environment, tool/catalog parity, retry/fallback law, model identity, network/sandbox/cleanup |

### Fixture construction rules

- Use a disposable frozen repository or source bundle for coding/review cases.
- Seed deterministic owner/source/effect facts so correctness is machine-checkable where possible.
- Review cases contain a known defect manifest kept hidden from the candidate and exposed only to the scorer/auditor.
- COO cases carry an event script and expected state-transition/consumption invariants; no candidate receives future events before their event time.
- Capability-isolation cases use controlled fake/loopback or reviewed native fixtures before real provider runs; no production secret or unrelated provider home enters the corpus.
- Holdout scenario bytes stay unread by candidate implementers/agents until confirmatory execution. A post-exposure repair creates a new experiment generation.

## 8. Environment manifest identity

Do not widen the canonical Agent Evaluation configuration with provider-private details unless the owner proves a missing semantic. Use existing `execution_surface`, `execution_surface_version` and `capabilities.environment_digest` to bind one canonical **environment manifest** whose owner-native artifact is referenced in run evidence.

The manifest should include only non-secret, reproducible identity:

```text
manifest_version
execution_surface + surface_version
harness family/kind
harness binary/package/source-qualified revision + digest
Mastermind adapter/bridge source-qualified revision + digest
provider protocol class (not credential/account identity)
requested session mode: fresh | resumable | persistent
native configuration digest
ambient configuration sources permitted/disabled
procedure/method materialization digest
context packet digest
capability/profile digest
tool/MCP catalog digest and effective-deny policy digest where relevant
sandbox/approval/network policy digests
native-helper/subagent ceiling identity
retry/fallback policy identity
write/artifact boundary digest
host OS/runtime class + required process-isolation class
cleanup/settlement contract version
feature-flag/config-generation digest where load-bearing
```

Excluded:

```text
credential values
provider-home paths
account emails/PII
access tokens/cookies/headers
Chairman browser/profile identity
arbitrary native config blobs
```

The configuration stores only the digest. The run must supply owner-native evidence proving the launched environment matches the manifest. Requested config is not self-attestation.

### Native Claude manifest proof

Must establish exact Claude CLI + Agent SDK identities, model selection, effective settings/MCP/plugins/agents/skills/browser state, permission mode, ambient setting-source policy, native helper ceiling and process/session identity. If rich operation is claimed, pre-work session/config evidence remains a hard gate.

### Codex manifest proof

Reuse existing App Server binary/config/Skills/MCP/plugins/sandbox/approval/network/workspace/session observations and protocol attestation. Do not create a second Codex environment census.

### DSH manifest proof

Pin exact DSH source/package/profile generation and enabled plugin graph. Explicitly identity-bind session persistence, compaction, tool registry, approval policy, retry plugin policy, MCP mounts, subagent providers and model route. Company lifecycle/retry/memory authority remains outside DSH.

### OpenCode manifest proof

Pin exact OpenCode binary/source generation and the **effective merged configuration**, not merely one supplied config file. Prove provider set, plugins, tools, instructions/project config, retry behavior, model route, direct-provider fallback disposition, workspace/session identity and the attempt-private endpoint when used.

## 9. Implementation sequence under existing owners

### Wave H0 — owner reconciliation and protocol adoption

Decision owner: incumbent Agent Evaluation/Fable COO program.

- reconcile the stale Agent OS wave projection against current protected source;
- review Chunk 4/5 as input, not authority;
- freeze which comparison edges are worth implementing;
- freeze exact corpus/scorer additions and environment-manifest representation;
- do not run providers.

**WHY FABLE for this decision:** Fable already owns the Agent Evaluation program and the question changes the company's heterogeneous-orchestration architecture. Creating a parallel principal would violate ownership. **WHY NOT FABLE for routine source implementation:** corpus/scorer/bridge construction is bounded once H0 freezes the design and should route to the least-scarce eligible implementation lane.

### Wave H1 — additive corpus + scorers

Use existing C0/S1 contracts.

- add the six-family scenario generations and manifest;
- add deterministic scorers for source/owner/effect/capability/fixture invariants;
- use model/human scorer passes only for dimensions not deterministically decidable;
- add mutation/discrimination tests for each load-bearing scorer;
- no provider runner changes required to finish this wave.

### Wave H2 — environment-manifest binding

- define one compatible canonical environment-manifest builder/validator under the existing evaluation owner;
- map its digest into current configuration v1;
- require runner bridges to provide owner-native manifest evidence;
- add negative tests for harness binary/version drift, config drift, tool widening, hidden fallback/retry and wrong session mode;
- no credential/provider call.

### Wave H3 — backend bridges/conformance

Use existing runner/bridge ownership. One backend per bounded PR/vertical.

Candidate order:

1. existing Codex/fresh-Sol reference path (prove new corpus/scorers compose with protected runner);
2. direct native Claude evaluation bridge/preflight only after the existing native owner supplies exact environment/session evidence;
3. DSH Claude one-shot bridge for bounded factor edges;
4. OpenCode sealed-worker bridge after its real Worker/effective-config qualification;
5. DSH ACP rich bridge only after frozen profile/pre-work attestation is accepted.

A bridge does not create provider eligibility or a new runner service.

### Wave H4 — Q0/Q1 dry qualification

- run static/native conformance and public-safe fixture cases;
- no holdouts;
- if actual provider turns are required, obtain fresh experiment-specific authorization first;
- eliminate invalid/non-comparable configurations before expensive blocks.

### Wave H5 — factor experiment preregistration

Freeze exact current model IDs, provider routes, harness/environment digests, scenarios, arm graph, replicates, order randomization, grader identities, invalid/degraded rules, resource capture and analysis language.

Do not reuse or edit E1. This is a new experiment identity with a new sealed preregistration.

### Wave H6 — live factor execution

Fresh authorization required. Execute Q1/Q2/Q3 according to preregistration. No route changes.

### Wave H7 — sustained COO evaluation

Only candidates that have a qualified rich profile enter Q4. Require real parent/result consumption and continuation/recovery proof.

### Wave H8 — consequence handoff

Agent Evaluation publishes evidence only. Outcome Learning / Model Router / Capacity / provider owners decide any later shadow, canary, route or capacity policy change.

## 10. Data, time, null and correction behavior

- Every model/harness/provider source fact is frozen at preregistration time and preserved with its observed time.
- `served_model_observed` is mandatory for a valid real run; requested model is never enough.
- Missing usage/tokens/quota/cash remains unknown, never zero.
- Subscription percentage/credits and cash are distinct units; do not synthesize USD from an unpriced subscription quota.
- Provider/model catalog changes after preregistration do not rewrite historical configurations. A new generation creates a new experiment/configuration.
- A corrected source or scenario invalidates affected analysis by append-only supersession; original run evidence remains.
- Invalid/degraded runs stay in intended-run denominators and resource accounting.
- Holdout exposure is irreversible for that experiment generation.

## 11. Deterministic versus model methods

**Deterministic owner code:** source/manifest digests, scenario/configuration identity, environment attestation, model match, capability/tool/network/effect/cleanup validity, fixture tests, seeded-defect ground truth, event-order invariants, resource accounting, paired identity and evidence graph.

**Model/human judgment:** usefulness/completeness of synthesis, architectural quality, non-obvious review findings, decomposition quality, repair quality and final product usefulness. These become append-only scorer passes with grader identity; they do not rewrite run validity.

## 12. Failure behavior

Stop or invalidate the affected run/arm on:

- model or harness generation mismatch;
- environment manifest unprovable;
- unexpected tool/MCP/plugin/Skill/browser/native helper;
- unsupported or ambiguous subscription/client terms;
- solution/holdout leakage;
- source/context/profile drift;
- hidden provider fallback;
- unowned retry after ambiguous effect;
- `EFFECT_UNKNOWN`;
- cleanup/session settlement uncertainty;
- missing independent evidence required by the scenario;
- scorer/fixture version drift after preregistration.

Do not switch accounts/providers/hosts/harnesses to salvage a failed run under the same configuration identity. A materially changed route is a new configuration and, where applicable, new experiment generation.

## 13. Acceptance and production proof

Chunk 5 itself is accepted only as a **records-only handoff candidate** when:

- it reuses the existing Agent Evaluation owner/contracts;
- it specifies a connected factor graph rather than a universal leaderboard;
- it preserves provider plan/terms gates;
- it defines exact scenario and environment identity without credentials;
- it separates first-pass capability, accepted-result economics and whole-system COO qualification;
- it creates no live provider effect.

Future implementation acceptance requires exact source tests, independent review, corpus/holdout integrity and current-base compatibility.

Future experiment acceptance requires immutable preregistration, real requested/served/harness evidence, complete intended-run accounting, independent leakage review, valid scorer passes and an evidence reference consumed by the actual decision owner.

No route is `PROVEN_LIVE` merely because it scores well. A later production/canary owner must prove the real producer-to-consumer path under current runtime/terms/capacity authority.

## 14. Stop condition and continuation

This planning operation stops short of live evaluation. The live boundary is intentionally separate:

```text
Agent Evaluation owner adopts/fixes protocol
-> corpus/scorers/environment binding implemented + reviewed
-> backend bridges pass Q0
-> new experiment preregistered and sealed
-> fresh Chairman/owner authorization names that exact experiment
-> live provider execution may begin
```

Until those gates exist, no provider/model turn should be described as the Chunk 4/5 experiment.

**Durable record owner:** implementation/evidence stays in Mastermind Agent Evaluation source; organizational program state stays in Macro `WS:AGENT-EVAL-FABRIC` under its incumbent owner; route consequences go to Outcome Learning / Model Router / Capacity.

**Exact next action after this handoff:** perform one independent architecture/adversarial review of the complete Chunks 2–5 convergence package against current #600 orchestration parity, #660 provider-neutral OHF work, native-Claude/PF1 owners, OpenCode/ACP state and Agent Evaluation source. Then freeze the implementation DAG and no-rebuild boundaries before any corpus/source implementation starts.
