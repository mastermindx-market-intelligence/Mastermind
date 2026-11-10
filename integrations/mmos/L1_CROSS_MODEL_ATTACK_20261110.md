# L1 lane adversarial attack — attempt 3 (gemini-4-argon, 2026-11-10)

- **Scope**: `git diff origin/feat/mmos-v1-integration-t3...t3/mmos-v2-l1` (14 files, +4034/-17)
- **Worktree / Branch**: `/Users/chriswong/.t3/worktrees/Mastermind/t3-b6f431e5` (`t3/l1b-attack3-1`; note `t3/l1b-attack3` was already checked out in sibling worktree `t3-d496d4ea`)
- **Scaffold commit**: `6cdf046f3f7647ec093484fe9ccc77b9617487c1` (`docs(mmos): L1 attack3 scaffold`)

---

## Attempt 1/2 Residue Note

Both prior `grok-4.7` adversarial runs were rejected for missing/fabricated deliverables:
- **Attempt 1 (`t3-0643efea` / `t3/l1b-attack-grok`)**: Worktree stayed at `34239c38a` (`Merge branch 't3/mmos-v2-l1' into t3/mmos-v2-l1b`) with zero commits and no `integrations/mmos/L1_CROSS_MODEL_ATTACK_20261110.md` file produced.
- **Attempt 2 (`grok-4.7`)**: Produced no `integrations/mmos/L1_CROSS_MODEL_ATTACK_20261110.md` artifact and reported a branch name and commit SHA that do not exist in any local worktree or on `origin`.

---

## PRIMARY TARGET — `child_request_admit` Gate Enumeration & Unauthorized-Admission Analysis

### Surface Map
1. **MCP HTTP boundary**: `integrations/executive_mcp/hermes_host.py` (`HermesHostMcpBoundary`, `build_hermes_host_mcp_app`, `validate_child_request_admit_arguments`)
2. **COO App forwarding**: `integrations/mastermind_executive_app/coo.py` (`CooApp.child_request_admit`, `_selected_child_frame`, `_child_request_admission_result`)
3. **Hermes delegate caller**: `integrations/hermes_delegate/executive.py` (`HermesExecutiveTransport.admit_child_request`, `HermesExecutiveEndpoint._record_admission_outcome`)
4. **Unix CEO ingress handler**: `control_plane/executive_service.py` (`ExecutiveControlService._handle_selected_child_frame`, `_handle_child_request_admit_frame`, `_selected_child_frame`)
5. **Runtime JobRegistry owner**: `control_plane/executive_runtime.py` (`JobRegistry.admit_child_execution_request`)

### Enumerated Gates (with verbatim code quotes)

#### Gate 1 — Transport trust, Origin check, HTTP method, and Bearer token extraction (`integrations/executive_mcp/hermes_host.py`)
- **Path & Origin gate** (`integrations/executive_mcp/hermes_host.py:165-174`):
```python
        origin = _header(scope, b"origin")
        if origin is not None and not self._app._origin_allowed(origin):
            await Response(
                "Forbidden origin", status_code=403, media_type="text/plain"
            )(scope, receive, send)
            return
        if scope.get("method", "").upper() != "POST":
```
- **Bearer token & JWT verification gate** (`integrations/executive_mcp/hermes_host.py:181-190`):
```python
        token = _bearer_token(scope)
        if token is None:
            await _unauthorized("missing_bearer_token")(scope, receive, send)
            return
        try:
            authenticated = await self._app.authorize_token(token)
        except AuthError as exc:
```
- **Host-only tool exposure (`child_request_admit` excluded from model-facing `COO_TOOL_NAMES`)** (`integrations/executive_mcp/hermes_host.py:124-131`):
```python
    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any] | None):
        if name != CHILD_REQUEST_ADMIT_TOOL_NAME:
            return _tool_result({
                "ok": False,
                "error": {"kind": "refused",
                          "message": f"unknown host tool: {name!r}"},
            })
```

#### Gate 2 — Closed argument validation (`integrations/executive_mcp/hermes_host.py:67-93`)
```python
    if set(arguments) != {"work_ref", "command"}:
        raise ValueError(
            "child_request_admit accepts exactly work_ref and command"
        )
    work_ref = arguments["work_ref"]
    command = arguments["command"]
    if not isinstance(work_ref, str) or not WORK_REF_RE.fullmatch(work_ref):
        raise ValueError("work_ref must be a canonical WS-<ULID>")
    if not isinstance(command, str) or not CHILD_REQUEST_COMMAND_RE.fullmatch(command):
        raise ValueError("command must be a canonical child-request:<sha256>")
```

#### Gate 3 — App-side rate limit, target presence, and principal authority (`integrations/mastermind_executive_app/coo.py:680-715`)
```python
        principal, blocked = self._enter(
            request, authenticated, "child_request_admit", str(raw_work_ref or ""))
        if blocked is not None:
            return blocked
        target = self._selected_child_target
        if target is None:
            return self._refused(request, principal, "child_request_admit",
                                 raw_work_ref, "conflict",
                                 "EXECUTIVE_CHILD_REQUEST_TARGET_NOT_BOUND")
```
```python
        work_ref = validated["work_ref"]
        command = validated["command"]
        authority, denied = self._authority(
            request, principal, "child_request_admit", work_ref, stamp)
        if denied is not None:
            return denied
```

#### Gate 4 — Unix socket frame schema & target digest verification (`control_plane/executive_service.py:2114-2135`, `6797-6824`)
- **Frame schema check** (`control_plane/executive_service.py:2114-2122`):
```python
    if raw.get("schema") != SELECTED_CHILD_FRAME_SCHEMA:
        raise ValueError("selected-child frame schema mismatch")
    expected = {
        "schema", "principal", "principal_context", "capability_profile_digest",
        "target_digest", "request",
    }
    if set(raw) != expected:
        raise ValueError("selected-child frame must contain the exact fields")
```
- **Target digest check & early dispatch to `_handle_child_request_admit_frame`** (`control_plane/executive_service.py:6806-6824`):
```python
        if parsed["target_digest"] != target.material_digest():
            await self._write_error(
                writer, code="conflict",
                message="EXECUTIVE_SELECTED_CHILD_TARGET_DIGEST_MISMATCH")
            return
        if action == "selected_child_admit":
            await self._handle_child_request_admit_frame(
                writer, app_binding=app_binding,
                require_current=require_current, command=command)
            return
```

#### Gate 5 — Service-side current-binding & frozen-material lookup (`control_plane/executive_service.py:6944-6994`)
```python
        if not require_current():
            await self._write_error(
                writer, code="conflict",
                message="EXECUTIVE_SELECTED_CHILD_BINDING_NOT_CURRENT")
            return
        materials = app_binding.child_request_material or {}
        if command not in materials:
            await self._write_error(
                writer, code="invalid_input",
                message="EXECUTIVE_CHILD_REQUEST_COMMAND_NOT_FROZEN")
            return
        raw_envelope = materials[command]
```

#### Gate 6 — Runtime admission, replay/conflict idempotency, parent/root lineage, and queue bounds (`control_plane/executive_runtime.py:16702-16915`)
- **Closed envelope validation**: `validate_child_execution_request(raw_request)` (`executive_runtime.py:16711`).
- **Command-ID replay / digest conflict check** (`executive_runtime.py:16716-16738`):
```python
        existing_command = self._load_admitted_child_request_by_command(
            command_id
        )
        if existing_command is not None:
            if existing_command["request_digest"] != request_digest:
                raise StateConflict(
                    f"child_request command_id {command_id!r} already admitted "
                    f"with digest {existing_command['request_digest']!r}, "
                    f"got {request_digest!r}"
                )
```
- **Logical child key (`(root_ref, immediate_parent_ref, logical_child_key)`) conflict / replay check** (`executive_runtime.py:16740-16768`).
- **Root/parent lineage & active-state check** (`executive_runtime.py:16770-16838`).
- **Atomic `BEGIN IMMEDIATE` transaction re-check (`recheck_inside_transaction`) + `UNIQUE` constraint on `events.command_id`** (`executive_runtime.py:16863-16906`).

---

### Answer to Primary Target Question: What concrete input or state makes `child_request_admit` admit something unauthorized?

**Concrete bypass identified (see `L1B3-1` below):**
1. **Cross-workstream `work_ref` + skipped service-side principal/grant/work_ref verification**:
   - In `integrations/mastermind_executive_app/coo.py:582`, `CooApp._selected_child` explicitly enforces `if work_ref != target.work_ref: return self._refused(..., "EXECUTIVE_SELECTED_CHILD_WORK_REF_MISMATCH")`. **`CooApp.child_request_admit` (`coo.py:673-745`) omits this check.** It validates `self._authority(request, principal, "child_request_admit", work_ref, stamp)` against whatever `work_ref` the caller passed in `arguments["work_ref"]`.
   - Then, in `control_plane/executive_service.py:6816-6824`, `if action == "selected_child_admit":` branches and **returns at line 6824 BEFORE `require_read_current()` (lines 6866-6906)**.
   - `require_read_current()` is the sole function on the service side of the Unix socket that calls `app_binding.principal_facts_factory(runtime)` and verifies:
     1. `parsed["principal"] == expected_principal`
     2. `parsed["principal_context"] == expected_context`
     3. `parsed["capability_profile_digest"] == expected_grant_digest`
     4. `parsed["principal_context"]["work_ref"] == target.work_ref`
   - Because `_handle_child_request_admit_frame` (`executive_service.py:6944-7025`) only calls `require_current()` (which checks `self._ceo_ingress_app_binding == app_binding`) and never calls `require_read_current()`, **the service side of the Unix socket never inspects `principal`, `principal_context`, `capability_profile_digest`, or `work_ref` on `selected_child_admit` frames**.
   - **Concrete exploit states**:
     - **State A (Cross-workstream admission via HTTP MCP)**: A caller holds a valid Bearer token and authority for workstream `WS_OTHER`, while `_selected_child_target` is bound to `WS_TARGET`. Calling `child_request_admit(work_ref=WS_OTHER, command=cmd)` passes `CooApp._authority` (checked against `WS_OTHER`), sends the frame with `principal_context.work_ref = WS_OTHER`, skips `require_read_current()` in `executive_service.py`, and admits `cmd` into `WS_TARGET`'s root job despite the caller having zero authority over `target.work_ref` (`WS_TARGET`) and despite `principal_facts_factory(runtime)` being bound to `WS_TARGET`.
     - **State B (Revoked/rotated runtime principal or local Unix socket frame)**: If the runtime's `principal_facts_factory(runtime)` rotates or revokes the principal/grant (which `require_read_current()` catches for `selected_child_status`/`selected_child_Result`), `selected_child_admit` still succeeds because `require_current()` only checks object identity of `self._ceo_ingress_app_binding`, never `principal_facts_factory(runtime)`. Similarly, any local process reaching the Unix socket only needs `target.material_digest()` and `command` — arbitrary dummy strings for `principal`, `principal_context`, and `capability_profile_digest` pass `_selected_child_frame` and are ignored by `_handle_child_request_admit_frame`.
     - **State C (Unverified `child_request_material` key->envelope binding)**: `_handle_child_request_admit_frame` (`executive_service.py:6969-6994`) looks up `raw_envelope = materials[command]` and calls `runtime.jobs.admit_child_execution_request(request)` without verifying `admission_command_id(request) == command` (only asserting `outcome["command_id"] == command` after the DB transaction has already committed at line 7013).

---

## SECONDARY — Adjudication of Prior Claims P1–P5

### P1 — `T3ModelRouteDriftError` (`control_plane/t3_execution_adapter.py:2314`)
- **Verdict**: **CONFIRM lead refutation (NOT a defect; designed fail-closed drift refusal, tested).**
- **Quoted code** (`control_plane/t3_execution_adapter.py:2313-2323`):
```python
        if spec_model != claimed_model:
            raise T3ModelRouteDriftError(
                f"spec.model {spec_model!r} drifts from claimed route "
                f"binding.model_ref {binding.model_ref!r} "
                f"(derived model {claimed_model!r})"
            )
```
- **Quoted test** (`tests/test_t3_execution_adapter.py:397-413`):
```python
def test_launch_refuses_spec_model_drift_from_claimed_route():
    port = FakeT3Port()
    adapter = T3ExecutionAdapter(port=port)
    with pytest.raises(T3ModelRouteDriftError, match="drifts from claimed route"):
        adapter.launch(_spec(model="gpt-5.4"), _binding())
    assert port.launch_calls == []
```
- **Analysis**: `_launch_envelope` derives `model_selection` from `binding.model_ref` + `binding.provider_instance_ref` and refuses `spec.model` mismatch before `claim_launch_intent` is written. When `spec.model` is empty (`""`), only `binding.model_ref` is used (`t3_execution_adapter.py:2305-2312`).

### P2 — `providerInstanceId` loss in `port_factory` path (`control_plane/t3_execution_adapter.py:3655, 3780` & `control_plane/t3_native_composition.py:725-733`)
- **Verdict**: **PARTIAL OVERTURN (default `T3McpToolPort` path preserves `providerInstanceId`, but custom `port_factory` in `compose_t3_native_adapter` silently drops `resolved_launch_arguments`, including `providerInstanceId`).**
- **Quoted code (default `T3McpToolPort` preserves host `providerInstanceId` and refuses mismatch)** (`control_plane/t3_execution_adapter.py:3654-3663`, `3778-3786`):
```python
        configured_instance = self._launch_arguments.get("providerInstanceId")
        if configured_instance is not None and (
            not isinstance(configured_instance, str) or not configured_instance.strip()
        ):
            raise T3ExecutionAdapterError(
                "T3McpToolPort launch_arguments.providerInstanceId must be a non-empty string"
            )
```
```python
            if (
                self._provider_instance_id
                and model_instance
                and model_instance != self._provider_instance_id
            ):
                raise T3ModelRouteDriftError(
```
- **Quoted code (custom `port_factory` drops `resolved_launch_arguments`)** (`control_plane/t3_native_composition.py:722-733`):
```python
    if port_factory is None:
        resolved_launch_arguments = _resolve_launch_arguments_for_composition(
            launch_arguments=launch_arguments,
            launch_arguments_file=launch_arguments_file,
            environ=environ,
        )
        port = T3McpToolPort(
            invoker=invoker,
            launch_arguments=resolved_launch_arguments,
        )
    else:
        port = port_factory(invoker)
```
- **Analysis**: In the default `port_factory is None` path, `T3McpToolPort` injects `self._provider_instance_id` into `modelSelection.options.providerInstanceId` (`t3_execution_adapter.py:3789-3793`) and refuses drift against `envelope.model_selection`. However, when `port_factory` is supplied to `compose_t3_native_adapter`, lines 697–706 validate `launch_arguments` / `launch_arguments_file`, and then lines 722–733 skip `_resolve_launch_arguments_for_composition` completely and call `port_factory(invoker)` without passing the resolved launch arguments (see `L1B3-3`).

### P3 — `launch_arguments` + `launch_arguments_file` both-configured refusal & test gap (`control_plane/t3_native_composition.py:650-657, 697-706`)
- **Verdict**: **CONFIRM BOTH (the both-sources refusal is typed at `t3_native_composition.py:650-657` and `697-706`, AND there is zero test coverage for the both-sources refusal across `tests/`; furthermore, ambient `MASTERMIND_T3_LAUNCH_ARGUMENTS_FILE` triggers an unintended refusal when programmatic `launch_arguments` is passed — see `L1B3-2`).**
- **Quoted code** (`control_plane/t3_native_composition.py:648-657`, `697-706`):
```python
    resolved_file = resolve_t3_launch_arguments_file(
        launch_arguments_file, environ=environ
    )
    if launch_arguments is not None and resolved_file is not None:
        raise T3AdapterCompositionError(
            "specify at most one of launch_arguments or launch_arguments_file"
        )
```
- **Grep verification across `tests/`**:
  - Searching `tests/` for `specify at most one of launch_arguments` returns **0 matches**.
  - In `tests/test_t3_native_composition.py:381-465`, tests cover `launch_arguments` alone, `launch_arguments_file` alone, `MASTERMIND_T3_LAUNCH_ARGUMENTS_FILE` alone, missing file, non-object JSON, unknown keys, and `environmentId` refusal — never both together.

### P4 — `root_id` chain and fallback source labeling (`control_plane/execution_return_wiring.py:321-330`)
- **Verdict**: **CONFIRM residual gap (the fallback chain prefers `child_request.root_ref`, then `binding.root_run_ref`, then `str(job.root_job_id or job.job_id)`, and the emitted `execution_return/v1` record does NOT label which source produced `attempt.root_id`).**
- **Quoted code** (`control_plane/execution_return_wiring.py:317-330`):
```python
        root_id = str(
            child_request.get("root_ref")
            or binding.get("root_run_ref")
            or getattr(job, "root_job_id", None)
            or job.job_id
        )
```
- **Quoted projection schema** (`control_plane/execution_return_projection.py:21-31`):
```python
_ATTEMPT_KEYS = frozenset({
    "root_id",
    "job_id",
    "attempt_id",
    "logical_child_id",
    "idempotency_key",
    "adapter_id",
    "provider_session_id",
    "fence_generation",
})
```
- **Analysis**: `_ATTEMPT_KEYS` is a closed keyset without a `root_id_source` field. When a job has no `child_request.root_ref` and no `binding.root_run_ref`, `attempt.root_id` silently falls back to `str(job.root_job_id or job.job_id)` (a `JOB-...` identifier rather than an external root run reference) with no provenance discriminator in `execution_return/v1`. In addition, see `L1B3-4` for a related `attempt.idempotency_key` violation in `execution_return_wiring.py:332-338`.

### P5 — Canary harness death realism (`integrations/t3/live_proof/t3_admitted_canary.py`)
- **Verdict**: **CONFIRM realism for R4 (`os._exit(90)` in a real child subprocess after SQLite `put_launch_receipt`, followed by cold P2 subprocess recovery), with one documented sidecar nuance (`main-p1-lease.json`).**
- **Quoted P1 crash hook** (`integrations/t3/live_proof/t3_admitted_canary.py:478-493`):
```python
class CrashHookStore:
    """Wraps SQLiteT3AdapterStateStore and calls os._exit(90) right after
    put_launch_receipt commits."""
...
    def put_launch_receipt(self, *args: Any, **kwargs: Any) -> Any:
        result = self._inner.put_launch_receipt(*args, **kwargs)
        self._arm_marker_path.write_text("armed-and-exiting\n", encoding="utf-8")
        os._exit(CRASH_EXIT_CODE)
```
- **Quoted P2 cold recovery** (`integrations/t3/live_proof/t3_admitted_canary.py:648-680`):
```python
    ref = adapter.reattach(spec, binding)
    reattach_ms = _now_ms()
    runtime.attempts.record_process(
        attempt_id,
        fence_generation=int(lease_meta["fence_generation"]),
        lease_token=str(lease_meta["lease_token"]),
        pid=ref.pid,
        pgid=ref.pgid,
        provider_session_id=ref.provider_session_id,
    )
    adopted = runtime.attempts.adopt_attempt(
        attempt_id,
        expected_fence_generation=int(lease_meta["fence_generation"]),
        lease_owner="canary-p2-supervisor",
    )
```
- **Analysis**: P1 is spawned via `subprocess.Popen` (`t3_admitted_canary.py:926-937`) and truly dies with `os._exit(90)` (`p1_exit_code == 90`) after `SQLiteT3AdapterStateStore.put_launch_receipt` commits and before `runtime.attempts.record_process` runs in P1. P2 runs in a fresh `subprocess.Popen` (`t3_admitted_canary.py:953-965`). Note the architectural nuance: because `AttemptRegistry.adopt_attempt` (`control_plane/executive_runtime.py:20528`) refuses to adopt an attempt when `row["pid"] is None and row["provider_session_id"] is None`, P1 writes its in-memory `lease_token` to a test sidecar file `main-p1-lease.json` (`t3_admitted_canary.py:598-609`) before launching so P2 can call `record_process` using P1's `lease_token` before calling `adopt_attempt`. That proves `T3ExecutionAdapter.reattach` is genuinely cold across process death, while showing that production `ExecutiveSupervisor` still lacks a pre-`record_process` crash bridge (see `L1B3-5`).

---

## FRESH HUNT — Findings (`L1B3-1` .. `L1B3-6`)

### `L1B3-1` — CRITICAL: `selected_child_admit` skips `require_read_current()` on the Unix service boundary and omits `work_ref == target.work_ref` in `CooApp.child_request_admit`
- **File:Line**: `control_plane/executive_service.py:6816-6824` (and `integrations/mastermind_executive_app/coo.py:682-715`, `control_plane/executive_service.py:6969-6994`)
- **Verbatim Quote**:
```python
        if action == "selected_child_admit":
            await self._handle_child_request_admit_frame(
                writer, app_binding=app_binding,
                require_current=require_current, command=command)
            return
```
- **Severity**: **CRITICAL**
- **Concrete Failure Scenario**:
  1. `CooApp._selected_child` (`coo.py:582`) checks `if work_ref != target.work_ref:`, but `CooApp.child_request_admit` (`coo.py:673-715`) never checks `work_ref == target.work_ref`. It validates `self._authority(request, principal, "child_request_admit", work_ref, stamp)` against the caller-supplied `work_ref`.
  2. When the frame arrives on the Unix socket at `ExecutiveControlService._handle_selected_child_frame` (`executive_service.py:6816`), `action == "selected_child_admit"` dispatches to `_handle_child_request_admit_frame` and returns at line 6824 **before** `require_read_current()` (lines 6866–6906).
  3. Consequently, `_handle_child_request_admit_frame` never verifies `parsed["principal"]`, `parsed["principal_context"]`, `parsed["capability_profile_digest"]`, or `parsed["principal_context"]["work_ref"] == target.work_ref` against `app_binding.principal_facts_factory(runtime)`. A caller authorized on `WS_A` can call `child_request_admit(work_ref=WS_A, command=cmd)` against an App whose frozen target is `WS_B` and admit `cmd` into `WS_B`. Furthermore, `_handle_child_request_admit_frame` (`executive_service.py:6969-6994`) does not check `admission_command_id(request) == command` before committing `runtime.jobs.admit_child_execution_request(request)`.
- **Minimal Fix**:
  1. In `integrations/mastermind_executive_app/coo.py:709`, enforce `if work_ref != target.work_ref: return self._refused(request, principal, "child_request_admit", work_ref, "conflict", "EXECUTIVE_SELECTED_CHILD_WORK_REF_MISMATCH")` before `self._authority(...)`.
  2. In `control_plane/executive_service.py`, move the `if action == "selected_child_admit":` dispatch **after** `if not await require_read_current(): return` (line 6908) so `selected_child_admit` enforces the exact same `principal_facts_factory(runtime)` and `target.work_ref` checks as `selected_child_status`/`selected_child_result`.
  3. In `_handle_child_request_admit_frame` (`executive_service.py:6977`), verify `admission_command_id(request) == command` before calling `runtime.jobs.admit_child_execution_request(request)`.

---

### `L1B3-2` — HIGH: Ambient `MASTERMIND_T3_LAUNCH_ARGUMENTS_FILE` breaks explicit `launch_arguments={...}` in `compose_t3_native_adapter`, and `both-sources` refusal is untested
- **File:Line**: `control_plane/t3_native_composition.py:648-657` (and `697-706`)
- **Verbatim Quote**:
```python
    resolved_file = resolve_t3_launch_arguments_file(
        launch_arguments_file, environ=environ
    )
    if launch_arguments is not None and resolved_file is not None:
        raise T3AdapterCompositionError(
```
- **Severity**: **HIGH**
- **Concrete Failure Scenario**:
  `resolve_t3_launch_arguments_file(launch_arguments_file, environ=environ)` falls back to `(environ if environ is not None else os.environ).get("MASTERMIND_T3_LAUNCH_ARGUMENTS_FILE")` (`t3_native_composition.py:242-246`). On a host where `MASTERMIND_T3_LAUNCH_ARGUMENTS_FILE` is set in the service environment (the standard M2 deployment configuration), any caller or test invoking `compose_t3_native_adapter(..., launch_arguments={"projectId": ...})` without explicitly passing `environ={}` raises `T3AdapterCompositionError("specify at most one of launch_arguments or launch_arguments_file")` because `resolved_file` is populated from the env var even though `launch_arguments_file=None`. Additionally, no test in `tests/test_t3_native_composition.py` exercises the both-sources refusal.
- **Minimal Fix**:
  Refuse only when both `launch_arguments is not None` and `launch_arguments_file is not None` are explicitly passed; when `launch_arguments is not None` and `launch_arguments_file is None`, do not consult `MASTERMIND_T3_LAUNCH_ARGUMENTS_FILE`. Add a unit test in `tests/test_t3_native_composition.py` asserting `T3AdapterCompositionError` when both `launch_arguments` and `launch_arguments_file` are supplied.

---

### `L1B3-3` — MEDIUM: `compose_t3_native_adapter` validates `launch_arguments` / `launch_arguments_file` but silently drops them when `port_factory` is provided
- **File:Line**: `control_plane/t3_native_composition.py:722-733`
- **Verbatim Quote**:
```python
    if port_factory is None:
        resolved_launch_arguments = _resolve_launch_arguments_for_composition(
            launch_arguments=launch_arguments,
...
    else:
        port = port_factory(invoker)
```
- **Severity**: **MEDIUM**
- **Concrete Failure Scenario**:
  A caller passes `compose_t3_native_adapter(..., port_factory=my_factory, launch_arguments={"projectId": "...", "workspaceStrategy": "worktree", "providerInstanceId": "codex2"})`. Lines 697–706 validate the arguments, but lines 722–733 skip `_resolve_launch_arguments_for_composition` in the `else` branch and never pass `resolved_launch_arguments` to `port_factory` (nor refuse the combination), silently losing `projectId`, `workspaceStrategy`, and `providerInstanceId`.
- **Minimal Fix**:
  Either refuse `launch_arguments` / `launch_arguments_file` when a custom `port_factory` is supplied (raising `T3AdapterCompositionError`), or resolve `resolved_launch_arguments` unconditionally and pass it to `port_factory` when accepted.

---

### `L1B3-4` — MEDIUM: `ExecutionReturnWiring._deliver` populates `attempt.idempotency_key` with `child_request.command_id` instead of the execution binding's `operation_key`
- **File:Line**: `control_plane/execution_return_wiring.py:331-338`
- **Verbatim Quote**:
```python
        idempotency_key = str(
            child_request.get("command_id")
            or binding.get("operation_key")
            or getattr(job, "idempotency_key", None)
            or f"job:{job.job_id}:attempt:{attempt.attempt_id}"
        )
```
- **Severity**: **MEDIUM**
- **Concrete Failure Scenario**:
  In `execution_return/v1`, `attempt` represents the per-attempt execution provenance (`attempt_id`, `adapter_id`, `provider_session_id`, `fence_generation`, `idempotency_key`). For every child job admitted via `ChildExecutionRequest.v1`, `child_request.get("command_id")` is non-empty (`"child-request:<sha256>"`, which is the job-creation admission command ID, invariant across retries), whereas the attempt's execution idempotency key is `binding.get("operation_key")` (or `derive_t3_client_request_id(binding)`). Because `child_request.get("command_id")` comes first in the `or` chain, `attempt.idempotency_key` always records the job-level `child-request:...` command ID and masks `binding.operation_key` across multiple attempts of the same job.
- **Minimal Fix**:
  Prefer `binding.get("operation_key")` first for `attempt.idempotency_key` (falling back to `child_request.get("command_id")`, `job.idempotency_key`, then `f"job:{job.job_id}:attempt:{attempt.attempt_id}"`), and include an explicit `root_id_source` or document the `root_id` fallback precedence.

---

### `L1B3-5` — MEDIUM: Production `ExecutiveSupervisor` cannot adopt a T3 attempt that crashed between `SQLiteT3AdapterStateStore.put_launch_receipt` and `AttemptRegistry.record_process`
- **File:Line**: `control_plane/executive_supervisor.py:5490-5503` (and `control_plane/executive_runtime.py:20527-20532`, `integrations/t3/live_proof/t3_admitted_canary.py:648-680`)
- **Verbatim Quote**:
```python
            if current.pid is None and current.provider_session_id is None:
                outcomes.append(
                    self._persist_reconciliation_evidence(
                        ReconcileReceipt(
                            attempt_id=current.attempt_id,
                            job_id=current.job_id,
                            status=ReconcileStatus.AWAITING_LEASE_EXPIRY,
```
- **Severity**: **MEDIUM**
- **Concrete Failure Scenario**:
  When a worker supervisor crashes right after `T3ExecutionAdapter.launch` commits `put_launch_receipt` to `SQLiteT3AdapterStateStore` (the exact R4 crash window in `t3_admitted_canary.py:489-493`), `runtime.attempts.record_process` has not yet run on `AttemptRegistry`, so the `attempts` table still has `pid IS NULL AND provider_session_id IS NULL`. In `t3_admitted_canary.py:604, 665-674`, P2 works around this by reading P1's `lease_token` from a test-only sidecar file (`main-p1-lease.json`) and calling `record_process` before `adopt_attempt`. In production, `lease_token` is held only in P1's memory (`executive_runtime.py:20489`), `AttemptRegistry.adopt_attempt` refuses when `pid is None and provider_session_id is None` (`executive_runtime.py:20528`), and `ExecutiveSupervisor` (`executive_supervisor.py:5490-5503`) classifies the attempt as `AWAITING_LEASE_EXPIRY` and then `EXPIRED_LOST` — stranding the live T3 thread instead of calling `adapter.reattach(spec, binding)`.
- **Minimal Fix**:
  During supervisor startup reconciliation, when `current.pid is None and current.provider_session_id is None` and the configured adapter supports `reattach(spec, binding)` with a persisted adapter receipt in `SQLiteT3AdapterStateStore`, allow `adopt_attempt` (or a dedicated `adopt_unrecorded_launch` transition) to bind `provider_session_id` from `adapter.reattach(spec, binding)` under a new `fence_generation`.

---

### `L1B3-6` — LOW: Tautological assertions (`assert "x" in text or True`) in `tests/test_t3_admitted_canary_receipt.py` cannot fail
- **File:Line**: `tests/test_t3_admitted_canary_receipt.py:163` and `tests/test_t3_admitted_canary_receipt.py:206`
- **Verbatim Quote**:
```python
    assert "4bc4" in text or "a78a" in text or True  # historical note is free-form; check keys below
```
```python
        assert status in ("completed", "succeeded", "idle", "ready") or len(status) > 0
```
- **Severity**: **LOW**
- **Concrete Failure Scenario**:
  - At `tests/test_t3_admitted_canary_receipt.py:163`, `assert "4bc4" in text or "a78a" in text or True` evaluates to `True` unconditionally for any string `text`.
  - At `tests/test_t3_admitted_canary_receipt.py:206`, line 205 already asserts `assert isinstance(status, str) and status.strip()`, so `or len(status) > 0` makes line 206 unconditionally `True` even if `status == "failed"` or `"errored"`.
- **Minimal Fix**:
  Remove the dead assertion at line 163 (or assert a real required substring), and replace line 206 with `assert status in ("completed", "succeeded", "idle", "ready")` so terminal failure statuses fail the receipt check.
