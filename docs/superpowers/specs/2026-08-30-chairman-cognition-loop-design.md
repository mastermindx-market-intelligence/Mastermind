# Chairman Cognition Loop — Architecture and First Vertical

**Date:** 2026-08-30  
**Chairman:** Chris  
**Owner:** `SOL:META-CEO:MASTERMIND`  
**Operation:** `mastermind-chairman-cognition-loop-20260830-sol-001`  
**Workstream parent:** existing `WS:CHAIRMAN-CONTROL-ROOM`  
**Cognition route:** `CHAT_PRO_DEFAULT`  
**Current capability:** `BUILT_NOT_PROVEN / PRODUCTION_INERT`

## 1. Outcome

Transfer recurring chief-chairman-engineer cognition from Chris into the existing logical Meta-CEO
office. The system must reconstruct current company truth, compare it with the desired future,
identify the binding constraint, preserve materially incomparable strategic alternatives, choose one
bounded transformation inside explicit authority, route execution through existing owners, and learn
from actual outcomes.

Chris remains Constitutional Chairman for terminal objectives, constitutional rules, unbounded
delegation, irreversible decisions, major budget expansion, production-deployment policy and
live-capital authority.

## 2. One office, two modes

Accepted:

```text
Chris, Constitutional Chairman
  -> SOL:META-CEO:MASTERMIND
       CHAIRMAN_COGNITION
       CEO_EXECUTION
  -> existing Program CEO / Project Sol / Integrator / Auditor topology
```

Rejected: a separate Meta-Chairman agent, strategy lifecycle, scheduler, queue, authority registry,
session registry or memory database.

**No `chairman_brain.db` is authorized.**

## 3. Existing owners remain canonical

Chairman Cognition composes, but does not replace:

- Strategic State and Charter for objectives and standing boundaries;
- Agent OS for durable workstreams, decisions, discoveries and handoffs;
- Executive OS for Job / Attempt / Worker / Event lifecycle and CEO admission;
- GitHub for implementation, CI, review, release and evidence;
- Linear for selected portfolio projection only;
- Capacity and Model Router for provider/account/surface eligibility;
- RuntimeBinding for the exact current execution surface;
- Wake for attention and delivery identity;
- Executive Steward and Control Room for normalized whole-company reads;
- Executive Attention Frontier for advisory attention ordering;
- Runtime Observability for diagnostic evidence;
- Operation Assurance for liveness/soundness evidence.

Slack and Linear prose remain transport/projection evidence. They do not become authority or repair a
stale canonical fact merely because they are recent.

## 4. Strategic option model

Each option names:

```text
observable outcome
action and reversibility
effect state
source references
canonical affected-scope references
stable operation and carrier
repository/path scope
expected head where applicable
budget and active-child ceiling
stop condition / rollback / falsifier
classification source
change classes and affected departments
benefit and cost dimensions
```

The action vocabulary includes `PORTFOLIO_HOLD`, research/audit/architecture analysis, source branch
and merge, Executive child commission, reversible runtime canary, Program start/pause/resume/retire,
Program combine/split, resource reallocation and organizational restructure.

New Programs and Executive children require an explicit `NEW_CHILD` carrier state. Existing effects
use allowed exact-carrier prefixes and cannot silently fail over.

## 5. Value, authority and serviceability are separate

A high-value option is not authorized merely because a model prefers it. A valid delegation envelope
does not cure stale evidence, `EFFECT_UNKNOWN`, a known-applied effect, an ambiguous carrier, missing
canary controls or a prohibited strategic constraint.

A1 always emits `execution_authority_granted=false`. The actual effect owner must reread current
canonical state and authority immediately before mutation.

## 6. Strategic frontier

A1 computes a genuine Pareto frontier over explicit benefit and cost dimensions. It has no hidden
universal score and no silent tie-break. Unknown dimensions prevent false dominance. A mechanical
recommendation exists only when exactly one eligible option remains non-dominated.

`PORTFOLIO_HOLD` remains a first-class no-effect alternative, so the system can decide not to start
more work.

## 7. Delegation envelope

`mastermind.chairman_delegation_envelope.v1` projects explicit Chairman authority. It binds:

```text
authority source references
SUPERVISED_LIVE_CANARY or BOUNDED_AUTONOMOUS mode
allowed actions and reversibility
repository/path scope
canonical affected-scope prefixes
allowed exact-carrier prefixes
budget and active-child ceilings
exact-carrier requirement
expiry
```

The default first operating mode is `SUPERVISED_LIVE_CANARY`. There is **no mandatory multi-week shadow**. The first integration targets **one supervised live reversible canary** with exact stop,
rollback and falsifier controls.

## 8. Source and effect semantics

- future-dated evidence is malformed;
- stale, conflicting or unknown load-bearing evidence refuses the dependent option;
- `EFFECT_UNKNOWN` requires same-carrier reconciliation before any retry;
- a known-applied effect is terminal and never re-enters a frontier;
- duplicate control planes remain refused or Chairman-only, never delegated;
- source branches and merges require exact expected heads;
- prefix checks use exact-or-delimited descendants rather than raw string starts-with behavior.

## 9. R2 — total Strategic State constraint coverage

R2 makes the current Strategic State rules operational rather than decorative.

### 9.1 Constraint map binding

The input requires `strategic_constraints_source_ref`. It must resolve to exactly one CURRENT,
load-bearing `STRATEGIC_STATE` receipt. The exact canonical constraint map is **content-bound** to
that receipt through:

```text
constraints-sha256:<sha256(canonical constraint map)>
```

A1 recomputes the digest. A caller cannot swap constraint values under a current-looking receipt.
The packet exposes the verified constraint digest and the exact source reference.

### 9.2 Classification binding

Every option has `classification_source_ref`, `change_classes` and `affected_departments`.
Classification is not trusted merely because the option says it is maintenance rather than a new
feature. The classification source must be cited, load-bearing and owned by an accepted canonical
classification owner: Chairman directive, Strategic State, Agent OS, Executive OS, GitHub, Steward,
Control Room or Operation Assurance.

The classification payload is content-bound through:

```text
classification-sha256:<sha256(canonical classes + departments)>
```

Slack and Linear cannot be classification owners. A stale classification source makes the option
stale; a missing, advisory-only, wrong-owner or mismatched binding makes the input invalid.

Closed classes include:

```text
NEW_FEATURE
MAINTENANCE_REPAIR
EXISTING_CAPABILITY_COMPLETION
ARCHITECTURE_RECORD
RESEARCH
RELEASE
RUNTIME_CANARY
ORGANIZATIONAL_EXPANSION
RESOURCE_REALLOCATION
UNKNOWN
```

`UNKNOWN` is exclusive. A modifying option must be classified. `ORGANIZATIONAL_EXPANSION` must name
an affected department.

### 9.3 Current constraints

All six current constraints are required and evaluated:

```text
autonomous_production_deploy
autonomous_live_capital_execution
duplicate_control_planes
marketing_org_expansion_before_distribution_proof
new_feature_expansion
unbounded_autonomous_strategic_modification
```

`NEW_FEATURE` activates the constrained new-feature rule. Marketing
`ORGANIZATIONAL_EXPANSION` activates the prohibited distribution-proof rule. Safe completion,
maintenance, research, release and runtime-canary classes do not accidentally become expansion.

A future constraint never disappears. Its selector is `UNKNOWN`; for modifying work, prohibited
refuses, constrained requires Chairman, and permitted may continue through every other gate while the
unknown applicability remains visible. Read-only work remains no-effect.

### 9.4 Complete output

Every adjudication emits sorted, digest-covered `constraint_results` containing ID, current level,
applicability and effect, plus one exact `blocking_constraint`. Final precedence is:

```text
REFUSED > CHAIRMAN_REQUIRED > eligibility
```

All results remain visible even when one blocker determines the final disposition.

## 10. A1 boundary

A1 is a pure deterministic standard-library core and JSON CLI. It does not gather company sources,
call a model, write a file, invoke a connector, create a Job, select capacity, bind a session, send
Slack, update Linear or Agent OS, merge, deploy, trade or persist memory.

Its schemas and tests live in:

```text
control_plane/chairman_cognition.py
scripts/chairman_cognition.py
tests/test_chairman_cognition.py
tests/test_chairman_cognition_hardening.py
tests/test_chairman_cognition_source_contract.py
```

## 11. Program sequence

```text
CCL-A1 deterministic decision core
-> CCL-A2 owner-preserving source composer and trusted bindings
-> CCL-A3 one real supervised reversible canary
-> CCL-A4 prediction/outcome learning through Agent OS + GitHub
-> CCL-A5 zero-touch integration through existing Executive/Capacity/Runtime/Wake owners
-> CCL-A6 bounded multi-program portfolio autonomy
```

A2 must migrate to the R2 grammar on its existing carrier. It must emit the Strategic State source
binding, full six-constraint map, classification facts and classification bindings. A1 protection
precedes that migration.

## 12. Completion ruler

A1 merge proves only a protected, production-inert decision contract. The overall Chairman outcome is
complete only when a real current-source cycle selects a bounded transformation, the existing owner
executes and reconciles it, learning changes the next decision, and Chris performs zero routine
message carriage, account selection, session hunting, watcher repair, carrier archaeology or
initiative babysitting across a representative interval.
