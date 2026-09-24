# Project Recovery Sentinel R8 — Post-Merge Source-Law Amendment

**Date:** 2026-08-27  
**Owner:** Sol, AI CEO  
**Chairman authority:** explicit approval in the current governing Sol conversation  
**Operation key:** `project-recovery-r8-postmerge-amendment-20260827-sol-001`  
**Protected Skillpack:** `Mastermind@a6fde00413979ede525033053bc09a495d6e5fbd`, `mastermind.sol_skillpack.v1` v1.0.0, bootstrap major 1  
**Amends:** Project Recovery Sentinel R8 package merged in #171 as `a44348f6e87614d925f2794f817ff0f7b35b155b`  
**Status:** Chairman-approved source-law amendment; records only. No runtime, recovery finding, Agenda item, Linear projection, Slack message, worker claim, or production capability is made live by this document.

## 1. Purpose and precedence

The #171 architecture remains accepted. Adversarial post-merge review identified three implementation-plan defects that could cause false recovery, duplicate work, or priority laundering if implemented literally.

For the three topics below, this amendment has higher technical precedence than the corresponding #171 implementation-plan clauses:

1. `docs/superpowers/plans/2026-08-27-project-recovery-r8-program-registry-source.md` (R8-B2 semantic-program source);
2. `docs/superpowers/plans/2026-08-27-project-recovery-r8-recovery-core.md` (R8-A recovery classifier);
3. `docs/superpowers/plans/2026-08-27-project-recovery-r8-improvement-agenda.md` (R8-C Agenda ingestion).

All other #171 architecture, dependency, owner, no-rebuild and acceptance law remains unchanged.

A future operator must read #171 plus this amendment before implementing B2, R8-A or R8-C. If accepted B1/B2/R1 interfaces differ at pickup, reconcile against those accepted interfaces rather than copying a draft shape.

---

## 2. R8-B2 correction — consume canonical lifecycle ontology; preserve legacy key-join behavior

### 2.1 Defect

The merged B2 plan proposed a second hard-coded constant:

```python
PROGRAM_LIFECYCLE = {"operating", "building", "planned", "parked", "dormant", "deprecated"}
```

Those values are already canonically declared by Macro `config/mastermind_programs.yml` under `ontology.lifecycle_states`. Copying them into Agent OS would create a second lifecycle-vocabulary owner that can silently drift from the semantic registry.

The same plan also proposed implementing legacy `_load_programs()` as a wrapper over the richer `_load_program_registry()` envelope. Current Agent OS deliberately uses `_load_programs()` as a tolerant, fail-open **key-membership join**. Making that legacy join depend on every richer metadata field (`name`, `lifecycle_state`, `scope`, `kind`, `category`) would turn an unrelated metadata defect into a new fleet-wide program-reference failure.

### 2.2 Binding correction

- `config/mastermind_programs.yml` remains the sole semantic-program and lifecycle-ontology owner.
- R8-B2 must read and validate the registry's own `ontology.lifecycle_states` for lifecycle membership. Do not duplicate the set in Python as an independent authority.
- The richer `agentos.program_registry.v1` projection may fail closed **for that projection** when required projected metadata or ontology is malformed.
- Existing `_load_programs()` key-membership behavior must remain backward-compatible and fail-open exactly as today. A malformed optional projected metadata field must not cause an otherwise-known program key to disappear from legacy Agent OS validation.
- A shared raw YAML read may be factored, but the key-only join and the richer projection must retain distinct failure semantics.
- No new registry file, database, lifecycle enum, scheduler, recovery state or parser is authorized.

### 2.3 Required falsifiers

B2 tests must prove:

1. changing the registry's authored `ontology.lifecycle_states` changes what lifecycle values the projection accepts without editing Python constants;
2. a program row with a valid key but malformed optional/richer projected metadata can make `program_registry.available=false` while legacy `_load_programs()` still exposes that exact key for existing referential validation;
3. missing/unreadable registry remains fail-open for the legacy join and explicit unavailable for the richer projection;
4. exact program/workstream joins remain key-only; no title similarity.

---

## 3. R8-A correction — terminal exact bindings are a source disagreement, not an orphan commission

### 3.1 Defect

The merged R8-A plan defined `ORPHAN_BUILDING_PROGRAM` as a lifecycle=`building` program with no **nonterminal** workstream. That collapses two materially different states:

- a genuinely building semantic program with **no exact workstream binding at all**; and
- a semantic program still marked `building` whose exact workstream bindings all exist but are terminal.

The second case can be stale semantic metadata or a completion-record disagreement. Calling it `RECOVERY_REQUIRED` would authorize the recovery system to recreate work that may already be complete.

### 3.2 Binding correction

Use three exact states:

```text
building + zero exact workstream bindings
    -> ORPHAN_BUILDING_PROGRAM / RECOVERY_REQUIRED

building + >=1 exact binding + >=1 nonterminal binding
    -> not orphan; classify the bound workstream frontier normally

building + >=1 exact binding + all exact bindings terminal
    -> PROGRAM_LIFECYCLE_DISAGREEMENT / UNKNOWN_RECONCILE
```

`PROGRAM_LIFECYCLE_DISAGREEMENT` is derived evidence only. Its machine next action is: reconcile the semantic registry lifecycle against terminal Agent OS/GitHub/proof truth; **do not create a new workstream or commission** until the owner disagreement is resolved.

This finding outranks any recovery commission for the same program subject. It does not mutate the registry or Agent OS automatically.

### 3.3 Required falsifiers

R8-A tests must prove:

1. zero exact bindings for a real `building` program can still yield `ORPHAN_BUILDING_PROGRAM / RECOVERY_REQUIRED`;
2. one terminal exact binding yields `PROGRAM_LIFECYCLE_DISAGREEMENT / UNKNOWN_RECONCILE`, never `ORPHAN_BUILDING_PROGRAM`;
3. multiple terminal exact bindings behave the same;
4. one nonterminal exact binding suppresses the lifecycle-disagreement path and uses normal frontier classification;
5. similar names/titles never count as bindings;
6. `UNKNOWN_RECONCILE` never auto-commissions, creates a workstream, or changes semantic lifecycle.

---

## 4. R8-C correction — recovery evidence is CEO review input, not automatically a code change; uncertainty must not dominate firm evidence

### 4.1 Defect

The merged R8-C plan mapped every recovery-derived Agenda item—including `CEO_ATTENTION` and `UNKNOWN_RECONCILE`—to the existing `code-change` fix type and proposed a class weight of 92. Under the current Agenda formula that can make an uncertainty/reconciliation item score around 99, above firm validation, unarmed-posture and lifecycle evidence.

That would launder "we do not yet know who owns/runs this" into both an implementation-shaped task and the top ranked company fix.

### 4.2 Binding correction: fix type

Add one bounded Agenda advisory vocabulary value:

```text
fix_type = ceo-review
```

All `project-recovery` source items use `ceo-review` at ingestion. Recovery assessment evidence is not itself an implementation instruction. Sol may later create an ordinary bounded architecture/build/research commission after reconciling the item.

`ceo-review` is advisory only. It must not be accepted by `self_tune` or any automatic executor. Existing owner law remains: project-recovery rows are `owner=ceo-sol`.

### 4.3 Binding correction: ranking prior

Freeze the initial recovery ranking prior as:

```python
_CLASS_WEIGHT[CLASS_RECOVERY] = 82
_RECOVERY_SEVERITY = {
    "RECOVERY_REQUIRED": 0.8,
    "CEO_ATTENTION": 0.5,
    "UNKNOWN_RECONCILE": 0.2,
}
```

With the existing Agenda formula this produces base scores of 90, 87 and 84 respectively before existing age/readiness behavior. The purpose is not to make recovery weak; it is to ensure uncertainty does not automatically outrank firmer validation/safety/lifecycle evidence merely because it is a recovery item.

No numeric priority enters R8-A. The Improvement Agenda remains the sole ranker.

### 4.4 Required falsifiers

R8-C tests must prove:

1. every `project-recovery` row uses `fix_type=ceo-review`, never `code-change`;
2. no project-recovery row is `owner=self-tunable` and `self_tune` cannot consume `ceo-review`;
3. otherwise-equivalent `UNKNOWN_RECONCILE` does not outrank firm current validation/unarmed/lifecycle evidence solely from class prior;
4. `RECOVERY_REQUIRED` remains high enough to surface near the top when its evidence is firm;
5. ranking/age/dedup still occur only through the existing Agenda engine and existing weekly schedule;
6. no new scheduler, queue, auto-dispatch, Linear issue, Slack send or Wake path is created.

---

## 5. Unchanged architecture and no-rebuild boundaries

This amendment does **not** change:

- Executive OS ownership of Job/Attempt/Worker/Event lifecycle;
- Agent OS ownership of durable organizational workstreams/decisions/discoveries/handoffs;
- Macro ownership of the semantic program registry;
- Mastermind ownership of R8-A classifier, Improvement Agenda and Control Room projections;
- exact-key joins only;
- typed waits from R8-B1;
- R8-D Linear dependency gates or its label/status refusal;
- R8-F Slack dependency-held law;
- R8-G fresh-Sol/full-autonomy acceptance law;
- the requirement that #162/Fresh-Sol be independently accepted before R8-G reuses it;
- the prohibition on a Recovery database, second priority engine, scheduler, queue, identity plane, Slack inbox or auto-worker assignment.

## 6. Completion boundary

Landing this amendment repairs **source law only**. It does not make B2, R8-A, R8-C or Project Recovery `BUILT` or `PROVEN_LIVE`.

After merge:

1. R8-B1 may continue on its existing Macro carrier under its accepted scope.
2. R8-B2 must implement the corrected ontology/compatibility law above.
3. R8-A remains held until accepted R1 + B1 + B2 interfaces exist.
4. R8-C remains held until accepted R8-A.
5. R8-G remains the final fresh-Sol + real claimed-handoff acceptance gate.
