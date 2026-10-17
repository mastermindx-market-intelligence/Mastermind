# Execution throughput — implementation frontier

## Assignment and acceptance
The October 14/15 Chairman assignment is to implement the execution-throughput assessment and keep improving delivery robustness and efficiency. Parent acceptance requires actual product work to advance through required review/checks/release/verification after an initiating Web turn ends without a human resume. A source PR, observer notification or passing scoped suite is not that outcome.

Operation: `execution-throughput-20261015-c3-001`. Source branch: `sol/web-execution-throughput-20261015-c3-001`. Base: `2cc4942e136ad4fb544fd5c72ab1856608a5dac1`. Procedure pin reused: `78388ac29f7e54c9dfe7799a8e4769fb46d4aed6`; no diff in `docs/sol_skills` or `docs/DELIVERY_WORKFLOW.md` between the pin and acquired base. Workspace acquired through installed `mmx-workspace`; one source writer. No runtime Job, source transfer or native-parent identity is invented.

## Recovered work that must not be duplicated
Mastermind #1341 is merged at `8e75547385fffcad1d125f0cf4d77659546f1d5f`. Installed M2 Codex global instructions already include active-principal/no-ghost-owner/ordinary-assignment/no-extra-approval/continue-after-checkpoint behavior. Repeating those paragraphs alone will not close the missing execution path.

Existing H5 source already owns candidate assessment, material-event filtering, a process-local waiter and Wake-obligation composition. `docs/claude_capability_hardening_20261004/H5_CI_CONTINUATION.md` explicitly leaves the real GitHub sampler and host/consumer integration unfinished. No duplicate lifecycle, queue, credential store, or persistent watcher registry is introduced by this work.

## Implemented first connection
- `integrations/github_ci_candidate_reader.py`: owner-native PR, branch/ruleset and check/workflow reads into the existing `assess_candidate_ci_observation`. Bounded full pagination, exact head/producer/workflow identity, complete policy read, revalidation, and explicit unsupported-evidence refusal.
- `scripts/github_ci_candidate.py`: the existing installed GitHub CLI provides closed GET-only, field-selected reads under its current authentication. Bounded output, fixed host, per-command timeout, sanitized failures, no alternate credentials/retries. Existing H5 waiter suppresses unchanged samples and returns one structured result to its current native/process caller.
- Consumer exit codes separate GREEN, FAILED, UNKNOWN, STALE and PENDING. Every result explicitly leaves `release_authorized=false` and `wake_delivered=false`.
- A test initially exposed unnecessary rejection when only the base branch commit moved during a read. Stable candidate/base identity now excludes unrelated base SHA and repo telemetry while retaining current policy revalidation. The focused regression was observed failing before repair and passing after it.

## Real GET-path observation
The command was exercised read-only on existing Mastermind #1201 at exact `8f88fb4946e71f573f40593eb7abdf54998516a7` on M2. It returned one GREEN observation for required `test`, app 15368, check-run `111350319115`, workflow run `37173209618`, attempt 1. Observed epoch: `1792040119`. Observation digest: `71653e24a78b8ad784449374a6ad7be295ee19a2deaeaaf3edfecb43ac397425`. Decision digest: `d7b43f6e64b494de44748ffc2da19d5e1edea8e448e45d46e11d46acde1c1c2b`. This proves real API -> normalizer -> canonical classifier -> structured foreground result. It does not authorize or merge #1201, prove a queued-to-finished transition, wake an idle session, or establish release acceptance.

## Verification and unresolved defects
Initial reader tests were observed RED for the absent implementation, then the original 15 passed. The CLI consumer tests were observed RED before implementation. The subsequent combined `tests/test_github_ci_candidate_*.py` plus `tests/test_github_release_assessment.py` run exited 1 with exactly two disclosed new test failures:
- `test_complete_check_pagination_uses_all_pages`
- `test_checks_changed_during_pagination_refuses`
Both new fixtures inadvertently changed `per_page=100` while constructing the page-two key, so their dictionary lacks the correct endpoint requested by the implementation. These are this change's new fixture defects, not inherited failures. A correcting edit was explicitly blocked before dispatch by platform safety checks; it was not retried or rerouted. The failing tests remain visible and release remains held. No claim of a green complete suite or independent approval is made.

## Effects and preserved refusals
The attempted creation of an implementation-coordinator packet `EXECUTION_PACKET.md` was platform-blocked before dispatch. No coordinator or Fabric worker was started. Direct independent source work continued; no denied assignment was replayed. The separate correcting edit described above was also blocked before dispatch. These refusals do not mean all tools are unavailable; ordinary independent source/read/test actions succeeded. There is no unresolved modifying effect in this operation.

The prior assessment's refused batch GitHub/host inspection for the six reported example PRs and run 38514680773 is not retried. Historical denials on the example product/native/browser missions remain their own action-scoped fences; this assignment does not reopen them.

## Next useful work and boundaries
Continue bounded integration validation, transport/process fault tests, independent qualified review and honest draft publication. Required coverage includes timeout/redaction, duplicate or reordered result rejection, missing policy, candidate change during waiting, and process ownership/return. The denied fixture correction requires an actual permitted resolution, not another tool/model/account. This source-only slice must not be installed or presented as a complete finish path while its required tests/review are held.

Then connect an actual admitted native executor to the existing wait/return path and prove one real assigned delivery beyond notification; reconcile applicable Macro ship-loop/instruction contradictions without replaying already accepted #1341 changes. Use existing runtime/process, GitHub review/release and Agent OS owners. Do not add another scheduler, approval ceremony or observer per chat. Current sampler support is deliberately same-repository GitHub Actions check-run evidence with positively bound app identity. Forks, legacy status-only/unbound producers and additional required-workflow policy are unsupported, not silently green. Idle Wake, formal review automation, merge/deployment and all-account adoption remain unproven.

## Current continuation pointer — source advanced after this initial receipt

The current cumulative frontier is `research/execution_throughput_20261015/CONTINUATION.md`; the initial account above and `research/execution-throughput-tests.json` remain historical evidence for their own source hashes, not the newer reader/CLI bytes. The latest source-bound local result is 308 tests: 306 passed and the same two disclosed fixture failures. `research/execution_throughput_20261015/validation_source.json` binds all six current source/test files and confirms the four new test modules are discovered by the repository's existing CI gate.

The original transport-fault test file was recovered and inspected, not overwritten. A distinct read-only Fabric review `throughput-ci-review-20261015-c3-001` has since been submitted against the manifest-bound five-file review snapshot; its result remains to be consumed. This does not reissue the refused native implementation-coordinator packet. The separate Macro entrypoint reconciliation is already in its own isolated operation `execution-instruction-reconcile-20261015-c3-b72e`; do not start a competing instruction patch or adopt its native-review process by inference. Keep its actual effects and original return path separate.
