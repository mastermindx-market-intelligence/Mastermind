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

## Rejected-head review repair — `5cfbc9764c5679727a16637f959ec92a24079662`

- Reviewer rejection covered the transitive extracted-release closure, mutable unit-template race, networked active-build subprocess under `AF_UNIX`, real source-clock freshness, source-local failure isolation, bounded subprocess capture/reap, and the production event sink.
- Architecture reconciliation: the externally reachable process remains uncredentialed and `RestrictAddressFamilies=AF_UNIX`; it consumes only `/var/lib/mastermind-control-room-sources/project-active-builds.json`, separately produced by the existing trusted Macro update lane. Mastermind creates only the fixed source directory at install time. There is no `gh`/network call, second store, queue, lifecycle, or persistent projector cache in this carrier.
- Release closure RED: focused archive/boot and unsafe-unit tests initially produced `8 failed`; the archive lacked `scripts.ohf`/`common`, and the service template was not an immutable staged input. GREEN focused after the minimal closure/staging repair: `13 passed`.
- Source artifact directory RED: `python3 -m pytest tests/test_control_room_remote_install.py -q -k installer_is_archive_based_atomic_and_install_only` -> `1 failed`; the installer did not materialize the fixed root:caddy source directory. GREEN: same focused test -> `1 passed`; `bash -n ops/control_room_remote/install.sh` exited 0.
- Source-local admission RED: `python3 -m pytest tests/test_chairman_control_room_remote.py::test_unavailable_source_clocks_omit_only_their_documents_from_composition -q` -> `1 failed`; unavailable future-clock sources were still admitted. GREEN with malformed-active and absent-runtime peers: `6 passed`.
- Cross-repository clock-contract RED: canonical Macro `datetime.isoformat()` (`+00:00`) fixture plus UTC-boundary matrix -> `2 failed`; the reader accepted only `Z`. GREEN: aware UTC offset zero now normalizes to `Z`, while naive/nonzero/malformed/future stay unavailable with stable reasons -> `10 passed` including source-local admission.
- Portable staging-owner RED: `python3 -m pytest tests/test_control_room_remote_install.py::test_installer_is_archive_based_atomic_and_install_only -q` -> `1 failed`; the shell retained a Darwin/Linux `stat` ambiguity. GREEN after descriptor-independent Python `lstat()` owner check: `1 passed`; shell parse exited 0.
- Current focused GREEN: `python3 -m pytest tests/test_chairman_control_room_remote.py -q` -> `72 passed` before the final root:caddy wiring regression was added; `python3 -m pytest tests/test_control_room_remote_install.py -q` -> `30 passed`.
- Final owned regression: `python3 -m pytest tests/test_control_room_remote_install.py tests/test_chairman_control_room_remote.py tests/test_chairman_control_room.py tests/test_chairman_control_room_ui_x1.py -q && python3 -m py_compile control_plane/chairman_control_room_remote.py scripts/chairman_control_room_remote.py && node --check app/static/chairman_control/control_room.js && bash -n ops/control_room_remote/install.sh && git diff --check` -> `152 passed`; Python, JavaScript, shell, and diff checks exited 0.
- Exact extracted-release proof: `python3 -m pytest tests/test_control_room_remote_install.py::test_installer_exact_extracted_allowlist_boots_under_isolated_python -q` -> `1 passed`; the test stages the exact archive allowlist, verifies its manifest, and boots that extracted entrypoint from outside the source/extraction directory under `python -I -B`.
- Root:caddy boundary: service wiring now has an explicit regression proving fixed artifact path, root directory/file ownership, caddy directory/file group, and service caddy group. File admission remains exact `0640`; parent directory admission and installer materialization remain exact `0750`.
- Bounded-runner regressions use continuous stdout and stderr writers plus a 30-second sleeper; each cap/timeout case kills and reaps in under 2 seconds and emits stable typed flags. Production request events default to no sink; an injected test sink must be a bounded `deque` and stays capped.
- One compositor invariant: `rg -n 'ccr\\.compose_control_room\\(|ccr\\.build_control_room\\(' control_plane/chairman_control_room_remote.py scripts/chairman_control_room_remote.py` returns exactly one production `ccr.compose_control_room(...)` call and zero `ccr.build_control_room(...)` calls.
- Effect boundary remains unchanged: no installer, host, service, provider, credential, DNS, Slack, Linear, GitHub PR, merge, or deployment action was performed.
