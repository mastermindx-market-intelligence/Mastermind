# Executive Job readback P3 — shared reason and clock contracts

**Owner:** existing Runtime producer `control_plane/executive_runtime.py`, existing Executive
MCP consumer, and existing Web CEO Job read gateway. No additional state,
credential, retry, identity, submission, or publication plane.

## Verified process-absence reasons

The Runtime stores two pre-existing LOST envelope families:

* Lease reconciliation: exact `{reason: lease_expired | ohf_lease_expired_fenced,
  expired_at_ms: nonnegative int64}`. OHF's *active* lease-expired fence must
  remain readable and is **not** a terminal Attempt until Runtime finishes it.
* Verified process absence: historical exact
  `{reason: bounded human-readable text, verified_process_absent: true}`.
  These rows already exist; rejecting or rewriting them would lose genuine
  historical lost→queued recovery.

**New Runtime writes** for process absence use the same readable `reason` but
add machine-readable `reason_code`. The canonical supervisor restart phrase
maps to `supervisor_restart_absence`. Known provider-session phrases map to
`provider_session_absence`. Any other *bounded* diagnosis is explicitly typed
`other_verified_absence`, never falsely certified as a known source. The new
shape has **exactly** those three fields. The reason must be trimmed, printable,
nonempty, and at most 1,024 codepoints. The Runtime refuses malformed new
diagnostics before touching a Job or Attempt.

The Web CEO reader uses exactly the same shared parser for legacy and new
errors. Mismatched `reason`/`reason_code` and extra fields are rejected. A
historical reason without the new code remains a *legacy diagnostic*, not a
newly certified typed source. The code is not proof of process absence: only
the existing durable PID/boot/start/provider-session check and lease fencing
authorize `mark_lost`; no read-side authority may infer a missing process
from text alone.

## Clock-skew contract

The shared Runtime/read gateway policy is **at most five minutes ahead of the
local trusted UTC observation for an *event***. Job creation/update, Attempt
start/heartbeat/finish are events. Existing historic times remain valid: **no
new minimum history age**. The Runtime's production clock validates the
generated observed timestamp against this shared ceiling. Explicitly injected
Runtime clocks in controlled simulations remain their own time authorities,
not a claim about the host's real clock.

An Attempt's `lease_expires_at` is an *authorization schedule*, not an
observation: it has a separate **30-day future horizon**. Empty nullable
Attempt timestamps retain the exact Runtime `""` serialization. Existing
UTC ISO parsing and created≤updated / started≤finished checks continue to
apply. The source-bound Web reader rejects implausibly far-future generated
event timestamps even when their text is syntactically valid and all bounded
latest/history projections agree.

The same 30-day lease lookahead is enforced *before mutation* by Runtime
claim, adoption, and heartbeat extension. It is an upper bound, **not** a
new entitlement to long leases; existing worker admission and fencing still
own actual durations. If the estate must lawfully admit longer leases, change
the shared constant and all three producer boundaries together, with a
reconciliation plan for older persisted leases.

## Compatibility / proof boundaries

`tests/test_executive_readback_contract_p3.py` proves a real Runtime →
readonly MCP → Web consumer roundtrip, v1 historical free-text acceptance,
v2 mismatch/extra-key rejection, original expiry/fence envelopes, bounded
producer diagnostics, event-vs-lease future tests, and acceptance of old UTC
history. `tests/test_executive_job_terminal_result_read.py` retains the
canonical #1726 lost→queued proof with the new machine code.

Production `executive_job(JOB-002)` and `JOB-025` live acceptance is **not**
established by source tests; the guarded installed release and readiness
attestation remain separate owners under MAS-158. This change must be treated
as a separate source PR, not a retrospective edit of merged #1726.
