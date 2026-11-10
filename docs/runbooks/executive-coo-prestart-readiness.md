# Executive COO pre-start workspace readiness

## Capability

The existing Executive control service must be able to advance a usable admitted
root while a higher-priority root has an unavailable initial workspace. This is
not a second scheduler or a new admission path. A published handoff or manual
placement request is not, by itself, an admitted Executive Job.

The existing READY/canary, autonomy receipt, host binding, worker composition,
serialized dispatch, review and effect-reconciliation gates remain controlling.
Nothing in this change enables those gates or changes an installed release.

## Narrow eligibility rule

The existing priority-ordered, bounded root scan may defer a root only when all
of these current owner facts hold:

- Its canonical status is QUEUED.
- Its attempt count is zero and its current Attempt is absent.
- The existing Runtime has no child Job and no Attempt record for that root.
- The same initial-workspace validator used immediately before execution refuses
  its assigned credentialless workspace or its clean, exact reviewed-base state.

Selection and execution share `_require_initial_coo_workspace`; the real action
still revalidates. The root stays QUEUED. The assigned directory is never cleaned,
reset, replaced or moved by this behavior. Priority order and the existing root
scan bound do not change.

A root with an existing child or Attempt is **not** eligible for this deferral.
Active work, historical execution, lost replies and ambiguous starts keep the
existing exact reconciliation path. A failed post-claim start still quarantines
the service rather than starting unrelated replacement work.

## Diagnostics and correction

The selector is read-only. Its caller-owned refusal map exists only for the
current tick. The tick validates the current autonomy receipt before recording
any refusal, then uses the existing idempotent `COO_SERVICE_TICK_REFUSED` event
owner. A refusal contains the canonical root reference and closed error/type
projection; it does not persist arbitrary exception text.

This does not create `COO_CYCLE_BLOCKED` or a persistent exclusion list for an
unusable initial workspace. Once the legitimate workspace owner restores valid
input, the same root is eligible at its original priority on a subsequent scan.
No requeue, new admission, cache reset, provider switch or Chairman CONTINUE is
needed for that input correction. A diagnostic-write failure prevents that tick
from claiming an unrelated root as the failed action.

If every inspected never-started root is unusable, status reports a diagnostic
tick and an explicit initial-workspace error. It does not claim execution.

## Boundaries

This correction does not implement cross-host placement, provider enrollment,
quota acquisition, admission of a human-readable packet, or unrestricted fan-out.
It does not relax the existing bounded-root census. Installed tools, a reachable
local transport and a successfully executed native authoring task are distinct
from a READY and armed Executive dispatcher.

It does not replace source-custody recovery for a job that already has children
or Attempts. It does not retry an uncertain effect or convert a missing receipt
into proof of no effect. Production acceptance still requires the separately
approved installed-path canary.

## Verification

`tests/test_executive_coo_tick_liveness.py` exercises the real background service
with isolated, model-free Runtime fixtures. It covers queued input retained across
service restart, missing and dirty initial workspaces, recovery from corrected
input without manual continuation, original priority, existing-child custody,
disarmed inactivity and quarantine after a durably claimed start loses its reply.
The existing service suite supplies adjacent regressions.

Use an operation-owned temporary root, not a shared pytest cleanup directory:

```sh
T=$(mktemp -d "${TMPDIR:-/tmp}/mmx-coo-proof.XXXXXX")
python3.12 -m pytest -q -p no:cacheprovider --basetemp "$T" \
  tests/test_executive_coo_tick_liveness.py tests/test_executive_service.py
git diff --check
```

Model-free tests prove source behavior, not an installed provider invocation or
an autonomous fleet. Keep source, review, release, installation and acceptance
receipts separate.
