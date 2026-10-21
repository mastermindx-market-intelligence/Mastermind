# Grok Secretary Mac-local Fabric: bounded retained-result reader

This package is a read-only consumer of the existing Fabric task adapter.
It does not create another Fabric runtime, gateway, scheduler, Job, queue, retry
state, authentication identity, enrollment mechanism or authorization grant.

## Proven context

On October 20, 2026, the actual Slack Secretary Grok Bot app executed a shell
command on the registered m2studio Mac. It reached the installed local Fabric
gateway /readyz and reported ready. The Bot sent one bounded C0 mechanical
request through the pre-existing fabric_task.py adapter, which placed GLM 5.3
Flash on ubuntu3, returned exactly OK, and recorded deterministic acceptance.
The original run ID was grok-secretary-local-canary-20261020-01; its root was
grok-secretary-local-canary-20261020-root. The accepted result and authoritative
evidence are recorded on Mastermind issue #983.

## Read-only usage

Call this module from a trusted source checkout on the same Mac. The
incumbent adapter path and SHA-256 are **pinned in reviewed source** and are not
caller-selectable. Drift requires an owner-qualified update instead of an
automatic arbitrary-file or credential fallback.

    python3 -m integrations.grok_bot_local_fabric.read \
      status --run-id ORIGINAL_RUN_ID --root-id ORIGINAL_ROOT_ID \
      --parent-id ORIGINAL_PARENT_RUN_ID

    python3 -m integrations.grok_bot_local_fabric.read \
      result --run-id ORIGINAL_RUN_ID --root-id ORIGINAL_ROOT_ID \
      --parent-id ORIGINAL_PARENT_RUN_ID

The client launches only the approved installed adapter with Python isolated
flags, an allowlisted environment excluding ambient provider/API secrets, and
a fixed working directory. The subprocess stdout is read with a bounded
buffer, and timeout/error paths terminate the original process group.

The client performs only incumbent adapter status and result calls. Returned
status fields are closed and output is bounded. The output intentionally
**does not expose raw worker result text**: it includes only result length,
SHA-256 digest and the typed content-exposed=false flag because this
Mac-user-local caller lacks a cryptographically authenticated Grok principal.
The original attended Fabric owner remains the only existing route for
reviewed exact result bytes. To provide a Bot with arbitrary result content,
the future authorized Executive principal/result-consumption path must be
qualified instead of adding a caller-selectable show-text flag. For a result, the incumbent
status must prove exact matching root AND immediate parent, TERMINAL state,
integer rc=0, exact terminal `signal=ok`, and actual result availability.
An affirmative acceptance projection additionally requires the SAME full
successful-terminal tuple plus the incumbent `accepted_by` to be `deterministic`
or `reviewer` together with `acceptance_state=ACCEPTED`. A failed or uncertain
run must never report `accepted=true` even if its other acceptance fields
appear valid; contradictory receipts are `UNVERIFIED`. Unknown, pending, changed or mismatched states
fail closed. It never retries a request, starts a child or records acceptance.
Request/result/acceptance are different lifecycle facts.

## Authority and limits

The root ID here is CORRELATION, NOT AUTHENTICATION. Grok Bot's Mac-local shell
runs with the same macOS user permissions as other Bots within that desktop
app. A saved skill that says only Slack Secretary may invoke it is advisory,
not a cryptographic or OS-enforced per-Bot permission. This reader does not
change that limitation; raw fabric_task.py remains a separately governed
attended manual route.

The canonical Executive ingress socket on M2 is owned by the existing
_mastermind_exec service with an ACL for _mastermind_executive_mcp.
The ordinary chriswong account was verified to have neither read nor write
permission to that socket. Do not widen that socket ACL, copy C3 credentials
or invent caller-supplied authority just to make a Bot appear admitted.

A production-grade unattended Grok Secretary delegation requires a real,
separately authenticated and authorized Grok principal at the existing
Executive ingress, bounded Job/Attempt/RuntimeBinding, capacity admission,
and original-parent result review. The Executive V3 reader tool was
backend_unavailable for this session. That authenticated route remains a
separate not-yet-proven wave under issue #983; VPS/Steward is not a dependency
of the already-proven Mac-local manual route.

Tests in tests/test_grok_bot_local_fabric_read.py cover opaque secret-result
non-disclosure, root and parent correlation,
fixed executable/digest denial, stripped ambient auth environment, byte/time
bounds, subprocess cleanup, parser/backend refusals and absence of
side-effecting tool commands. Source build does not prove that the native
desktop Bot has independently loaded this reader; production release and a
fresh-Grok-session read proof are still required.
