---
name: open-executive-cockpit
description: Compose the current Chairman and Sol company view through the approved Steward interface without another state store.
---

# Open Executive Cockpit

Use when the Chairman asks what is happening, what needs attention, which role owes the next turn, or why a program is blocked.

## Mandatory current-source gate

Read protected Mastermind `master`, record its exact commit, load `docs/sol_skills/INDEX.md`, `COLD_START.md`, and `RECONCILE_STATE.md` from that same exact commit, and verify compatibility before using packaged guidance. Run `bootstrap-mastermind` first. If compatibility cannot be established, modifying workflow is unavailable.

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
