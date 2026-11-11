# Harness convergence: author-review hardening amendment

**Disposition:** DRAFT / RECORDS ONLY / AUTHOR-SIDE ADVERSARIAL REPAIR / PRODUCTION INERT. This amendment continues planning operation `harness-convergence-dsh-teardown-20260916-sol-001`. It is not independent review, does not self-accept PR #687, and grants no implementation, provider, credential, routing, Agent OS, capacity, merge, release, or production authority.

**Exact candidate reviewed:** Mastermind PR #687 at `b3e24dc5148e0e1c10edaddb7d24f9b847119acd` before this amendment.

**Protected Mastermind / Skillpack:** `8ba7deedde164c90298d3e88785d98e02fa5e2d2`, `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap major 1.

**Independent review state:** GitHub review remains requested from non-author `mastermindx-3`; this amendment does not impersonate or replace that independent evidence. Current Chairman direction explicitly allows Sol to continue author-side work rather than parking the program while that review is pending.

## 1. Purpose

Chunks 4–6 survive author-side red-team review, but three load-bearing experimental claims need stronger boundaries before any live harness comparison can be trusted:

1. the six published "sealed holdout" concepts are already semantically exposed and cannot remain confirmatory holdouts;
2. a causal harness edge needs exact non-secret host and provider-realm/principal generation identity, not only a broad host class plus `auth_realm_class`;
3. a `grader_identity` string does not prove an independent model/human grader.

A fourth clarification separates experimental randomization from provider RNG support so a configured seed is never mistaken for deterministic model generation.

These corrections are compatible with the existing Agent Evaluation v1 contracts. They use current `environment_digest`, run evidence artifacts, scorer `input_evidence`, Executive/OHF identity, Provider Control, and protected host-capacity identity rather than introducing a new lifecycle, evaluator, reviewer registry, host registry, or schema v2.

## 2. BLOCKER AR-1 — the six named Q3 holdouts are burned

The public PR already names these supposed sealed holdouts:

- `continuation_recovery_after_context_loss`
- `no_duplicate_plane_under_new_backend`
- `cancel_cleanup_unknown_no_replay`
- `owner_scope_collision_with_green_tests`
- `process_generation_resume_stale_predecessor`
- `wrong_model_or_direct_provider_fallback`

Even though exact fixture bytes and solutions are not published, the semantic failure mode is now visible to implementers and future candidate authors. Git history makes that exposure irreversible. Renaming the cells later would not restore secrecy.

### Ruling

Those six concepts are now **BURNED_FOR_CONFIRMATORY_Q3**. They may be retained as public development/adversarial stressors, but they cannot count as the one-per-family sealed Q3 confirmation set.

The replacement Q3 law is:

```text
public preregistration sees:
  holdout generation id
  family membership
  immutable commitment/digest
  scorer/validity policy digest
  exposure state = SEALED

candidate implementers / harness authors see before Q3:
  no holdout semantic title
  no fixture bytes
  no seeded defect manifest
  no expected state transition
  no hidden solution / expected-contract body

private Agent Evaluation owner root contains:
  exact immutable holdout bytes
  expected contract / defect manifest
  author + independent leakage-review provenance
```

The Agent Evaluation owner must create a **new holdout generation after candidate implementation is frozen** or prove an already-existing unexposed private generation. A public commitment is recorded before provider execution. Any semantic or byte exposure to a candidate implementer before confirmatory scoring burns that generation and requires a new experiment generation; no post-exposure patch may be relabeled as the original confirmation.

This is not a new secret store. Use the existing private Agent Evaluation artifact root / corpus governance and its existing immutable artifact/digest machinery.

## 3. BLOCKER AR-2 — factor-locked execution needs exact opaque substrate identity

Current Agent Evaluation configuration v1 intentionally stores a broad `execution.auth_realm_class` and a capabilities `environment_digest`. Current run receipts add process and native-session fingerprints. That is sufficient for the historical contract, but the new causal harness experiment would overclaim if two arms can silently land on different provider principals or physical host generations while still sharing the same broad class.

Protected source now also has canonical host-capacity identity with opaque `host_ref`, `boot_ref`, `capacity_pool_ref` and immutable snapshot digests. Rich OHF already has provider-account/realm requested-vs-observed semantics. Reuse those owners.

### Two experiment modes

Every comparison edge must preregister one of:

```text
FACTOR_LOCKED
SYSTEM_REALISTIC
```

### `FACTOR_LOCKED`

Required for a `MODEL_EFFECT`, `HARNESS_EFFECT`, or crossed `INTERACTION` edge that claims substrate equality.

The environment manifest bound by existing `configuration.capabilities.environment_digest` must include or content-address owner-native artifacts proving, where applicable:

```text
opaque host_ref
boot_ref / host-generation identity
host OS/runtime class
process-isolation class
opaque provider-principal / auth-realm binding digest
provider-realm generation or equivalent action-time identity
provider route/protocol generation
harness/adapter/config/capability/tool identities already specified in Chunks 4–6
```

Do not store account email, credential value, cookie, token, provider-home path, or PII. If the provider owner exposes only a sensitive account identifier, bind a canonical owner-produced digest/opaque ref and preserve the raw value only in its existing protected owner if required.

A host boot change, provider principal/realm change, provider route change, or other load-bearing binding change during a factor block creates a different configuration/generation or invalidates the intended pair. Do not silently pool it into the same causal edge.

Dynamic load is observation, not route authority. When available, the run evidence should reference the existing canonical host-capacity snapshot/digest and observation time so load/cooling imbalance is visible. Agent Evaluation must not use that snapshot to create its own host allocator.

### `SYSTEM_REALISTIC`

Used for whole-system / production-like robustness comparisons where normal Capacity placement is intentionally part of the treatment.

The environment manifest binds the placement/capability policy, while run evidence records the actual owner-observed host/principal/runtime identities. Host/account variation is then part of the system treatment and **the result may not be relabeled as a pure harness or model effect**.

### Why this does not require Agent Eval v2

The current configuration already binds `environment_digest`; run/scorer evidence already supports content-addressed artifacts. The missing fact belongs inside the environment-attestation artifact and owner-native run evidence, not as new provider-private fields in the top-level configuration.

Only if implementation proves that the v1 evidence graph cannot bind or validate these facts without semantic distortion should a compatible contract extension be proposed.

## 4. BLOCKER AR-3 — independence-sensitive grading needs provenance, not a label

Current scorer-pass v1 correctly requires `grader_identity` for `MODEL_GENERATED` and `HUMAN` methods, but `grader_identity` is a string. String inequality is useful metadata, not proof that the grader is independent from the candidate author/model/session/provider path.

That matters most for the `adversarial_review` family and any subjective adjudication used to compare models/harnesses.

### Ruling

Deterministic scorers remain preferred and need no grader principal.

Any model-generated or human scorer pass that is used as **independent evidence** must reference an owner-proven grader-provenance artifact through the existing `input_evidence` list. The provenance artifact should bind the smallest non-secret identity required to establish the preregistered independence rule, for example:

```text
grader provenance schema/version
grader method = MODEL_GENERATED | HUMAN
exact grader model/provider/harness/configuration identity when model-generated
exact scorer run / native-session or Executive worker/result identity when applicable
human reviewer verified principal/ref when human
candidate author/configuration provenance digest
independence rule applied
owner-native attestation/evidence refs
```

Do not invent a reviewer registry. Provider/session facts come from the existing runner/OHF/Executive/provider owners; GitHub identity comes from GitHub when GitHub review is the evidence; human identity remains with the existing authorized identity owner.

If the required provenance cannot be established, the scorer pass may still be stored as an attributed opinion but must be classified **NONINDEPENDENT / NOT_ELIGIBLE_FOR_INDEPENDENT_REVIEW_DIMENSIONS**. It cannot close an independence gate merely because `grader_identity` contains a different string.

The task-specific scorer/summary verifier should fail closed for independence-required dimensions when the provenance artifact is absent, malformed, mismatched, or self-referential.

This also remains compatible with scorer-pass v1: `input_evidence` already binds immutable artifact refs/digests and `scorer_configuration_digest` can bind the preregistered grader policy.

## 5. MAJOR AR-4 — experimental seed is not provider RNG proof

The configuration contract contains a randomness seed and sampling-parameter digest, but many providers/harnesses do not expose or honor an exact deterministic generation seed.

Therefore preregistration must distinguish:

```text
experiment/block/order randomization seed
provider sampling parameters
provider RNG seed requested (optional)
provider RNG seed acceptance/effect observed (optional/unknown)
```

A provider that does not expose deterministic seeding is not invalid merely for that reason. Its stochasticity is handled by preregistered replicates and paired/block order. Do not describe equal configuration seeds as equal model randomness unless the provider-native surface proves that property.

## 6. Consequences for the 24-scenario registry

The **six families and 18 public development cases remain useful**.

The six formerly named holdout concepts are reclassified as public/burned stressors. They may be used in Q1/Q2 development or mutation testing but not in Q3 confirmation.

The eventual Q3 registry still contains six holdouts total, one per family, but only opaque holdout generation IDs + commitments may appear in public preregistration before execution. Their semantic titles and bytes must stay private until the frozen confirmatory wave consumes them.

Therefore the phrase "24-scenario registry" should be interpreted as:

```text
18 public development scenarios
+ 6 private sealed confirmatory scenarios
= 24 governed scenarios in the accepted generation
```

The current public document does **not** itself contain the final six confirmatory scenario identities.

## 7. Consequences for causal claims

A comparison may be labeled:

- `MODEL_EFFECT` only when model is the intended changing factor and factor-locked environment identity is proven;
- `HARNESS_EFFECT` only when harness/environment is the intended changing factor and exact model/provider/principal/host constraints are proven;
- `INTERACTION` only for an identified crossed block under the same factor-lock discipline;
- `WHOLE_SYSTEM` whenever private Fable state, normal Capacity placement, provider/account variation, native-helper differences, unobservable config, or another load-bearing factor cannot be held/proven equal.

No favorable result may upgrade itself from `WHOLE_SYSTEM` to a cleaner causal class after observation.

## 8. Updated A0/A1/A2 gate

The previous local DAG remains, with this amendment inserted before implementation:

```text
A0.1 incumbent Agent Evaluation owner reconciles stale organizational projection
A0.2 author-side hardening amendment applied (this record)
A0.3 independent review remains requested and may add/close findings
A0.4 decision owner freezes accepted experiment claim classes and owner bindings

then:
A1 additive public corpus/scorers + NEW private holdout generation
A2 environment manifest/evidence identity with FACTOR_LOCKED vs SYSTEM_REALISTIC modes
```

Current Chairman direction permits author-side forward motion while A0.3 is pending; that does not make A0.3 complete or independent evidence.

## 9. Self-review disposition after repair

**Author-side recommendation: PASS WITH THESE CORRECTIONS INCORPORATED AS CONTROLLING AMENDMENT.**

Architecture still does not justify a universal Harness OS, Worker v2, OHF v2, Agent Eval v2, second evaluation service, second reviewer registry, or evaluator-owned routing.

Verified at source in this review:

- Agent Eval configuration v1 has `auth_realm_class` + `environment_digest` rather than exact provider-principal identity;
- Agent Eval run v1 separately carries process/native-session fingerprints and content-addressed evidence;
- scorer-pass v1 carries arbitrary `grader_identity` plus content-addressed `input_evidence`;
- protected MH1/host-capacity source now owns opaque `host_ref`/`boot_ref` and snapshot identity;
- rich OHF owns requested-vs-observed provider account/realm semantics;
- #600 still owns orchestration-parity integration planning;
- #660 still owns provider-neutral rich proxy work and remains `BUILT_NOT_PROVEN / PRODUCTION_INERT`.

Still unverified:

- any actual Fable/model harness effect;
- whether exact Fable model/private environment can be factor-locked;
- DSH/OpenCode behavioral quality;
- provider-plan legality for future cross-engine arms at action time;
- effective environment implementation for Claude/OpenCode/DSH;
- independent review of this amended candidate;
- owner adoption by the incumbent Agent Evaluation program;
- any production routing consequence.

## 10. Exact next action

1. update PR #687 body/review packet so this amendment is part of the candidate and the leaked holdout concepts are explicitly burned;
2. notify the incumbent Agent Evaluation owner on its existing carrier that A1/A2 must consume this amendment rather than the older public holdout labels;
3. let the already-requested independent reviewer review the new head rather than creating another reviewer operation;
4. once owner reconciliation/adoption is explicit, implement the smallest **non-provider** A1/A2 slice through the existing Agent Evaluation owner: public corpus/scorer additions, opaque private holdout commitments, environment-manifest/attestation validation, and negative tests only;
5. provider/model turns remain a separately preregistered and authorized later wave.
