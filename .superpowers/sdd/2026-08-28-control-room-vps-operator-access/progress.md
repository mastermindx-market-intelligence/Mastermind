# Control Room Mastermind Wave Progress

- Plan: `/Users/chriswong/Documents/Cluade/Mastermind/.worktrees/control-room-vps-operator-auth-20260828/docs/superpowers/plans/2026-08-28-control-room-vps-operator-access.md`
- Carrier: `/Users/chriswong/Documents/Cluade/Mastermind/.worktrees/control-room-vps-projection-20260828`
- Branch: `codex/control-room-vps-operator-access-20260828`
- Base: `e80e9aea894c758ae7a95720ab56c9cbc868b1ba`
- Scope: Tasks 1-5 only. No host, service, provider, credential, DNS, Slack, Linear, PR, merge, or deployment effects.
- Status: TASKS_1_TO_5_GREEN_NOT_INSTALLED

## Task 1 — remote schema boundary

- RED: `python3 -m pytest tests/test_chairman_control_room_remote.py -q` -> collection error, missing `control_plane.chairman_control_room_remote` (exit 2).
- GREEN focused: same command -> `14 passed` (exit 0).
- GREEN regression: `python3 -m pytest tests/test_chairman_control_room.py -q` -> `26 passed` (exit 0).
- Mutation guard: temporary in-process removal of the allowlisted `bindings` canonical work-card key -> `MUTATION_GUARD_PASS unexpected_keys`; process exit restored the module constant.
- Note: plan examples say `python`; this host resolves `python` to Python 2.7.18, so all Python 3.11+ plan commands are executed with `python3` and recorded literally.

## Task 2 — background collector and process-memory cache

- RED: `python3 -m pytest tests/test_chairman_control_room_remote.py -q -k 'collector or cache or refresh or startup or snapshot or runtime_database'` -> 10 setup errors, missing `CollectorConfig` (exit 1).
- GREEN focused: same command -> `10 passed` (exit 0).
- GREEN owned/local-compositor regression: `python3 -m pytest tests/test_chairman_control_room_remote.py tests/test_chairman_control_room.py -q` -> `50 passed` (exit 0).
- Broader inherited local-server command: `python3 -m pytest tests/test_chairman_control_room_remote.py tests/test_chairman_control_room.py tests/test_chairman_control_room_server.py -q` advanced through 69% without a failure line, then made no progress at 0% CPU in two accidentally duplicated invocations. Exact owned PIDs 19062 and 21735 were verified by cwd and terminated with SIGTERM. Receipt is `INCOMPLETE_INHERITED_SERVER_TEARDOWN_HANG`, not PASS. No Task 2 production path imports or modifies the inherited local server.

## Task 3 — Unix-only fixed-route server

- RED: `python3 -m pytest tests/test_chairman_control_room_remote.py -q -k 'socket or route or method or path or health or server or cli or state_is_typed or browser_credentials'` -> collection error, missing `scripts.chairman_control_room_remote` (exit 2).
- First GREEN attempt exposed Darwin's AF_UNIX pathname limit in pytest's deep temporary root; the test-only socket seam was moved to an owned short `/tmp/ccr-remote-*` directory. The next run exposed two real canonicalization defects: root `/` was rejected and stdlib normalized a raw `//api/state` before the handler saw it. The server now preserves the raw request target and handles root explicitly.
- GREEN focused: same Task 3 command -> `23 passed` (exit 0).
- GREEN owned/local-compositor regression: `python3 -m pytest tests/test_chairman_control_room_remote.py tests/test_chairman_control_room.py -q` -> all tests passed (73 collected; exit 0).
- The inherited local-server full-suite receipt remains the already-recorded `INCOMPLETE_INHERITED_SERVER_TEARDOWN_HANG`; no existing local-server file was modified.

## Task 4 — immutable shared-renderer remote mode

- RED: `python3 -m pytest tests/test_chairman_control_room_ui_x1.py -q` -> 5 failures: missing `remote.html`, missing remote transport/mode branch, and missing remote layout rules (exit 1).
- GREEN focused: same command -> `23 passed` (exit 0).
- GREEN combined owned regression: `python3 -m pytest tests/test_chairman_control_room_ui_x1.py tests/test_chairman_control_room_remote.py -q && node --check app/static/chairman_control/control_room.js` -> `70 passed`, JavaScript parse exit 0.
- Runtime transport harness: remote mode emitted exactly `GET /api/state` with `{method: GET, credentials: same-origin, headers: {}}`; `postJSON` rejected `remote_read_only` before fetch. Local mode retained its `X-CCR-Token` GET and JSON POST contracts.
- Local browser fixture at `1440x900`, `1024x768`, and `390x844`: degraded banner visible, two work-card projections rendered, zero local control IDs, `scrollWidth == clientWidth` at all three widths, and no console warning/error entries. The first 1440 check found topbar/drawer overflow; remote-only CSS was repaired and the matrix rerun green. Temporary viewport was reset, browser tab closed, and the test-only loopback server stopped.

## Task 5 — exact-identity release and reviewed install-only unit

- RED: `python3 -m pytest tests/test_control_room_remote_install.py -q --tb=short` -> `18 failed`; release helper interface and install/unit artifacts did not exist (exit 1).
- Permission regression RED: `python3 -m pytest tests/test_control_room_remote_install.py -q -k installer_is_archive_based_atomic_and_install_only --tb=short` -> `1 failed`; the initial venv/manifest materialization did not explicitly restore group-read/traverse permission after `umask 077` (exit 1).
- Permission regression GREEN: `python3 -m pytest tests/test_control_room_remote_install.py -q -k installer_is_archive_based_atomic_and_install_only && bash -n ops/control_room_remote/install.sh` -> `1 passed`, shell parse exit 0.
- GREEN focused: `python3 -m pytest tests/test_control_room_remote_install.py -q --tb=short` -> `19 passed` (exit 0).
- GREEN Task 5 plus remote boundary: `python3 -m pytest tests/test_control_room_remote_install.py tests/test_chairman_control_room_remote.py -q && bash -n ops/control_room_remote/install.sh` -> `66 passed`, shell parse exit 0.
- Service syntax: `systemd-analyze` is unavailable on this macOS development host, recorded `SYSTEMD_ANALYZE_UNAVAILABLE`; it is explicitly not a local PASS and remains a hosted Linux exact-head gate.
- GREEN Tasks 1-5 owned regression: `python3 -m pytest tests/test_control_room_remote_install.py tests/test_chairman_control_room_remote.py tests/test_chairman_control_room.py tests/test_chairman_control_room_ui_x1.py -q && python3 -m py_compile control_plane/chairman_control_room_remote.py scripts/chairman_control_room_remote.py && node --check app/static/chairman_control/control_room.js && bash -n ops/control_room_remote/install.sh && git diff --check` -> `115 passed`; Python, JavaScript, shell, and diff checks exit 0.
- Artifact boundary: installer was not run; no user, directory, unit, daemon, socket, host, service, provider, credential, DNS, Slack, Linear, PR, merge, or deployment effect occurred. The installer renders one exact validated commit into the unit, re-attests every archived runtime file before socket bind, switches `current` atomically, runs daemon reload only, and contains no service activation/restart operation.
