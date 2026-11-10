# Lane: Executive / Capacity / Fleet integration — Director C (2026-11-09)

Branch `t3/executive-capacity-fleet-integration`, created from `bbfad42da`.
All work is confined to this isolated worktree; no push, no merge, no PR, no
master write, nothing under `~/.hermes` edited, no daemon started or stopped,
no port bound. This document is the lane summary for the principal to
integrate: changes, review-item→test mapping, PROVEN vs SOURCE_ONLY, pinned
files, open issues.

## Commits on the lane

| Commit | Package | Content |
|---|---|---|
| `636424a1e` | import | WO-11 r4 state imported from origin/feat/mmos-v1-wo11-launch-guard @244be4afc (pre-lane base recovery, before this lane's work) |
| `9eb4e5487` | C1 | Guard: structural shell-shape refusal rework for REVIEW_2329 r3 B-1/M-A/M-B (WO-11 r5) + adversarial tests |
| `f8387af56` | C2 | Docs: executive reader `backend_unavailable` diagnosis (read-only, PROVEN parser-boundary reproduction) |
| `119d72b1a` | C3 | Claim path: ExecutionBinding v1.1 t3-native idempotency join at claim + WorkspaceLease containment join by contract |
| `686689041` | C4 | Docs+data: quota truth record from the read-only Rev5 observation run (artifacts committed) |
| `062cd77c5` | C5 | Docs: fleet host readiness typed read-only summary |

## Changed files (vs `bbfad42da`)

- `ops/executive_os/provider_orchestrator_guard.py` (C1) — structural
  scanner additions, all deny-side; see mapping below.
- `tests/test_provider_orchestrator_policy.py` (C1) — r5 adversarial block;
  file total 173 tests.
- `control_plane/executive_runtime.py` (C3) — `_join_native_runtime_binding`
  module function + one call site inside `AttemptRegistry.claim_job`'s
  transaction. **PR #2177 hunk protection verified**: none of the 62
  protected `executive_runtime.py` hunks (PR #2177's diff was fetched from
  GitHub for the check; the integrator did not retain the 2k-line copy in the
  branch — re-fetch `gh pr diff 2177` to reproduce) overlap the edited
  old-file region (~18550-19350); the protected hunks are byte-identical to
  the imported state.
- `control_plane/workspace_lease.py` (C3) — added `attach_workspace_lease`
  (contract join onto an ExecutionBinding v1.1 from one real lease record;
  refuses non-active leases); `t3_workspace_id` stays lease-side. No lease
  lifecycle, writer-epoch or single-writer logic changed.
- `tests/test_executive_claim_job_placement_authority.py` (C3) — 4 new
  contract tests (real SQLite stores in temp dirs; no live launch).
- `integrations/mmos/*.md`, `quota_observation_v2.json`,
  `quota_preview_os_current.json` (C2/C4/C5) — lane documents + committed
  observation artifacts.

**Files NOT touched** (verified `git diff --name-only bbfad42da..HEAD`):
Director A's `control_plane/t3_execution_adapter.py`, `integrations/t3/**`,
`dsh_acp_runtime.py`; Directors B/D `app/**`; every review-identity-pin test
(`tests/*identity_review*.py`, `tests/*review_pins*.py`,
`test_executive_reviewed_site_identity_tokens.py`,
`test_next_mounted_identity_pins.py`). **No pinned file was moved or
modified.**

## REVIEW_2329 r4 review-item → test mapping (C1)

Guard module: `ops/executive_os/provider_orchestrator_guard.py`
(`_deny_structurally_unobservable`). Tests:
`tests/test_provider_orchestrator_policy.py`, docstring at the head of the
r5 block maps every review item to its tests. Per item:

- **B-1 interpreter one-liners / computed words escape** →
  `test_r5_b1_interpreter_option_forms` (12 forms: `-c`, `--command`,
  stdin-fed heredoc/pipes, `python -`, `sh <script`, always-inline
  interpreters incl. `osascript -e`),
  `test_r5_b1_interpreter_stdin_fed` (3),
  `test_r5_b1_always_inline_interpreters` (3),
  `test_r5_b1_computed_words_through_unlisted_runners` (15: time/sudo/
  caffeinate/script/strace/flock/systemd-run/unbuffer/ionice/doas/chrt/ssh/
  su -c/brace-group/subshell shadow),
  `test_r5_b1_command_substitution_arguments` (2).
- **M-A function/brace/trap/watch multiplication** →
  `test_r5_ma_function_definition_bodies` (5),
  `test_r5_ma_brace_body_loops` (3),
  `test_r5_ma_trap_payloads_and_watch_repeaters` (3).
- **M-B nested eval/source/dot** → `test_r5_mb_nested_eval_source_dot` (5),
  `test_r5_mb_separate_process_dot_stays_allowed` (scoped control).
- **Scoped-refusal regression guard** →
  `test_r5_b1_structural_refusals_stay_scoped` (ALLOW controls: honest
  observed launches, incl. `python3 /opt/mastermind/ext/slot.py glm -- run`
  and a faithful `bash -c` nested launcher, still pass).
- **Fail-before proof**: 49 of the 53 new r5 tests FAIL on the pre-fix guard
  (commit `636424a1e`); the 4 that pass on r4 are the two ALLOW controls
  (by design) plus two deny variants r4's regexes incidentally caught.

C3 contract-test mapping (claim seam):

- `test_t3_native_claim_issues_v1_1_binding_with_t3_idempotency_join` — v1.1
  join fields, `T3_REQUEST_NAMESPACE`, `derive_t3_client_request_id` key,
  binding rides `JOB_CLAIMED` payload.
- `test_plain_adapter_route_stays_a_v1_binding` — non-t3 routes stay v1.
- `test_unknown_route_adapter_fails_closed_inside_the_claim_transaction` —
  unknown adapter id → typed `StateConflict`, commitments rolled back, Job
  stays QUEUED.
- `test_workspace_lease_join_stamps_containment_by_contract` — lease join
  fields, idempotence, input binding unchanged, `LEASE_NOT_ACTIVE` refusal
  after release.

## PROVEN vs SOURCE_ONLY

**PROVEN (test or executed evidence):**

- C1: 173/173 green in `tests/test_provider_orchestrator_policy.py` at
  `9eb4e5487` (and in the final acceptance run); fail-before evidence above.
- C2: exact-generation reproduction — installed reader generation
  `b4a5a8925c6c` refuses exactly 1 of 115 live Macro workstream records
  (`WS-PROPHET-END-TO-END-R7.md`, hash-prefixed continuation lines in folded
  block scalars); staged `036e8d26…` accepts 115/115. Parser-boundary proof,
  no server involved. See `EXECUTIVE_READER_DIAGNOSIS.md`.
- C3: 23/23 green in `tests/test_executive_claim_job_placement_authority.py`
  (19 pre-existing + 4 new) and 12/12 in `tests/test_workspace_lease.py` at
  `119d72b1a` (the two files together are the 35 an earlier draft cited);
  real SQLite stores, temp dirs.
- C4: observation run RC=0; artifacts committed with sha256 recorded in
  `QUOTA_TRUTH_2026-11-09T0925Z.md` (raw rows 6 observed / 17 unknown;
  composed 8 observed / 13 unknown over 21 canonical resources).
- C5: 45/45 green (`tests/test_t3_environment_projection.py` +
  `tests/test_session_bridge_t3.py`); 7/7 green
  (`tests/test_executive_worker_broker.py -k "executor or heartbeat"`).

**SOURCE_ONLY (stated, not executed):**

- C3 Director A coordination proposals C-P1/C-P2/C-P3 in
  `DIRECTOR_C_SHARED_PATH_PROPOSALS.md` — proposed seam checks in
  `t3_execution_adapter.py` (launch-time verification of
  operation_key/caller_namespace; workspace containment against
  `binding.workspace_ref`; persisting `t3_workspace_id` at native workspace
  creation). This lane did not and may not implement them.
- C4/C5 document claims about live fleet/quota state are typed observations
  with provenance, not executed integrations.
- The C1 guard rework is not claimed to be exhaustive over all shell
  grammars — it closes the specific r3 review shapes with scoped controls;
  unknown shapes stay refusable by the existing deny-side defaults.

## Open issues (for the principal)

1. **C2 resolution needs the Control release path** (owner:
   `ops/executive_os/control_component_update.py`): the #2088 frontmatter
   fix exists in staged `036e8d26…` but the installed reader is
   `b4a5a8925c6c`; the 2026-11-08 plan returned
   `REFUSED / control_component_worker_live`, and the 09b/call5913
   protected-result disposition (#1893) is a prerequisite. Do not disarm the
   Worker to make the plan eligible.
2. **PR #2177 protected hunks** remain unmerged; the C3 edits avoid them
   (verified by hunk-range overlap), but the principal must keep both
   surfaces consistent when #2177 lands.
3. **Director A must consume C-P1/C-P2/C-P3** before the t3-native join is
   enforced at launch; today the adapter still derives the key
   independently (drift would launch a new upstream identity).
4. **Quota unknowns stay unknown** (C4): 13/21 canonical resources have no
   observable quota surface; nothing in this lane fabricates them.
5. **Fleet enrollment blockers unchanged** (C5): no host is fresh; 0
   eligible slots fleet-wide; ubuntu4 unreachable; Tailscale TCP/22
   control-path broken from M2.
6. **OQ-5 open** (WO-04): whether the coordinator should hold any worker
   slots — 12 is the formula output only.

## Acceptance

Commands (run at the final lane SHA; counts in the final Director C report):

```
env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q <file>   # one per file:
tests/test_provider_orchestrator_policy.py
tests/test_fabric_placement_policy.py
tests/test_workspace_lease.py
tests/test_executive_claim_job_placement_authority.py
tests/test_hermes_selected_child_dispatch.py
tests/test_hermes_selected_child_ingress.py
tests/test_child_execution_contracts.py
tests/test_rev5_contracts_v1_1.py
tests/test_worker_adapter.py
tests/test_executive_coo_hierarchy.py
+ every file from: grep -rl claim_job tests/
```
