---
name: open-executive-cockpit
description: Use when the Chairman asks what is happening, what needs attention, who owes the next turn, or why a program is blocked.
---

# Open Executive Cockpit

Use when the Chairman asks what is happening, what needs attention, which role owes the next turn, or why a program is blocked.

## Mandatory current-source gate

Reuse the verified compatible mission pin. Read protected Mastermind `master` and bootstrap only
at unfamiliar entry/recovery without a usable pin, or a material governing-procedure change. Load
`docs/sol_skills/INDEX.md` and the needed companions from that same exact commit; never mix revisions.
Action-specific references: `COLD_START.md`, `RECONCILE_STATE.md`.
A worker return, tool call, new turn or phase completion alone does not restart bootstrap. If no
verified compatible pin can be established, modifying workflow is unavailable for actions depending
on that procedure. A failed refresh does not erase a usable pin for independent work whose governing
constraints are unaffected. Apply gates only to the actual action under INDEX modification scoping.

## Required package reference

Read `../../references/authority-boundaries.md` before interpreting any app, record, or action as authority. The reference summarizes canonical ownership; current protected source still controls.

## Input

- optional program, workstream, or responsibility reference;
- the logical `mastermind-steward` app when installed;
- current GitHub, Agent OS, Executive, Linear, and Slack evidence only as required.

## Procedure

1. Call the narrowest Steward read that answers the request.
2. Preserve each fact's canonical owner, source reference, observation time, freshness, unknown or degraded state, and disagreements.
3. Distinguish organizational state, Executive lifecycle, GitHub proof, Linear projection, Slack transport, RuntimeBinding, and attention.
4. Mark old provider or session surfaces `STALE_BINDING`, `SUPERSEDED`, `TERMINAL`, or `NON_ACTIONABLE` only when the canonical join proves it.
5. Explain one exact next lawful action; do not invent priority, worker placement, successor work, or completion.

If the logical Steward app is missing, unavailable, unauthenticated, version-mismatched, or returns an unrecognized schema, return `STEWARD_APP_UNAVAILABLE` or the exact typed degradation. do not infer healthy state from absence and do not silently replace Steward with a new store.

## Output

```text
current protected grounding
responsibility/program/workstream
organizational status
current child Job / Attempt / Worker when known
turn owner and exact action target or UNKNOWN
attention / transport / retry-effect state
GitHub carrier/proof and Linear projection
source disagreements/degradations
exact next lawful action
```

## Forbidden inferences

- `turn_owner = SOL` does not mean every Sol chat may act.
- Slack `ACK`, `START`, or `RESULT` is not Executive runtime truth.
- Linear `In Progress` or `Done` is not execution or acceptance.
- Missing source data is not an empty healthy value.

## Stop conditions

Stop before a modifying semantic edge unless the separately loaded current procedure and canonical exact target authorize it.
