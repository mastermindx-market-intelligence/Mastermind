# Explicit reconciliation of an unfinished Wake

## Capability

`control_plane.wake_dispatcher.reconcile_persisted_nudge` closes one narrowly
proven uncertainty: the original native submission is confirmed ACCEPTED by a
reviewed exact-session read, but its acceptance was not recorded after the
original response was lost. It appends ACCEPTED through the existing Executive
Wake event repository. It never submits a nudge or creates another attempt.

This implements the existing accepted protocol in
`docs/superpowers/specs/2026-08-28-wake-pr3-effect-unknown-reconciliation-amendment.md`,
particularly sections 6 and 8. It is not a new retry controller, event store,
queue, endpoint, permission system, identity, worker, or production activation.

## Explicit invocation only

The existing action-authoritative host supplies the original durable nudge ID,
complete frozen obligation/route group, exact current RuntimeBinding, and the
existing dispatcher with a reviewed read-only `reconcile` implementation.
Those are host-owned facts, not parameters a model can synthesize to gain access.

```python
result = await reconcile_persisted_nudge(
    repository,
    original_obligation_route_pairs,
    nudge_id=original_result.nudge_id,
    dispatcher=qualified_original_dispatcher,
    binding=current_original_binding,
)
```

The ordinary `dispatch_persisted_nudge` path is unchanged. For an unfinished
attempt it still returns RECONCILIATION_REQUIRED without calling the provider.
This function must be deliberately invoked only by an already-authorized owner;
constructing it, installing source, or possessing a nudge ID grants no authority.

The dispatcher retains actual native connection, account, current binding,
permission and observation validation. For a queued Codex route, its existing
client reads `thread/queue/list`; it never adds another item. This coordinator
does not read credentials, resume a session, switch hosts, create connections,
or replace the dispatcher’s current-target guard.

## Outcome and atomicity

The coordinator requires all members of the original coalesced group and rejects
missing/extra members, changed requested obligations, rotated bindings, changed
routes, partial acceptance, closed deliveries and superseded attempts before a
provider read. An older nudge cannot silently select a newer attempt.

The provider result must contain exactly one matching nudge correlation and an
existing typed ACCEPTED receipt. Missing/malformed/negative/unavailable evidence
stays unresolved. DELIVERED and any target-acknowledgement projection are outside
this function’s scope. Acceptance proves neither native pickup nor parent
consumption; the established delivered/acknowledgement owners remain unchanged.

One repository transaction reads the initial group. No transaction spans the
external observation. A second transaction revalidates the whole original group
and atomically appends acceptance for every member. Any intervening canonical
change holds the result, except a matching all-member ACCEPTED winner can be
replayed without another append. Storage failure cannot partially accept a group.
A lost transaction response remains uncertain to that caller; a new caller reads
any committed ACCEPTED result without a provider call.

No provider read seam means RECONCILIATION_REQUIRED. No evidence of a queue item
means unresolved, not permission to submit again. Cancellation propagates and
leaves the original persisted attempt intact. This function never mints
DELIVERED, TARGET_ACKNOWLEDGED, SOURCE_RESOLVED, or a later attempt.

## Source qualification and installation boundary

Source operation: `executive-wake-reconciliation-20261003-c3-001`.
Initial source/procedure base: `bdf2a972e68a70270c24d4b5d61a4d60edc4f288`.
Named consumer: recorded recovery for the queued native client in Mastermind
PR #1156, integrated with the existing messaging mission in #1112 / #703.

`tests/test_wake_explicit_reconciliation.py` uses the actual temporary Runtime,
Wake repository, persisted dispatch, event hydration and transactions. Only
provider observations are fixtures. It covers whole-group/restart recovery,
zero resubmission, incomplete/malformed observations, superseded and revoked
inputs, cancellation, concurrent winners, atomic rollback, and post-commit
response loss. Source validation does not qualify an installed connection or
prove actual Web-to-native-to-original-parent delivery.

Independent review and required current-candidate hosted checks remain release
gates. Installed use additionally requires the existing host’s admission and
current native identity/permission checks. No production call is enabled by this
runbook, and no original unknown production operation is replayed by its tests.
