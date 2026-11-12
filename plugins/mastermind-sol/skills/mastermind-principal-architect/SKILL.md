---
name: mastermind-principal-architect
description: Use when Mastermind work requires system boundaries, contracts, ownership, cross-system integration, migrations, or a consequential architectural decision rather than a mechanical edit.
---

# Resolve a Mastermind Architecture Decision

## Mandatory current-source gate

Reuse the verified pin for the mission; verify compatibility. Read protected Mastermind `master` and run `bootstrap-mastermind` only
at unfamiliar entry/recovery without a usable pin, or a material governing-procedure change. Load
`docs/sol_skills/INDEX.md` and the needed companions from that same exact commit; never mix revisions.
Read `../../references/authority-boundaries.md` once before interpreting any app, record, or action as authority. This skill grants no authority; GitHub owns source/evidence and existing owners retain runtime, custody and effects.
A worker return, tool call, new turn or phase completion alone does not restart bootstrap. If no
verified compatible pin can be established, modifying workflow is unavailable for actions depending
on that procedure. A failed refresh does not erase a usable pin for independent work whose governing
constraints are unaffected. Apply gates only to the actual action under INDEX modification scoping.

## Do not use

Do not redesign a system for a local bug with an established contract. Do not turn a research question into infrastructure, or a role label into runtime or merge permission.

## Working method

1. Start with the consuming user or machine journey and the failure that matters. Read the smallest existing implementation and governing contracts that can establish current owners. Separate observed behavior, accepted design, candidate proposals and missing evidence.
2. State invariants before components: who owns each fact, identity, admission, effect, retry, durability and publication. Trace one normal journey and one failing journey across those boundaries. Reuse an adequate existing owner; convenience does not justify a parallel queue, registry, cache-as-authority or state machine.
3. Compare credible alternatives, including extending the current design and making no change. Explain trade-offs in correctness, simplicity, latency, cost, operability and user value. Present the strongest counterargument to the preferred choice and its deciding falsifier; do not invent numeric certainty.
4. Specify inputs, outputs, versions, units, time/freshness, nulls, corrections and error behavior. Examine response loss, partial writes, duplicate delivery, stale bindings, concurrent writers, permission denial, restart and rollback. Separate transport success from the actual effect. State what remains unknown.
5. Define a migration that keeps existing consumers coherent: compatibility period where necessary, rollout boundary, data reconciliation, rollback or forward repair, observability and removal of superseded behavior. Avoid dual authoritative writers disguised as migration scaffolding.
6. Choose the smallest vertical slice that unlocks the named capability with a real consumer, projection, tests and proof. Define negative tests that discriminate the proposed design from the tempting unsafe alternative. Keep acceptance and independent review with their current owners.

## Evidence and output

Produce a decision-ready architecture record: problem and consumers, current owners, invariants, alternatives, recommendation, contract changes, migration, failure behavior, falsifiers, ordered implementation and acceptance evidence. Cite exact source revisions and relevant primary technical evidence. Separate source candidate, implemented behavior and production proof. Continue the parent delivery assignment after a design artifact unless its actual scope ends at accepted design.
