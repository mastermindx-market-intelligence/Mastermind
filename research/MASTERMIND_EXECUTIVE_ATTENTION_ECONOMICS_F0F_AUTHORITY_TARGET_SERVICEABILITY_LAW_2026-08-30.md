# Executive Attention Economics — F0F Authority, Action-Target & Serviceability Law

**Operation:** `mastermind-executive-attention-economics-20260830-sol-001`  
**Parents:** F0/F0A/F0B/F0C/F0D/F0E  
**Action-time protected source that triggered this amendment:** `mastermindx-market-intelligence/Mastermind@28d365cceaef6efb0a26e0ac9af51ead44695d60`  
**Relevant protected capability:** `control_plane/sol_action_target.py` (`mastermind.sol_action_target.v1`)  
**Status:** `ARCHITECTURE CORRECTION / SPEC_ONLY / RECORDS_ONLY`

This amendment corrects one unsafe simplification in the original F0 freeze before F0 is protected.

## 1. Failure found during current-source reconciliation

F0 originally modeled `RECONCILE_FIRST` and `COVERED_BY_BUNDLE` as mutually exclusive values in the same closed attention-disposition enum as `INTERRUPT_NOW`, `FOCUS_NOW`, and `BATCH_NEXT`.

That is unsafe.

A source-backed emergency can be both:

- genuinely `INTERRUPT_NOW`; and
- currently unsafe/unavailable to act because authority identity, exact Sol action target, source integrity, or effect state needs reconciliation.

If `RECONCILE_FIRST` replaces the interrupt disposition, a compact frontier can accidentally hide the emergency from interrupt counts and concurrent-demand pressure. Conversely, `COVERED_BY_BUNDLE` is a projection relationship, not a statement that the underlying demand ceased to be urgent.

The newly protected Stage-A exact Sol action-target resolver makes this distinction concrete: one can know a Sol-class cognition demand is urgent while the exact action-authoritative Sol runtime is `UNAVAILABLE`, `CONFLICT`, `UNKNOWN`, or this observing actor is not the target. Urgency must survive that fact; action permission must not.

## 2. Corrected V1 model — three orthogonal axes

Where F0 conflicts with this amendment, **F0F controls**.

Each valid demand is represented on three separate axes:

### Axis A — `authority_requirement`

Who/what class of authority must lawfully make the decision or perform the executive cognition/action?

Conceptual values remain source-law mappings such as:

- `CHAIRMAN`
- `SOL`
- `COO_OR_WORKER`
- `EXECUTIVE_PLACEMENT`
- `ADMIN_OR_EXTERNAL`
- `NONE`
- `UNKNOWN`

This is the **authority class**, not a runtime target and not priority.

### Axis B — `attention_class`

How scarce executive cognition should be allocated **given the demand's source-backed timing/impact/autonomy/optionality facts**?

The controlling closed V1 classes are now:

- `INTERRUPT_NOW`
- `FOCUS_NOW`
- `BATCH_NEXT`
- `AUTONOMOUS_CONTINUE`
- `VALID_WAIT`
- `NON_ACTIONABLE`

These classes answer *when cognition matters*, not whether the current actor may safely execute it.

### Axis C — `serviceability`

Can the lawfully required cognition/action path be trusted and used now?

The normalized V1 state is intentionally small:

- `READY`
- `BLOCKED`
- `UNKNOWN`
- `NOT_APPLICABLE`

Typed `serviceability_reasons[]` preserve exact source-owned causes, for example:

- `AUTHORITY_SOURCE_CONFLICT`
- `IDENTITY_SOURCE_CONFLICT`
- `SOURCE_FRESHNESS_UNKNOWN`
- `SOURCE_STALE`
- `ACTION_TARGET_UNAVAILABLE`
- `ACTION_TARGET_CONFLICT`
- `ACTION_TARGET_EVIDENCE_UNKNOWN`
- `EFFECT_UNKNOWN`
- other exact accepted source-owner reasons added through versioned contract review.

`BLOCKED`/`UNKNOWN` never means low urgency. It means **do not pretend the action path is safe**.

## 3. Projection relationship is separate too

Root-cause compaction and service selection are projection relations, not attention classes.

A demand may carry a relation such as:

- `ROOT_VISIBLE`
- `COVERED_BY_BUNDLE -> <bundle_id>`
- `DOMINATED_BY -> <demand_id>`
- `DEFERRED_EQUIVALENT_CONTEXT -> <bundle_id>`
- `DEFERRED_ORDINARY_SERVICE -> <reason>`

The raw demand retains its own `attention_class`, authority and serviceability even when its primary card is represented by a root bundle.

This preserves F0C's omission-receipt law and F0A's requirement that independent interrupt roots cannot be compacted away.

## 4. Protected AD-SOL1 Stage-A resolver is an exact action-target owner, not an EAF-owned authority system

At protected Mastermind `28d365cceaef6efb0a26e0ac9af51ead44695d60`, `control_plane/sol_action_target.py` provides a storeless exact Sol action-target resolution contract:

- exact `root_job_id` is mandatory;
- the root Job -> CEO-seat alias in `SessionTargetRegistry` wins;
- seat/workstream defaults are deliberately not consulted;
- a complete current `RuntimeBindingSnapshot` is required for a confident target;
- missing exact target is `UNAVAILABLE`, not permission to promote a sister Sol;
- missing evidence is `UNKNOWN`;
- duplicate/contradictory binding identity or reasoning surface is `CONFLICT`;
- an observing actor may be `observer_only` even when the target itself is resolved;
- a `SolActionTargetResolution` is evidence, not a reusable authority token; enforcement re-resolves current evidence immediately before action;
- the module owns neither target transfer nor RuntimeBinding persistence.

**EAF must consume this boundary rather than rebuild it.**

### 4.1 Authority class vs exact target

For a valid demand whose canonical authority requirement is `SOL`, EAF may attach an exact Sol action-target projection when the accepted source contract is available.

This does not mean `sol_action_target.py` decides whether the demand belongs to Chairman or Sol. It answers a narrower question: **which exact Sol runtime, if any, is action-authoritative for the already-Sol/root-Job context?**

The correct composition is therefore:

```text
authority_requirement = SOL
attention_class = INTERRUPT_NOW | FOCUS_NOW | ...
sol_action_target = <source-owned resolution or unavailable/unknown>
serviceability = READY | BLOCKED | UNKNOWN
actor_can_act = true | false | unknown
```

Do not collapse these into one `priority/authority` field.

### 4.2 Current capability state matters

The protected AD-SOL1 commit explicitly describes Stage A as `BUILT_NOT_PROVEN / PRODUCTION_INERT`; Stage B target transfer and production enforcement remain gated.

Therefore:

- A1 deterministic logic/tests may integrate or mirror the protected **contract semantics** without claiming live placement/transfer exists;
- A2 real-portfolio shadow may use a Sol action-target fact as authoritative only when its actual source path is available/proven for that episode;
- otherwise preserve `ACTION_TARGET_EVIDENCE_UNKNOWN`/`UNKNOWN` rather than assuming the protected module is already a live end-to-end signal;
- EAF never uses its own urgency to invoke target transfer, promote a sister Sol, create placement, or bypass Stage-B gates.

## 5. Urgent-but-blocked is first-class

Examples:

### 5.1 Urgent Sol decision, exact Sol target unavailable

```text
authority_requirement = SOL
attention_class = INTERRUPT_NOW
serviceability = BLOCKED
serviceability_reasons = [ACTION_TARGET_UNAVAILABLE]
```

Result:

- it remains in the Sol interrupt-root count and concurrent-demand pressure;
- the UI says the exact action target is unavailable;
- existing continuity/placement/target-transfer owners own repair/transfer;
- EAF does not select a sister Sol or ask Chairman to perform a routine Sol decision merely because the Sol target is unavailable.

### 5.2 Urgent decision, authority source conflict

```text
authority_requirement = UNKNOWN
attention_class = INTERRUPT_NOW   # if urgency evidence itself is independently valid
serviceability = BLOCKED
serviceability_reasons = [AUTHORITY_SOURCE_CONFLICT]
```

The emergency remains visible, but no action-authoritative seat is fabricated. The operating surface should say **urgent / authority reconciliation required**.

If the urgency classification itself depends on the conflicted source, then its attention class must degrade according to the exact evidence relationship instead of being guessed.

### 5.3 EFFECT_UNKNOWN

A demand may remain `INTERRUPT_NOW` or `FOCUS_NOW` as cognition pressure while:

```text
serviceability = BLOCKED
serviceability_reasons = [EFFECT_UNKNOWN]
```

This preserves the one-carrier/no-blind-retry law. Urgency does not permit retry/failover.

### 5.4 Observer-only Sol

If the exact target is resolved but the current consuming Sol session is not that binding:

- the frontier may be globally `READY` because a lawful target exists;
- `actor_can_act = false` / source reason `ACTOR_OBSERVER_ONLY` is shown to this consumer;
- this observing Sol may reason/explain within current source law but cannot use EAF as authority to act on the target's behalf.

## 6. `RECONCILE_FIRST` is superseded as a mutually exclusive attention class

The phrase may remain in UI copy or compatibility adapters, but in canonical V1 semantics it is represented by:

```text
serviceability = BLOCKED | UNKNOWN
serviceability_reasons = [...]
```

while the underlying `attention_class` remains independently visible.

Examples:

- `INTERRUPT_NOW + BLOCKED(AUTHORITY_SOURCE_CONFLICT)`
- `FOCUS_NOW + UNKNOWN(ACTION_TARGET_EVIDENCE_UNKNOWN)`
- `BATCH_NEXT + BLOCKED(SOURCE_STALE)`

This is more truthful than replacing all three with one generic `RECONCILE_FIRST` bucket.

## 7. `COVERED_BY_BUNDLE` is superseded as a mutually exclusive attention class

A child symptom may remain `INTERRUPT_NOW` in raw truth while its primary presentation is `COVERED_BY_BUNDLE` under one exact canonical interrupt root. The root bundle remains the visible interrupt; all member urgency/authority/serviceability receipts remain drillable.

If bundle members have different authority or serviceability, the bundle cannot imply one shared action permission. The root card must preserve per-member action boundaries.

## 8. Product consequences

The Control Room card/header must visually separate at least:

1. **Pressure** — interrupt / focus / batch / continue / wait;
2. **Authority** — Chairman / Sol / other / unknown;
3. **Can act now?** — ready / blocked / unknown;
4. **Exact target** — when an accepted owner provides one;
5. **Why blocked/unknown** — exact source-backed reason;
6. **Why now** — independent pressure evidence.

Never use red urgency styling to imply action authorization. Never use grey blocked styling to imply low urgency.

A concurrent-pressure banner counts interrupt roots by `attention_class`, regardless of serviceability, and separately reports how many are blocked/unknown.

Example:

```text
CHAIRMAN: 2 interrupts — 1 ready, 1 authority-blocked
SOL: 3 interrupts — 1 ready, 1 exact-target unavailable, 1 target-evidence unknown
```

## 9. Wire-contract correction

The future EAF v1 result should conceptually carry:

```text
items[]
  demand_id
  responsibility_ref
  authority_requirement
  authority_source
  attention_class
  pressure_reasons[]
  serviceability
  serviceability_reasons[]
  exact_action_target|null
  actor_can_act: true|false|unknown
  factor_vector
  projection_relation
  source_receipts[]
```

The original F0 wire field `disposition` should not force these independent concepts back into one enum.

Compatibility/UI code may derive a human phrase such as `RECONCILE_FIRST`, but it cannot be the canonical information model.

## 10. Adversarial corpus additions

35. source-backed urgent Sol demand + exact Sol target unavailable -> `INTERRUPT_NOW + BLOCKED`, remains in interrupt count, no sister-Sol promotion;
36. source-backed urgent Sol demand + target resolved + observing actor differs -> interrupt remains; target visible; `actor_can_act=false`;
37. source-backed urgent demand + authority conflict -> urgent remains visible while authority/serviceability blocked; no default Chairman escalation;
38. `EFFECT_UNKNOWN` urgent operation -> urgency visible, serviceability blocked, no retry/failover;
39. exact-root bundle with three urgent symptoms, one member target conflict -> one visible interrupt root with all three member receipts and per-member serviceability;
40. ordinary batch item + stale optional impact source but intact authority/identity -> preserve pressure class and typed source issue according to owner freshness semantics; do not silently demote to harmless;
41. protected AD-SOL1 module exists but no live source snapshot for the episode -> target evidence `UNKNOWN`; do not equate `BUILT_NOT_PROVEN` code existence with a proven live target;
42. root Job target missing but workstream `owner: ceo-sol` present -> do not fall back from exact root target to workstream owner for action authority.

## 11. Freeze effect

The accepted V1 architecture is no longer a one-axis "closed disposition list." It is:

**authority class × attention pressure × action serviceability**, plus exact projection/bundle relations.

This correction strengthens the original Chairman outcome: urgent risk cannot be hidden by reconciliation debt, while urgency can never be mistaken for permission to act.
