# Fleet Health OS Implementation Plan

> For agentic workers: use the existing execution-plan/TDD workflow; the current Chairman commission already authorizes routine implementation. Do not request a second design approval.

**Goal:** Replace the existing Fleet & Capacity placeholder with an authenticated, source-backed hardware and historical-health view.

**Architecture:** Bounded diagnostics projection of the existing Fabric registry, snapshots and collector log, served by the existing workspace read owner. Fixed web/native read; no new monitoring or control plane.

**Tech stack:** Python standard library/pytest, existing Starlette workspace edge, React/TypeScript/Vitest, existing Tauri Rust transport.

**Spec:** `docs/superpowers/specs/2026-10-13-fleet-health-os.md`.

## Global constraints

Reuse protected pin `d837e04bf60a9fb60b7c530d287115a298fc1af0` and managed operation `fleet-health-os-20261013-sol-001`. Source modifications only in its returned workspace. Maximum 32 hosts, 360 history points/host, 1,500,000-byte public document. Fleet data is observation-only. Missing data is null, not zero. Preserve #1363 held effects and #1404 incumbent collector source. No collector activation, host settings, worker cancellation, new daemon or alternate authority.

## Review focus

- Missing or stale readings must never imply idle agents, healthy hardware or fresh temperature.
- Future/nonfinite/bool timestamps and metric values, duplicate host identity, symlink/oversized source reads must fail closed.
- Thermal duration must not bridge gaps or derive from downsampled charts.
- Host auth/sign-out/revocation and stale response cancellation must remain effective on the new read.
- Lane occupancy is not total subagents; selected history range is not proof of retained history.

## Task 1 — Bounded source projection

Files: create `control_plane/fleet_health.py`, `tests/test_fleet_health.py`.
Interface: `read_fleet_health(fabric_root: Path, *, window: str = "24h", now: float | None = None) -> dict`; pure `compose_fleet_health(registry: dict, snapshots: dict, log_text: str, *, window: str, now: float, history_truncated: bool = False) -> dict`; typed `unavailable_fleet(window, now, reason)`.

- [ ] Write failing fixtures for current/stale/offline/unknown, missing fields versus measured zero, safe host identity, numeric validation, sparse history, duration gaps, thermal operator-limit labeling, and CPU pressure not hardware damage.
- [ ] Run `python3 -m pytest -q tests/test_fleet_health.py` and observe the absent-feature failure.
- [ ] Implement standard-library-only registry/snapshot/log adapters and deterministic findings. Bound source descriptors and output; consume no external process/network.
- [ ] Run new tests and relevant workspace/capacity regressions. Read real source snapshots without modifying the collector; record actual coverage separately.

## Task 2 — Typed Fleet consumer

Files: create `app/mastermind_os/src/fleet.ts`, `fleet.test.ts`, `fleet/FleetHealth.tsx`, `fleet/FleetHealth.test.tsx`, `fleet/fleet.css`; modify existing `App.tsx` Fleet branch and `host.ts`.
Interface: `decodeFleetHealth(value: unknown): FleetHealthDocument | null`; `FleetHealth({read, generation}: {read?: FleetRead; generation?: number})`. `FleetRead` takes `{window, signal}`; no path or URL.

- [ ] Write failing decoder/component tests for malformed shapes, missing sensors, zero values, stale data, window selection, active-lane scope, cancellation and findings.
- [ ] Implement validated DTO, accessible metric/history cards, refresh/window controls, abort-safe periodic reads only while mounted/visible, and explicit unavailable state. Use existing typography/colors and no additional chart dependency.
- [ ] Wire to existing Fleet navigation without changing Mission lifecycle or other routes. Run focused tests/typecheck, then the frontend suite and build.

## Task 3 — Existing authenticated transport integration

Files: existing `common/executive_workspace_contract.py`, `control_plane/workspace_read_service.py`, `integrations/mastermind_workspace_app/contract.py`, `app.py`, fixed mount/edge route lists, `src/web-auth.ts`, `src/host.ts`, native Rust fixed-command files; focused route/host tests.
Interface: one `fleet` read operation with exact `{window}` selection through the same enrolled viewer, fixed `/workspace/fleet/current?window=<enum>`, optional trusted-host `fleet_read` constructor callback. Missing trusted source binding returns UNAVAILABLE, never a guessed root.

- [ ] Add failing tests for exact route/query/body/permission and optional producer behavior; inspect the existing owner seams before editing.
- [ ] Implement frame validation, service injection, same permission-before/after fencing, app envelope mapping, fixed web and native bridges, cancellation and bounded response.
- [ ] Add installation composition only through the existing service configuration/source owner. No new credentials, auth grant, background service or direct client filesystem access.
- [ ] Verify new route and regressions; prove actual host-source read and local authenticated test journey. Distinguish source proof from installed production proof.

## Task 4 — Reviewable delivery and remaining rollout

- [ ] Inspect exact changed paths/whitespace, run relevant tests and build, publish same managed branch using CAS commit/push, obtain independent review and CI.
- [ ] Save cumulative checkpoint with exact head, verified results, explicit sensor/subagent/history gaps and actual release/install gates.
- [ ] Continue next safe source or proof phase while available. Do not deploy a draft/unaccepted head or bypass held collector effects. Only accepted protected-source installation plus real app proof can mark production integration complete.

## Execution frontier

2026-10-13: managed workspace acquired and verified clean at the pin; source census and design complete. Plan and spec written only; implementation/tests/PR/install not yet performed. Three compound shell inspection calls were refused before dispatch by the platform safety-status check; no modifying effect began. Explicit filesystem reads and this assigned-workspace write are working. Do not replay the refused shell inspections. No child has been submitted. Principal retains source/architecture work while exact worker input and original-root binding are established.

## Milestone — producer, HTTP edge and Fleet consumer implemented

Operation/source pin unchanged. The managed workspace now contains the bounded Fabric snapshot/log projection, shared closed Fleet DTO, optional WorkspaceReadService producer binding, authenticated fixed `/workspace/fleet/current?window=<enum>` HTTP route, frontend decoder and Noir Fleet screen, fixed browser/native-JS reads, and replacement of the existing Fleet placeholder. No collector/host configuration, Runtime work, external service, permission or production installation changed.

Verified: 24 producer tests initially failed before implementation and then passed; the full workspace HTTP file plus Fleet producer/service tests passed (process 97162, exit 0). The combined Fleet frontend/host/browser/App route tests passed 77 cases, followed by TypeScript checking (process 66764, exit 0). Sign-out and permission revocation withdraw machine data; gaps and unknown readings remain explicit. A real read-only Fabric canary successfully projected current Ubuntu observations and stale Mac records; this is source proof, not installed app proof.

The one M2 Fabric leaf request `fleet-health-ui-20261013-sol-001` was refused before worker start: no eligible remote mode, telemetry-source/disk admission reasons. Same-ID readback remains NOT_FOUND. No child, result, uncertain effect or repeat authorization exists. Do not retry via another identity or alter those limits. Direct principal source work continues.

Next safe phase: finish the native Rust fixed route/selector and public mount/edge allowlists; bind a trusted existing observer source through the actual installation owner, without a browser path or guessed HOME root. Then run focused regressions and build/browser proof, obtain independent review/CI and publish the same source carrier. Remaining outcome gates: actual service-account source access, accepted installation, live Mac sensor/complete-subagent/RAM-history coverage. 30-day selection is not proof of 30-day retention. Source-only work is not production completion.
