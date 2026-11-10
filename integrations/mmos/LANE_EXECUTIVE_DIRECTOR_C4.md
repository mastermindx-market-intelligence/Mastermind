# Lane ledger — Executive Director C4 (audit #14 closeout, t3-native composition)

Branch `t3/t3-native-runtime-composition` (from merged `t3/t3-hermes-restart-recovery`
head `29a82f779`). No push, no PR. Successor of Directors C/C2/C3 on the Executive
shared path.

Mission: close audit item #14 — "no runtime composes the SQLite store,
`T3McpToolPort` and a real producer of the pre-ACK recovery binding" — plus the
store-path decision and the `t3-native` route row (DONE_WHEN 2), with no new owner,
queue, registry or database.

## PROVEN_BY_TEST (tests/test_t3_native_composition.py, all green)

1. **Store placement follows the Executive's own database rule.** The adapter
   state file is a SIBLING of the Executive's actual database
   (`t3_adapter_state.sqlite3` beside `runtime.store.path`), never
   `executive.sqlite3` itself; a configured installed-layout root resolves the
   same way without a live Runtime; with NEITHER, the composition falls back to
   the per-checkout `default_t3_adapter_state_path()` and DISCLOSES that fact in
   the typed `basis` field (`CHECKOUT_DEFAULT`) — the per-checkout default is
   exactly what makes the re-audit R1 no-row recovery window reachable, so a
   production composition must say when it is on it. The store itself
   independently refuses the Executive file (pinned by the durability tests).
2. **Token law.** No token file (env `MASTERMIND_T3_MCP_ACCESS_TOKEN_FILE`
   absent) → typed `T3_NOT_ENROLLED` composition result, no exception, no owner;
   empty or unreadable file → typed not-enrolled with reason; the token value
   never enters logs, errors or results. Resolution prefers an explicit path,
   then the env var.
3. **One token for attestation and transport (re-check M2).** A present token
   attests `client:<sid>` from the token claims AND the transport sends exactly
   that token — proven both with a recording fake (the port's transport callable
   IS the recording transport's bound method) and with the REAL stdlib
   `T3McpHttpTransport` against a live local HTTP server asserting the
   `Authorization: Bearer <token>` header it received.
4. **Route row well-formedness without touching the protected file.** The
   verbatim proposal row parsed out of `T3_NATIVE_ROUTE_ROW_PROPOSAL.md` merges
   into a temp copy of `config/executive_worker_routes.json` and loads through
   the real `ModelRouter.load()`; the live file's bytes are asserted unchanged.
5. **Launch through the Executive's own path + the pre-ACK binding.** A claimed
   t3-native route (child-placement claim; `ExecutionBinding.runtime_kind ==
   "t3-native"`) launches through `MixedExecutionOwnerSupervisor._select` →
   `_start_claimed_job`; the native port launches once; the supervisor's
   `_launch_metadata` persists `worker_recovery_binding` (adapter_id
   `t3-native`, durable `input/worker-prompt.txt` + prompt sha256 in the
   binding's launch_spec) BEFORE the RUNNING transition — the audit #14
   producer, exactly where other adapters get theirs.
6. **Crash-before-ACK recovery with ZERO native launches.** `mark_running`
   replaced by `SystemExit` (escapes Exception containment like a kill): the
   attempt stays CLAIMED with the binding durable. A RESTARTED composition
   (fresh adapter over the same SQLite store, FRESH port) `reconcile_restart()`
   → `TERMINAL_RECOVERED`, then `reattach` runs through the real adapter (not a
   stored coroutine): zero launches, zero replays, zero reads, and the
   recovered run carries the ORIGINAL idempotency key and thread id.
7. **Remote process law.** The t3 process controller reports `TERMINAL_OWNED`
   only for attempts carrying this adapter's binding, `UNKNOWN` otherwise,
   never verifies absence, and `terminate` always refuses (a remote thread is
   interrupted only through the adapter's cancel seam).

## SOURCE_ONLY (not proven here; live steps below)

- The installed Executive service actually composing owners on an enrolled host
  (the phase1c seam is wired and compiles under the pinned d7 fingerprint, but
  no installed-host run happened in this lane).
- A real T3 MCP upstream (tests use a recording port and a local HTTP server).
- The route row applied to the live protected file (#2177).
- Any `_ADAPTER_EXECUTION_SURFACES` entry / `worker_eligible` alias for
  t3-native (deliberately deferred with the row's alias stance).
- Full t3 job TERMINALIZATION (collect → validation → seal): `T3ExecutionAdapter.
  run_validation_argv` refuses typed ("the T3 seam exposes no argv-validation
  operation"), so a t3 job carrying `validation_commands` cannot complete
  terminalization until the remote validation story is designed. The canary
  must use a job shape without local validation argv, or that story lands first.

## Store-path rule (decision)

`sibling of the Executive's actual database`, basis `EXECUTIVE_DATA_DIR`; the
per-checkout default is used only when no installed layout is configured and is
disclosed as `CHECKOUT_DEFAULT`. Why: the re-audit R1 reachability finding says
the per-checkout default is the reachable-but-undesired state; the composition
adopts the same layout rule the Executive uses for its own DB (one data
directory, one placement authority) and TYPES which basis it is on instead of
silently defaulting. No second placement authority is created.

## The seam wired (production wiring)

`scripts/executive_os_phase1c.py` — three additive call sites of
`compose_t3_native_owners_for_service` (compose once → per-worker owners; `{}`
on unenrolled hosts leaves every existing path byte-identical):

- paid branch: `scripts/executive_os_phase1c.py:2303` (`owners.update(...)` on
  the paid owners map);
- no-paid/no-fabric branch: `scripts/executive_os_phase1c.py:2328-2343`
  (composes; if any t3 owners exist, wraps primary in
  `MixedExecutionOwnerSupervisor` with `{config.worker_id: primary, **t3_owners}`
  and updates the recovery controller's owners; else `return primary`
  unchanged);
- fabric branch: `scripts/executive_os_phase1c.py:2349` (`owners.update(...)`).

## Supervisor-boundary projection (WHY it exists — read before touching)

The supervisor's single `record_process` call site (protected
`executive_supervisor.py`) passes the process ref's pid/pgid verbatim; the
Runtime accepts either a POSITIVE local pid or the ALL-None provider-managed
shape (`provider_session_id` only). The T3 durable ref contract pins
`pid=0`/`pgid=0` (remote thread; retained-ref determinism is what `reattach`
verifies; pinned by the durability tests), so `control_plane/
t3_native_composition.py:519 SupervisorBoundaryT3Adapter` translates ONLY the
four local-process identity fields (pid, pgid, process_start_identity,
boot_session_id) to the provider-managed recording shape at the supervisor
boundary — a pure, reversible projection; every durable T3 fact (launch nonce,
thread id, paths, receipts, store) is unchanged, and the execution owner stays
the adapter built through `construct_reviewed_adapter` +
`bind_reviewed_adapter`. Every translation is fail-closed (a ref that is not
the exact twin of the durable retained ref is refused typed). Two more bridges
live there:

- **sync `reattach`**: the supervisor calls non-paid `reattach` SYNCHRONOUSLY;
  the reviewed adapter's `reattach` is async. Without the bridge the supervisor
  stores an UNAWAITED coroutine (found live in this lane: recovery "succeeded"
  while the adapter's reattach never ran). The bridge runs the inner coroutine
  on a private one-shot loop — safe because `reconcile_restart` is a sync entry
  point; do NOT enter it from a running event loop.
- **`launch_attestation` twin identity**: the attestation's `process_identity`
  block carries the twin shape so `_validated_recovery_binding`'s comparison
  against the binding's process ref matches.

## Additive hunks OUTSIDE new files (complete list, with justification)

1. `control_plane/t3_execution_adapter.py` — ADDITIVE only: constant
   `T3_LAUNCH_ATTESTATION_SCHEMA_VERSION` (`.../t3-native/v1`, line 155) and
   method `T3ExecutionAdapter.launch_attestation` (line 1963). Justification:
   the mission explicitly permitted additive helpers when a seam is genuinely
   missing, and it is: the supervisor binds the admitted isolation manifest to
   the adapter's launch attestation on EVERY supervisor-built spec
   (`_launch_spec` always stamps `isolation_manifest_sha256`), and the adapter
   had no attestation reader. The method reads ONLY durable state (persisted
   spec + retained ref) and refuses typed when the durable launch record is
   absent or the supplied ref is not the retained one. No existing behavior
   changed.
2. `scripts/executive_os_phase1c.py` — the three additive call sites above;
   no existing line changed (the d7 wrapper AST anchor
   `060525ac61b01452e7a84397f0e68ab4be9c0a05f6dac560113bce8180adc819` is
   byte-identical).
3. `tests/test_ceo_submit_armed_composition.py` — d7 full-file fingerprint of
   phase1c moved `eb33b3f4…` → `d9d4492f…` with a dated comment, following the
   file's own documented precedent (accepted compositions move the
   fingerprint; the wrapper AST anchor is asserted unchanged and still is).

New files: `control_plane/t3_native_composition.py`,
`tests/test_t3_native_composition.py`,
`integrations/mmos/T3_NATIVE_ROUTE_ROW_PROPOSAL.md`, this ledger.

## Route-row proposal (summary)

`integrations/mmos/T3_NATIVE_ROUTE_ROW_PROPOSAL.md` carries the verbatim
`"t3"` provider row: `adapter_id: "t3-native"`, `enabled: false`,
`autonomous_allowed: false`, `production_armed: false`, arming grant OQ-7
(scoped V1 Wave-2 live testing, NOT blanket arming). Shape follows the
deepseek precedent (naming the route selects nothing); the hermes shape
(enabled + armed, no aliases) is the post-canary target together with the
`_ADAPTER_EXECUTION_SURFACES` entry and an explicit alias — not this row. The
document explains how `claim_job`'s `_join_native_runtime_binding` picks the
route up (quota-class `metadata.adapter_id`, falling back to the provider
row's `adapter_id`), gives the canary quota class
(`{"default": {"capabilities": ["code"], "metadata": {"adapter_id":
"t3-native"}}}`, provider `t3`), and keeps profile-less job constraints (the
historical early-return path in `_validate_execution_profile`). The live
protected file is untouched; the row is proven loadable through the real
router from a temp copy.

## Commands and counts

```
env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
  tests/test_t3_native_composition.py tests/test_worker_adapter.py \
  tests/test_executive_worker_broker.py tests/test_t3_execution_adapter.py \
  tests/test_t3_adapter_durability.py tests/test_rev5_contracts_v1_1.py \
  tests/test_executive_claim_job_placement_authority.py \
  tests/test_mmos_admission_to_t3_native_e2e.py \
  tests/test_hermes_selected_child_ingress.py \
  tests/test_ceo_submit_armed_composition.py
→ 785 passed, 117 subtests passed in 81.56s   (d8 identity scans included, green)
```

Side sweep over every other test file referencing `executive_os_phase1c.py`
(source-join, privileged-host prep, isolated entrypoints, subscription broker
definitions, fabric remote composition, web commission source, control-room
install, mixed startup activation, COO launchers, native return transport):
216 passed, 5 failed — ALL five are
`test_native_unix_contract_one_request_no_retry[*]` failing with
`OSError: AF_UNIX path too long` (socket bind under this worktree's long tmp
path); the same tests PASS from a short `--basetemp` (`17 passed`), so they are
a pre-existing environment limitation of deep worktrees, not a regression of
this lane.

## Remaining for live (beyond this lane's source-only work)

1. Apply the route row through the protected-change path for
   `config/executive_worker_routes.json` (owner: that file's normal protected
   path).
2. Enroll the token file on the installed Executive host and set
   `MASTERMIND_T3_MCP_ACCESS_TOKEN_FILE` in the service environment.
3. Register the canary worker (`worker_type: "t3-native"`, quota class above)
   in the installed Runtime; `compose_t3_native_owners_for_service` composes
   its owner at service start.
4. Run the canary through the composed path on the installed Executive; verify
   the pre-ACK binding in `launch_metadata` and a simulated crash recovering
   with zero native launches.
5. Design the remote validation story (`run_validation_argv`) or canary with a
   job shape that needs no local validation argv; likewise the launch-FAILURE
   quarantine branch requires a passing dedicated-UID sweep
   (`require_uid_sweep=start_invoked`) that a remote-thread adapter cannot
   produce — an honest remote sweep story is needed before relying on that
   branch for t3.
6. Only after the canary: flip the row to the hermes shape, add the
   `_ADAPTER_EXECUTION_SURFACES` entry and a `worker_eligible` alias
   (separate reviewed changes).
