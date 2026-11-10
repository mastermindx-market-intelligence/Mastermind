# Producer gap table — upstream producers for the L2 UI owner asks

Lane L6 slice 5 (sub-lead). Base `8d4e24d12` (= trunk `origin/feat/mmos-v1-integration-t3`
at pickup; trunk has since advanced with no changes to any surface named below).
Source of the asks: `integrations/mmos/LANE_L2_UI_V2.md` §OWNER ASKS.

**Program plan V3 scope trim (2026-11-10, trunk @ `c0263d2d1`)**: the old app
screens are frozen and Paperclip is the product shell. Per the principal's
ruling: finish the producers already in flight, start nothing whose only
consumer is an old app screen, mark shell-owned capabilities as such, and add
the module-consumer column below. "Module consumer" = can a Paperclip module
worker read the producer as-is (Python read path callable from a plugin
worker, or local HTTP route)? The named call is the honest, tested read path.

Method: every "exists" row cites the file on the base commit; every "missing"
row names the exact absent artifact and classifies it **BUILDABLE** (source
lives in this repository; contract tests prove it without the live runtime),
**NEEDS-LIVE-RUNTIME** (the data's owner is the installed Executive/Hermes/fleet
runtime or collector; listed only — never built in this lane, per the
honest-state law: no sample data, no fake producer), or **PROVIDED BY SHELL**
(Paperclip already owns the capability; building it here would duplicate the
shell).

| # | Owner ask (L2 wording) | Producer on trunk? | Where (if yes) | Exactly what is missing | Classification | Module consumer |
|---|---|---|---|---|---|---|
| 1a | `delegatedTask` producer — `ChildExecutionRequest` v1.2 requester block (Director C2) | **YES** | `control_plane/child_execution_contracts.py` — `OriginalRequesterBinding` (lines ~767–1011), sparse all-or-nothing digest law; proven by Director C2 tests (103 passed incl. digest pins). Receipt persistence via `control_plane/execution_return_wiring.py` (events row `EXECUTION_RETURN_DELIVERY`, idempotent command id) and the runtime hook (`executive_runtime.py` `_execution_return_seam`, line ~21509). | Nothing source-side. The TS binding mirror adoption in `src/team/delegated-task.ts` was an old-screen concern — frozen under V3. | Exists — Executive job/attempt state, worth keeping | **YES** — `python3` import: `control_plane.child_execution_contracts` (parse/validate v1.2 records read-only); the persisted facts are read via the Executive store events APIs (see 1b). |
| 1b | `executionReturn` producer — the execution-return read route (Director F gap list) | **PARTIAL → BEING FINISHED** | Projector: `control_plane/execution_return_projection.py` (29 tests). Delivery: `integrations/session_bridge/hermes_native_return.py` (14 tests). Seam: `control_plane/execution_return_wiring.py` + runtime hook. TS mirror + fixtures: `src/hermes-native/execution-return-contract.ts`, `integrations/mmos/fixtures/execution_return_v1/`. | An authenticated Workspace read route + directly importable Python read owner projecting the persisted delivery receipt per attempt. **IN FLIGHT** (producer P1, branch `t3/mmos-l6-p1-exec-return`). | BUILDABLE — Executive attempt state, worth keeping, already in flight | **YES (planned)** — Python: `control_plane.workspace_execution_return_read` source object `.read(attempt_id)`; HTTP: `GET /workspace/resources/execution-returns/current?attempt_id=<run id>`. Verified call paths to be recorded here at merge. |
| 2 | `t3ThreadProjection` host source — implemented by no host | **BUILT THIS LANE** (merged `6440703e6`) | `common/workspace_t3_thread_projection_contract.py` + `control_plane/workspace_t3_thread_projection_read.py` (read-only `mode=ro` projection over the durable `t3_adapter_runs` store; honest empty/unavailable/refusal documents) + route `GET /workspace/resources/t3/threads/current` (`integrations/mastermind_workspace_app/t3_thread_projection.py`) + ceo-ingress/executive-mcp/installed wiring. 89 contract tests + 88 fleet regression tests green on the merged result. | The UI host facade wiring was an old-screen concern — frozen under V3; a module consumes the route/owner directly. | BUILT — Executive attempt state, worth keeping | **YES** — Python: `from control_plane.workspace_t3_thread_projection_read import default_source; default_source().read_frame(...)` (installed composition over `default_t3_adapter_state_path()`); HTTP: `GET /workspace/resources/t3/threads/current` (no query keys). Both re-validated by `common.workspace_t3_thread_projection_contract` validators. |
| 3 | Qualified host-capacity producer for `HostTelemetryPanel` (`capacity` prop) | **NO** (pure projector + decoder exist) | Projector: `control_plane/executive_host_capacity.py::project_native_host_capacity` (+ tests, inert fixture). Decoder: `src/resources/host-capacity.ts`. `src/resources/README.md` records: no telemetry in the existing Control Room, Mission, plan ceilings or host status document. | The retained qualified telemetry source itself (live fleet collector/VPS owner) and the fixed authenticated reader composing it. The old-screen consumer is frozen; the telemetry source gap is unchanged. | **NEEDS-LIVE-RUNTIME** — list only | Not callable: no retained source exists to read. |
| 4 | TS02 Teamlink surface: contract exists, no view consumes it | contract **YES** | `control_plane/teamlink_contracts.py` + `teamlink-contract.ts`. | Not a producer gap: the missing artifact was a consuming view — an old-app-screen decision, frozen under V3. No upstream producer is absent. | Not a producer build — listed (view decision frozen) | n/a (contract library only; no live producer) |
| 5a | Conversation-search read | **NO** | — | A searchable conversation corpus + read route; the corpus lives in the live Hermes/Executive conversation runtime, and the sole consumer surface (HC20) is a frozen old screen. | **NEEDS-LIVE-RUNTIME** — list only (consumer frozen) | Not callable: no in-repo honest source. |
| 5b | Routines-schedule read (HC10) | **NO — PROVIDED BY SHELL** | Paperclip (per program plan V3 §2.1) supplies routines and routine history. | Nothing to build here: building a routines store/read would duplicate the shell. HC10 was an old-screen surface — frozen. | **PROVIDED BY SHELL** — do not build | Read via Paperclip's own routines surfaces; not a Mastermind producer. |
| 5c | Provider-configuration read (HC11 `CodeSettingsPanel`) | **NO** | — | A coding-agent provider configuration source (executable/args/defaultModel/connectionAuth). Truth lives with the installed agent runtimes (Hermes profiles); the agent *roster* view is shell-owned, but provider configuration is runtime-owned. No in-repo store can honestly answer it; a repo YAML would be an invented source. | **NEEDS-LIVE-RUNTIME** — list only (roster aspect shell-owned) | Not callable: no honest in-repo source. |

## Shell-owned capabilities (V3 §2 rule — never duplicated here)

Task lists, inbox, artifacts, routine history, agent roster and cost totals are
provided by the installed Paperclip shell. None of the producers this lane
builds or lists duplicates them: P1/P2 project **Executive job/attempt state**
(sealed execution-return receipts, durable T3 adapter thread facts), which the
principal named as worth keeping. The only owner-ask row that crossed into
shell territory was 5b (routines-schedule) — marked **PROVIDED BY SHELL** above.

## Build plan (post-trim)

- **P1 (ask 1b)** — execution-return Workspace read producer: **in flight**
  (restarted after a transport-level child failure; branch
  `t3/mmos-l6-p1-exec-return`, base = merged `6440703e6`).
- **P2 (ask 2)** — T3 thread-list Workspace read producer: **merged**
  (`6440703e6`, fast-forward; 89 + 88 tests re-run green by the sub-lead on the
  merged result).
- Rows 3, 5a, 5c: NEEDS-LIVE-RUNTIME — listed only. Row 5b: PROVIDED BY SHELL.
  Row 4: view decision frozen under V3. Row 1a: exists; nothing to build.

## Adversarial pass (Deliverable 3)

Runs on the merged producer result only (what actually merged), via one
READ_ONLY grok-4.7 child; findings verified against the diff before acceptance.
