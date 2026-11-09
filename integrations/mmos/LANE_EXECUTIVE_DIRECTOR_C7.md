# Lane ledger — Executive Director C7 (review #3 rework, t3-native composition r2)

Branch `t3/t3-native-composition-r2` (from merged `t3/t3-hermes-restart-recovery`
head `166923b1d`, which contains C4's `control_plane/t3_native_composition.py`).
No push, no PR. Successor of Director C4 on the Executive shared path; this
lane closes review #3's B1/B2 NEEDS_REWORK findings (B3 d7 pin and B4 route-row
were ACCEPT and are untouched).

Review #3 authoritative record (once committed by the reviewer):
`integrations/mmos/REVIEW3_GUARD_R7_C4_OPUS_20261110.md`.

## Finding → fix → test (all in this lane, all green)

| # | Review #3 finding | Fix | Tests |
|---|---|---|---|
| B1 MAJOR | `compose_t3_native_owners_for_service` read `primary.inspector` BEFORE checking enrollment → `AttributeError` for every stand-in primary without `.inspector`; 16 existing tests failed (11 × installed-fabric-composition, 4 × session-bridge-codex-runtime, 1 × privileged-control-composition) | The seam now resolves the token file FIRST (`resolve_t3_access_token_file`); an unenrolled host returns `{}` without touching the primary AT ALL; only an enrolled host reads `getattr(primary, "inspector", None)` | `test_unenrolled_service_seam_never_touches_a_stand_in_primary` (SimpleNamespace primary, no inspector); all 16 regressions green in the mandated run |
| B1 MAJOR (law) | C4's new `ExecutiveSupervisor` construction site (`compose_t3_native_supervisor`) was uncalibrated → constructor source law failed (expected 8 supervisor sites) | Registered through the law's own normal process: identity `("control_plane/t3_native_composition.py", "compose_t3_native_supervisor", "supervisor", 1)` added to `_EXPECTED_CONSTRUCTOR_SITES` with a dated comment; counts moved 8→9 supervisors and 14→15 killed mutants (the mutant-kill check covers the site like every other) | `test_constructor_source_law_covers_calibrated_sites_and_kills_each_mutant` (green, 15/15 mutants killed) |
| B1 MINOR | A malformed token file (`garbage-no-dot`, `a.b`) raised `T3NamespaceAttestationError` out of the composition INTO `_service_from_config`, taking the paid/plain/fabric lanes down together; an empty file quietly returned `{}` with its reason discarded | One explicit decision, as the review preferred: a new typed status `T3_ENROLLMENT_BROKEN`. `compose_t3_native_adapter` classifies a configured-but-unreadable/empty file AND an attestation failure at port construction into that typed result (never an exception; the reason never echoes token material). The service seam composes no owner (fail-closed for the t3 lane only) and SURFACES the reason visibly at startup through the module logger (`logging.ERROR`) — the one seam that keeps the phase1c call sites plain `dict` consumers; the other lanes stay up | `test_malformed_token_file_is_a_typed_broken_enrollment_not_a_crash`; `test_service_seam_surfaces_a_broken_enrollment_and_never_raises` (no exception, `{}`, ERROR record with the reason, no token material in the log); `test_service_seam_surfaces_an_empty_token_file_reason`; the empty/missing-file tests reclassified from `T3_NOT_ENROLLED` to `T3_ENROLLMENT_BROKEN` |
| B1 MINOR | `T3McpHttpTransport.initialize()` was never called before tool calls (upstream behavior for session-less `tools/call` UNKNOWN); `urlopen` honoured environment/system proxies and followed 3xx redirects RESENDING the bearer | (a) lazy, thread-safe, exactly-once `initialize()` before the first `call_tool` (`_init_lock` + `_initialized`); a typed `reinitialize_after_session_loss()` is the ONLY re-init path — a mutating call is never auto-retried or auto-reinitialized. (b) the opener is built once from `build_opener(ProxyHandler({}), _RefuseRedirects())`: no environment or system proxies, and every 3xx becomes a typed `T3McpTransportError` (http_status carried) because `_RefuseRedirects.redirect_request` declines — the redirect target is never requested, so the bearer is never resent off-origin | `test_transport_initializes_once_before_the_first_tool_call` (fake upstream records method order: `initialize` → `notifications/initialized` → `tools/call`; second tool call does NOT re-initialize); `test_transport_refuses_redirects_and_never_resends_the_bearer` (302 → typed error, only `/mcp` ever requested); `test_transport_ignores_environment_proxies` (dead `http_proxy`/`https_proxy`/`all_proxy` in all cases still delivers directly, bearer intact) |
| B2 MAJOR | `SupervisorBoundaryT3Adapter.reattach` substituted the retained ref into the binding WITHOUT checking the binding's ref was the twin of that retained ref — the inner adapter's "retained original ref differs … refusing to swap executions" check compared the retained ref to ITSELF, so a binding forged with `thread-FOREIGN`/`foreign-key` was ACCEPTED | `if self._twin(retained) != binding.process_ref: raise T3NativeCompositionError("…refusing to swap executions")` BEFORE the substitution — fail-closed, typed, the inner adapter is never called for a forged binding. Also the optional hardening the review suggested: entering the sync bridge from a running event loop is now a typed refusal (the supervisor surfaces it as `LIVE_QUARANTINED`; production calls arrive off-loop via `asyncio.to_thread` → unaffected) | `test_bridge_reattach_refuses_a_forged_binding_before_the_inner_adapter_runs` (genuine binding sanity-asserted to BE the twin; forged `thread-FOREIGN`/`foreign-key` binding → typed error, inner `reattach` mocked to fail if called); `test_bridge_reattach_refuses_entry_from_a_running_event_loop` |

Confirmed-correct items from review #3 kept BYTE-IDENTICAL (no edit): store
placement rule + `CHECKOUT_DEFAULT` disclosure; never `executive.sqlite3`;
unenrolled host `{}` and no files; one token for attestation and Authorization
header; token never in repr/errors; conservative error classification; pre-ACK
binding via supervisor `_launch_metadata`/`record_process` (crash → durable
binding → `TERMINAL_RECOVERED` with zero launches/replays/reads — re-pinned by
the existing crash test, still green).

## Files changed (complete list)

1. `control_plane/t3_native_composition.py` — the B1/B2 fixes above.
2. `tests/test_t3_native_composition.py` — 8 new tests + 2 reclassified
   (empty/missing token file now `T3_ENROLLMENT_BROKEN`).
3. `tests/test_worker_execution_contract.py` — constructor-site calibration
   through the law's own registration process (site identity + counts).

No edit to `executive_runtime.py`, `executive_supervisor.py`,
`scripts/executive_os_phase1c.py` (all three additive call sites byte-identical;
the d7 wrapper AST anchor and the d7 full-file pin C4 moved in
`tests/test_ceo_submit_armed_composition.py` are UNCHANGED — phase1c did not
change), `config/executive_worker_routes.json`, `t3_execution_adapter.py`
(NOT even additive helpers were needed), `src-tauri`, React, pins, `~/.hermes`.
`control_plane/t3_native_composition.py` imports nothing from `integrations`.

## The mandated run

```
env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest \
  -p no:cacheprovider --basetemp=/tmp/c7bt \
  tests/test_t3_native_composition.py tests/test_worker_execution_contract.py \
  tests/test_executive_mcp_installed_fabric_composition.py \
  tests/test_session_bridge_codex_runtime.py \
  tests/test_executive_privileged_control_composition.py \
  tests/test_worker_adapter.py tests/test_executive_worker_broker.py \
  tests/test_t3_execution_adapter.py tests/test_t3_adapter_durability.py \
  tests/test_ceo_submit_armed_composition.py \
  tests/test_hermes_selected_child_ingress.py
→ 810 passed, 117 subtests passed in 109.67s   (d8 identity scans green)
```

The 17 review-#3 regressions (16 `.inspector` + 1 constructor law) are green
inside this run (C4's "216 passed, 5 failed" side sweep was superseded by this
full-file inclusion).

## The 84-file phase1c sweep (short basetemp)

Census at this head: `grep -rl executive_os_phase1c tests/` → **85 paths =
84 `test_*.py` files + 1 fixture (`tests/executive_installed_control_fixture.py`,
imported by the tests)**, matching review #3's "84 files".

```
env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest \
  -p no:cacheprovider --basetemp=/tmp/c7sw3 $(the 85 paths)
→ 80 failed, 3626 passed, 2 subtests passed in 480.85s
```

(reproduced twice; a third attempt errored wholesale only because a STALE
basetemp from the first run was reused — pytest basetemp dirs are not
idempotent across runs here; a fresh short basetemp is required each time.)

**Attribution — ZERO failures are caused by this lane.** Every failing file
was re-run at the base commit `166923b1d` (this lane's diff stashed by SHA,
restored, stash dropped) with the SAME failure set:

| File | Failures | Also fails at base? | Class |
|---|---|---|---|
| `tests/test_executive_codex_attestation_receipt.py` | 54 | YES — identical ("codex attestation receipt has an unexpected group owner") | pre-existing environmental (root-uid/group-owner file semantics on this unprivileged macOS host) |
| `tests/test_c1_relay_release_rebind.py` | 21 | YES — identical | pre-existing environmental (same ownership/socket-stanza class) |
| `tests/test_fabric_attended_probe_join.py` | 3 | YES — identical | pre-existing environmental |
| `tests/test_executive_acceptance_observability.py` | 1 | YES — identical | pre-existing environmental |
| `tests/test_codex_provider_realm.py` | 1 | YES — identical | the review's own named pre-existing failure (`:150`) |

The review's "23 failures (5 AF_UNIX + 16+1 C4 regressions + 1 provider
realm)" was measured in the reviewer's environment. In THIS worktree the
environmental baseline of the same 84-file sweep is 80 (the AF_UNIX five
PASS with a short basetemp; this host instead trips the file-ownership
class above), and the 17 C4 regressions fail at the merged head exactly as
reviewed (confirmed directly at session start, before any edit: the
`AttributeError: '_NoExecutionSupervisor' object has no attribute
'inspector'` repro). After this lane's fixes those 17 are GREEN (mandated
run above; the sweep at my head no longer contains them), leaving the 80
pre-existing failures byte-identical to base.

## Scope-roots decision (A1 note for THIS lane) — NO seam exists; proposal below

**Finding (confirmed).** `guard_bash`
(`ops/executive_os/provider_orchestrator_guard.py:2990`) returns before ANY
check when `is_project_scope(payload)` is false. Scope roots are the 7 fixed
roots (`_scope_roots`, guard :2018-2032) plus `MASTERMIND_SCOPE_ROOTS`
(os.pathsep-separated) read from `os.environ` **of the process running the
hook**. `~/.t3/worktrees/…` matches no fixed root and `MASTERMIND_SCOPE_ROOTS`
is unset here → an armed t3-native child session receives NO guard checks
(fabric-launch gate, R7 armed length gate, CI-watch cadence all skipped).

**Seam investigation (this lane, read-only).**
- The launch envelope (`T3ThreadLaunchEnvelope`, `t3_execution_adapter.py:404`)
  carries only namespace/key/run/worker/title/message/workspace_ref/model/
  created_at; `_launch` (:3663) sends only `title`/`message`/`clientRequestId`
  (+`modelSelection`) plus port-level `launch_arguments` — and the donor
  `t3_thread_launch` handler census (audit doc; `handlers.ts`) accepts
  title/message/clientRequestId/modelSelection(/scratch/admission): there is
  **no environment parameter** on the tool.
- `T3McpToolPort(launch_arguments=…)` is the only additive argument seam into
  the launch call, but it feeds JSON tool arguments, not the child process
  environment; the guard reads the HOOK process's env (the T3 Code app
  process), which no tool argument reaches.
- Nothing in `WorkerLaunchSpec`/`_launch_envelope` maps to thread-process
  environment, and `integrations/t3/docs/*` documents no env-passing surface.

**Decision: no existing env-passing seam exists, so nothing was composed here**
(the adapter was not edited at all — not even additive helpers; the guard was
not edited). The exact proposal for the owner of each act:

1. **Preferred (deployment, no code):** set, in the T3 Code ENVIRONMENT's own
   process environment on the machine hosting t3-native children (the
   environment whose hooks run `guard_bash`), `MASTERMIND_SCOPE_ROOTS` naming
   the roots t3-native children work under — at minimum the workspace/
   isolation roots the composition passes (`isolation_roots` = proof-workspace
   root + worker runs root at the phase1c call sites) — plus, when the armed
   shared-placement path is in force, the binding env the guard then expects
   (`POOL_EXECUTION_BINDING`, `MASTERMIND_SHARED_PLACEMENT`,
   `MASTERMIND_PLACEMENT_RECEIPT`, `MASTERMIND_PLACEMENT_RECEIPT_DIGEST`,
   `MASTERMIND_PLACEMENT_RECEIPT_OWNER_UIDS` — guard :151-193, :2603-2652).
   That is a host-level T3 environment configuration act through its existing
   owner; it arms the guard for every session in that environment (which is
   the guard's own scope model), not per-launch.
2. **Alternative (creates a real seam, upstream act):** an upstream T3 patch
   adding a launch-time env/scope parameter to `t3_thread_launch` +
   `integrations/t3/upstream_patches`-style review. Heavier; only worth it if
   per-launch scoping (not per-environment) is ever required.
3. **Not chosen:** widening `_scope_roots`' fixed list with `~/.t3/worktrees`
   inside the guard would arm it for ALL T3 worktree sessions on a host
   regardless of Mastermind admission — a guard-policy change for the guard's
   owner (`ops/executive_os`), not this lane.

Until (1) or (2) lands, the honest statement for live: **an armed t3-native
child on an unconfigured T3 environment runs with the guard's scope check
inert** — the canary plan must either configure the scope roots first or
record that gap.

## Remaining for live (unchanged from C4 except where noted)

1. Apply the route row through the protected-change path for
   `config/executive_worker_routes.json` (owner: that file's protected path).
2. Enroll the token file on the installed Executive host and set
   `MASTERMIND_T3_MCP_ACCESS_TOKEN_FILE` in the service environment; a broken
   enrollment now surfaces typed at startup instead of crashing the service.
3. Register the canary worker (`worker_type: "t3-native"`, quota class in
   `T3_NATIVE_ROUTE_ROW_PROPOSAL.md`) in the installed Runtime.
4. Run the canary through the composed path; verify the pre-ACK binding and a
   simulated crash recovering with zero native launches.
5. Design the remote validation story (`run_validation_argv` refusal) or canary
   with a job shape needing no local validation argv; likewise the honest
   remote sweep story for the launch-FAILURE quarantine branch.
6. NEW (this lane): configure `MASTERMIND_SCOPE_ROOTS` (+ armed binding env)
   in the T3 environment hosting t3-native children, per the proposal above,
   BEFORE relying on any guard behavior for armed t3 children.
7. NEW (this lane): confirm against the real T3 MCP endpoint whether
   `tools/call` requires a session — with the lazy initialize this no longer
   matters for correctness, but the answer belongs in the canary record.
8. Only after the canary: flip the row to the hermes shape, add the
   `_ADAPTER_EXECUTION_SURFACES` entry and a `worker_eligible` alias
   (separate reviewed changes).
