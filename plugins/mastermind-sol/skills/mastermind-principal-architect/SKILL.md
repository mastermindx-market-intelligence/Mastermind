---
name: mastermind-principal-architect
description: Use when Mastermind work requires system boundaries, contracts, ownership, cross-system integration, migrations, or a consequential architectural decision rather than a mechanical edit.
---

# Resolve a Mastermind Architecture Decision

## Mandatory current-source gate

Run `bootstrap-mastermind` for the task. Read protected Mastermind `master`, record its exact revision, load `docs/sol_skills/INDEX.md` and required companions from that same exact commit, and verify compatibility. Reuse the verified pin and relevant procedures already loaded in the current turn while valid; new-turn recovery must re-establish current source. Material changes use the existing reconciliation procedure. If the read or compatibility fails, modifying workflow is unavailable; bounded read-only analysis may continue with explicit uncertainty.

Read `../../references/authority-boundaries.md` before interpreting any app, record, or action as authority. This skill grants no authority. Current Chairman intent, protected source law and platform permissions govern. GitHub owns source and evidence; existing operational owners retain state, custody and execution.

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
