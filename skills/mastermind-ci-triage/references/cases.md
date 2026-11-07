# CI diagnostic cases

## Order-dependent configuration
Input: test B fails only after test A in the hosted shard; B alone passes.
Next: run A then B in the same process at the same head. Compare environment and
module-level state before and after A. Add teardown or dependency injection, then
prove A+B and the interacting group pass. Do not classify a green B-only rerun as
resolution.

## Queue delay versus slow tests
Input: wall time is 29 minutes, queue wait is 17, tests are 9, setup/teardown are 3.
Conclusion: a test-only speedup cannot remove the 17-minute queue wait. Report all
components; compare capacity/queue evidence separately. Do not promise a target
wall time from summed shard durations.

## External dependency failure
Input: dependency download returns a verified upstream service error before tests.
Next: preserve the exact run and evidence; inspect authorized cache/failure policy.
Do not invent a source regression or push an empty commit to obtain a new run.

## Acceptance falsifiers
Reject a candidate that deletes a failing test, changes required checks, hides a
collection error, widens production credentials, or presents a different-head
run as current proof. A missing browser journey remains a separate product gate.
