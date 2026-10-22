# Eliminate the empty-PID readiness race in a CI fixture

## Consumer and scope
This test-only repair removes a reproducible unrelated CI failure from the execution-throughput delivery path. It changes no production Browser resource, admission, cleanup, permission, timeout, workflow or release policy.

Operation: `execution-ci-pid-readiness-20261015-c3-001`. Base: `a5ebced8f1129871bfe05066090de3328ce783b4`. Parent mission/root: `execution-throughput-20261015-c3-001`; these are attended source-operation correlations, not fabricated native-thread or Executive Job identities. The workspace was acquired with the incumbent `mmx-workspace` owner. The compatible protected procedure pin remains `78388ac29f7e54c9dfe7799a8e4769fb46d4aed6`; relevant procedure comparison found no changes.

## Reproduced defect
Hosted run `38687686462`, job `116266271007`, failed `tests/test_workbench_browser_resource_port.py::test_pre_barrier_inspection_failure_terminates_owned_wrapper_and_is_not_applied` because its PID file was empty. The fixture child created the final file before writing. The parent inspector treated existence as readiness, raised the intended synthetic inspection error, and production cleanup correctly terminated the child before it finished writing.

The new regression pauses the child immediately after opening its output. Before the repair it reproduced the exact `ValueError: invalid literal for int() with base 10: ''`. This is controlled test-only latency injection, not a retry or production timeout increase.

The fixture now writes and closes a same-directory `.pending` file, then atomically publishes the final PID path with `os.replace`. The original assertions still require `NOT_APPLIED`, no browser reference, and actual termination of the owned child. The regression invokes those original assertions rather than substituting a mock success.

## Verification and continuation
The complete resource-port test module passed all **9 cases**, exit 0; diff whitespace checks passed. Existing discovery-first CI already owns this module. Independent read-only Fabric review `throughput-pid-fixture-review-20261015-c3-004` was submitted once with the exact source snapshot; normal routing selected MiniMax on Ubuntu1. Consume that same retained return and its digest before claiming accepted review. A running process is not an accepted review.

This source candidate can undergo hosted CI in parallel with review. It requires no application restart or Browser grant because production behavior is unchanged. Exact-head checks, review adjudication and the normal source merge remain required. The two held pagination-fixture corrections in #1486 and the held adjacent AGENTS correction in #9438 are separate operations and are not retried here.

The parent programme still owes actual native continuation through a real product delivery after its initiating Web turn ends; this repair removes a concrete CI flake, not that entire obligation.
