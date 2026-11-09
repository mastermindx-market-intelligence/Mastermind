# Executive Privileged Action Broker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make reviewed macOS root effects and Codex/Claude permission posture unattended without exposing an administrator password or arbitrary root execution.

**Architecture:** A socket-activated root executor accepts only typed catalogued actions from the installed operator/control UID, writes idempotent effect receipts, and invokes exact root-owned Executive OS release scripts. Provider permission configuration is separately verified/applied so Codex and Claude do not stop for their own approval UIs.

**Tech Stack:** Python 3.12 stdlib, asyncio/AF_UNIX, macOS launchd, Bash installer, pytest, TOML/JSON operator settings.

**Spec:** `docs/superpowers/specs/2026-09-13-executive-privileged-action-broker-design.md`

## Global Constraints

- Protected implementation base is `f087f9cf90a8fc7a81273c2576eefa6d06b54d9e`.
- No arbitrary shell/argv/path request surface and no caller-supplied executable.
- No secret bytes in requests, receipts, logs, tests, or chat.
- Root executes only code in a root-owned exact installed Executive release.
- No new Job queue, retry scheduler, identity plane, or authority database.
- V1 actions are exactly the six actions named in the spec.
- Real root installation occurs only after merge from exact protected master.

---

### Task 1: Typed privileged-action contract

**Files:**
- Create: `control_plane/executive_privileged_action.py`
- Create: `tests/test_executive_privileged_action.py`

**Interfaces:**
- Produces `PrivilegedActionRequest`, `ValidatedPrivilegedAction`, `validate_request(raw)`, and `build_argv(validated, release_root)`.
- Later broker code consumes only these validated objects; it never interprets caller strings directly.
- [ ] **Step 1: Write failing contract tests**

```python
def test_unknown_action_refuses():
    with pytest.raises(PrivilegedActionError, match="unknown privileged action"):
        validate_request({"schema": REQUEST_SCHEMA, "request_id": "req-001", "action": "shell", "args": {}})

def test_service_start_has_fixed_argv(tmp_path):
    request = validate_request({"schema": REQUEST_SCHEMA, "request_id": "req-002", "action": "executive.services.start", "args": {}})
    assert build_argv(request, tmp_path) == ("/bin/bash", str(tmp_path / "ops/executive_os/service-control.sh"), "start")
```

- [ ] **Step 2: Run tests and observe RED**

Run: `python3 -m pytest -q tests/test_executive_privileged_action.py`
Expected: import/module failure because the contract does not exist.

- [ ] **Step 3: Implement the minimal immutable action catalog and validators**

Use dataclasses, strict set-equality for request/args keys, `^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$` request ids, reviewed slot ids, and exact `YYYY-MM-DDTHH:MM:SSZ` UTC parsing. Build argv only from catalog constants plus validated scalar values.

- [ ] **Step 4: Run Task 1 tests GREEN and commit**

Run: `python3 -m pytest -q tests/test_executive_privileged_action.py`
Commit: `feat(executive): add typed privileged action contract`

### Task 2: Root broker, receipts, and effect uncertainty

**Files:**
- Create: `control_plane/executive_privileged_broker.py`
- Create: `tests/test_executive_privileged_broker.py`

**Interfaces:**
- `PrivilegedBrokerConfig.from_mapping(mapping)` validates root-owned paths/UID policy.
- `PrivilegedActionBroker.handle(raw_request, peer_uid)` returns one JSON-safe receipt/result mapping.
- `run_broker(config, activated_socket=None)` is the service entrypoint.
- [ ] **Step 1: Write failing broker tests**

```python
def test_peer_uid_must_be_allowlisted(tmp_path):
    broker = make_broker(tmp_path, allowed_peer_uids=(501,))
    with pytest.raises(PeerAuthorizationError):
        broker.handle(valid_service_request("req-001"), peer_uid=502)

def test_stale_inflight_is_effect_unknown(tmp_path):
    broker = make_broker(tmp_path)
    broker.inflight_path("req-002").write_text('{"request_sha256":"deadbeef"}')
    with pytest.raises(EffectUnknownError):
        broker.handle(valid_service_request("req-002"), peer_uid=501)
```

Also test matching terminal receipt replay, mismatched request-id reuse refusal, bounded diagnostics, and no spawn when receipt persistence cannot establish the in-flight marker.

- [ ] **Step 2: Run tests RED**

Run: `python3 -m pytest -q tests/test_executive_privileged_broker.py`
Expected: module/import failure.

- [ ] **Step 3: Implement broker with injected executor for CI**

Use atomic `os.replace`, `fsync` on files/directories, canonical JSON SHA-256, `subprocess.run(argv, shell=False, env=CLOSED_ENV, cwd=release_root, timeout=...)`, and bounded sanitized diagnostics. Production startup requires EUID 0; unit tests inject `require_root=False` and a fake executor only through constructor arguments unavailable on the CLI.

- [ ] **Step 4: Run broker tests GREEN and commit**

Run: `python3 -m pytest -q tests/test_executive_privileged_broker.py`
Commit: `feat(executive): add receipt-gated privileged broker`

### Task 3: Broker service/client CLI

**Files:**
- Create: `scripts/executive_os_privileged_broker.py`
- Create: `scripts/mmx_admin.py`
- Create: `tests/test_mmx_admin.py`

**Interfaces:**
- Broker CLI: `serve --config /absolute/root-owned/config.json` only.
- Client CLI: `ACTION [--request-id ID]` plus action-specific typed flags; it sends one newline-delimited JSON request and prints only the secret-free JSON response.
- [ ] **Step 1: Write failing CLI tests**

```python
def test_client_builds_verify_ready_request():
    request = build_request(["executive.worker_auth.verify_ready", "--slot-id", "codex-pro-01", "--credential-expires-at", "2026-09-14T00:00:00Z"])
    assert request["action"] == "executive.worker_auth.verify_ready"
    assert request["args"]["slot_id"] == "codex-pro-01"
```

- [ ] **Step 2: Run RED, implement strict argparse/client framing, rerun GREEN**

Run: `python3 -m pytest -q tests/test_mmx_admin.py`
The client socket path defaults to `/var/run/mastermind-executive/privileged.sock` and can be overridden only by an explicit CLI flag for tests; the broker production CLI has no executor/path override.

- [ ] **Step 3: Commit**

Commit: `feat(executive): add mmx-admin privileged client`

### Task 4: launchd + exact-release installer integration

**Files:**
- Create: `ops/executive_os/com.mastermind.executive.privileged.plist.template`
- Modify: `ops/executive_os/install.sh`
- Modify: `tests/test_executive_launchd_config.py`
- Modify: `ops/executive_os/HOST_PREREQUISITES.md`

**Interfaces:**
- Installer flag: `--arm-privileged-broker`.
- Config: `/Library/Application Support/MastermindExecutive/config/privileged-broker.json`, root:wheel 0400.
- Socket: `/var/run/mastermind-executive/privileged.sock`, operator UID + ops GID, mode 0660.
- Receipt root: `/var/db/mastermind-executive/privileged-actions`, root:wheel 0700.

- [ ] **Step 1: Add failing static launchd/install tests**

Assert the plist has no shell, no `KeepAlive`, no environment secrets, root identity, socket activation, and fixed broker entrypoint. Assert install requires the explicit arm flag before `launchctl enable/bootstrap` and writes allowed peer UIDs from the resolved operator/control accounts.

- [ ] **Step 2: Run targeted RED**

Run: `python3 -m pytest -q tests/test_executive_launchd_config.py -k 'privileged or service_lifecycle'`
- [ ] **Step 3: Implement installation**

Install the plist/config from the exact release with root ownership and closed modes. Do not modify `/etc/sudoers`. When the arm flag is absent, explicitly disable/bootout the privileged label like other inert installed surfaces. When present, validate plist/config, enable the label, bootstrap the plist, and verify the socket exists with expected metadata before reporting arm success.

- [ ] **Step 4: Run static tests GREEN and commit**

Run: `python3 -m pytest -q tests/test_executive_launchd_config.py -k 'privileged or service_lifecycle'`
Commit: `feat(executive): install socket-activated privileged broker`

### Task 5: Provider permission profile manager

**Files:**
- Create: `ops/executive_os/provider_autonomy_profile.py`
- Create: `tests/test_provider_autonomy_profile.py`
- Modify: `ops/executive_os/HOST_PREREQUISITES.md`

**Interfaces:**
- `verify --codex-config PATH --claude-settings PATH` is read-only and exits nonzero on drift.
- `apply --codex-config PATH --claude-settings PATH` updates only the two reviewed Codex keys and Claude `permissions.defaultMode`, preserving unrelated settings and atomically creating `.mastermind-backup` files before the first mutation.

- [ ] **Step 1: Write failing profile tests**

```python
def test_apply_preserves_unrelated_claude_settings(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"model":"opus","permissions":{"allow":[]}}')
    apply_claude(path)
    value = json.loads(path.read_text())
    assert value["model"] == "opus"
    assert value["permissions"]["defaultMode"] == "bypassPermissions"
```

Also test Codex normalization to `sandbox_mode = "danger-full-access"` and `approval_policy = "never"`, idempotence, malformed-file refusal, and verify-only drift reporting.

- [ ] **Step 2: Run RED, implement minimal atomic manager, run GREEN**

Run: `python3 -m pytest -q tests/test_provider_autonomy_profile.py`

- [ ] **Step 3: Apply and verify on the Mac Studio user profile**

Run the checked-in tool against `/Users/chriswong/.codex/config.toml` and `/Users/chriswong/.claude/settings.json`, then run `verify`. Never print credential-bearing settings values.

- [ ] **Step 4: Commit**

Commit: `feat(executive): standardize unattended provider permissions`
### Task 6: Integrated verification and adversarial review

**Files:** all files above.

- [ ] **Step 1: Run the focused suite**

Run: `python3 -m pytest -q tests/test_executive_privileged_action.py tests/test_executive_privileged_broker.py tests/test_mmx_admin.py tests/test_provider_autonomy_profile.py tests/test_executive_launchd_config.py`

- [ ] **Step 2: Run source-security scans**

Search changed files for `shell=True`, `os.system`, `eval(`, `exec(`, `/etc/sudoers`, `NOPASSWD: ALL`, password literals, caller-selected executable/path fields, and unbounded stdout/stderr persistence. Every occurrence must be absent or an explicit negative test/doc statement.

- [ ] **Step 3: Run the original baseline suite**

Run: `python3 -m pytest -q tests/test_executive_authority.py tests/test_executive_worker_auth_provisioner.py tests/test_executive_launchd_config.py`
Expected: no new failures beyond the pre-existing `test_acceptance_rejects_existing_receipt_container_metadata_drift` baseline failure.

- [ ] **Step 4: Adversarial review and repairs**

Review exact diff for arbitrary-root escape, symlink/TOCTOU, peer spoofing, receipt replay, effect-unknown retry, mutable-release execution, secret leakage, and install rollback. Repair any finding with a failing regression test first.

### Task 7: Protected merge and real-host proof

**Files:** no new source unless proof finds a defect.

- [ ] **Step 1: Push branch and open one focused PR**

PR title: `feat(executive): add receipt-gated privileged action broker`

- [ ] **Step 2: Require protected CI and review to pass, then merge**

Do not call merge production proof. Re-pin the resulting protected master SHA.

- [ ] **Step 3: One-time local administrator ceremony from exact protected master**

Run the reviewed Executive installer with `--arm-privileged-broker` from a clean exact protected-master checkout and the already pinned Executive Python runtime. This is the final password-required bootstrap; do not store the password.

- [ ] **Step 4: Prove non-root unattended actions**

As `chriswong`, run `mmx-admin executive.worker_auth.verify_only` and a safe service status/readiness request with no sudo and no prompt. Verify a terminal receipt under the root receipt store and replay the same request id. Verify an unknown action and modified duplicate request are refused.

- [ ] **Step 5: Close capability state**

Only after the real-host receipt and provider profile verification pass, record `PROVEN_LIVE`; otherwise record the precise `BUILT_NOT_PROVEN` or `PARTIAL` boundary and the exact next action.
