# Project Recovery R8 — Post-Merge Implementation Amendment

> **For future R8-B2 / R8-A / R8-C operators:** read `docs/superpowers/specs/2026-08-27-project-recovery-r8-postmerge-source-law-amendment.md` before the corresponding #171 plan. This file is records-only and creates no implementation authority by itself.

**Protected planning basis:** `Mastermind@a6fde00413979ede525033053bc09a495d6e5fbd`  
**Amended architecture merge:** #171 / `a44348f6e87614d925f2794f817ff0f7b35b155b`  
**Operation key:** `project-recovery-r8-postmerge-amendment-20260827-sol-001`

## R8-B2 delta

Implementation must satisfy all original B2 requirements **plus**:

1. read lifecycle membership from `config/mastermind_programs.yml -> ontology.lifecycle_states`; do not own a duplicate Python lifecycle set;
2. preserve today's `_load_programs()` key-membership semantics independently from the richer projection's metadata validation;
3. prove malformed richer metadata can degrade `agentos.program_registry.v1` without deleting a valid program key from existing Agent OS referential validation;
4. preserve exact-key joins and explicit unavailable state.

**Expected bounded files remain:** `scripts/agentos.py`, focused Agent OS schema/tests. No recovery classifier/Agenda/Linear/Slack work enters B2.

**Stop:** deterministic current-estate registry projection + compatibility proof + hosted CI; return to Sol.

## R8-A delta

Implementation must satisfy the original R8-A requirements **plus** the following exact program-binding state machine:

```text
building + zero exact WS bindings -> ORPHAN_BUILDING_PROGRAM / RECOVERY_REQUIRED
building + nonterminal exact WS binding -> normal frontier classification
building + exact WS bindings all terminal -> PROGRAM_LIFECYCLE_DISAGREEMENT / UNKNOWN_RECONCILE
```

The terminal-binding disagreement must never create/commission a new workstream. It must emit bounded owner evidence and a reconciliation next action only.

Add `PROGRAM_LIFECYCLE_DISAGREEMENT` to the closed recovery finding vocabulary and test one/multiple terminal bindings, mixed terminal/nonterminal bindings, and similar-name non-joins.

**Stop:** pure classifier + current-estate falsifier; no repair/projection/dispatch.

## R8-C delta

Implementation must satisfy the original R8-C requirements **with these replacements**:

```python
FIX_CEO_REVIEW = "ceo-review"
_CLASS_WEIGHT[CLASS_RECOVERY] = 82
_RECOVERY_SEVERITY = {
    "RECOVERY_REQUIRED": 0.8,
    "CEO_ATTENTION": 0.5,
    "UNKNOWN_RECONCILE": 0.2,
}
```

Every `project-recovery` Agenda item uses `fix_type=ceo-review` and `owner=ceo-sol`. `self_tune` must not accept `ceo-review`. The Agenda remains advisory and the sole ranker; no recovery source is executable merely because it ranks highly.

Add paired ranking tests proving uncertainty does not outrank otherwise-comparable firm validation/unarmed/lifecycle evidence solely from class prior, while firm `RECOVERY_REQUIRED` remains prominently ranked.

**Stop:** Agenda ingestion + existing rank/age/dedup + no-auto-execution proof; reuse the existing weekly job only if the accepted current-assessment provider exists.

## No other amendment

All #171 dependency gates, R8-D/F projection law, R8-E read-only UI law, R8-G fresh-Sol acceptance law, exact-key identity rules, and no-duplicate-control-plane boundaries remain unchanged.
