# Producer gap table — upstream producers for the L2 UI owner asks

Lane L6 slice 5 (sub-lead). Base `8d4e24d12` (= trunk `origin/feat/mmos-v1-integration-t3`
at pickup; trunk has since advanced to `8b888c19b` with no changes to any surface named
below — verified by `git diff --name-only`). Source of the asks:
`integrations/mmos/LANE_L2_UI_V2.md` §OWNER ASKS.

Method: every "exists" row cites the file on this base commit; every "missing"
row names the exact absent artifact and classifies it **BUILDABLE** (source lives
in this repository; contract tests prove it without the live runtime) or
**NEEDS-LIVE-RUNTIME** (the data's owner is the installed Executive/Hermes/fleet
runtime or collector; listed here only — never built in this lane, per the
honest-state law: no sample data, no fake producer).

| # | Owner ask (L2 wording) | Producer on trunk? | Where (if yes) | Exactly what is missing | In-repo / live runtime |
|---|---|---|---|---|---|
| 1a | `delegatedTask` producer — `ChildExecutionRequest` v1.2 requester block (Director C2) | **YES** | `control_plane/child_execution_contracts.py` — `OriginalRequesterBinding` (lines ~767–1011), `CHILD_EXECUTION_REQUEST_SCHEMA_V1_2`, sparse all-or-nothing digest law; proven by `tests/test_child_execution_contracts*` (Director C2: 103 passed incl. digest pins). Receipt persistence via `control_plane/execution_return_wiring.py` (events row `EXECUTION_RETURN_DELIVERY`, idempotent command id) and the runtime hook (`executive_runtime.py` `_execution_return_seam`, line ~21509). | Nothing source-side. Remaining UI-side: `app/mastermind_os/src/team/delegated-task.ts` still parks the fields in `PENDING_REQUESTER_FIELDS`; adopting them into the TS binding mirror is **L2 UI-lane consumption**, not this lane. | Exists |
| 1b | `executionReturn` producer — the execution-return read route (Director F gap list) | **PARTIAL** — projector + deliverer + post-terminal seam exist; **no UI read route** | Projector: `control_plane/execution_return_projection.py` (29 tests). Delivery: `integrations/session_bridge/hermes_native_return.py` (14 tests). Seam: `control_plane/execution_return_wiring.py` + runtime hook. TS mirror + fixtures: `src/hermes-native/execution-return-contract.ts`, `integrations/mmos/fixtures/execution_return_v1/`. | An authenticated Workspace **read** route projecting delegated-task / execution-return state (latest `mastermind.execution_return/v1` + `mastermind.execution_return_delivery/v1` receipt per attempt, joined to the v1.2 original-requester block) so the L2 host can feed `delegatedTask`/`executionReturn` props. Follows the fleet-read pattern: `common/workspace_*_contract.py` wire contract + read-only `control_plane/workspace_*_read.py` owner over the persisted events rows + one route in `integrations/mastermind_workspace_app/app.py`. No new listener/queue/store. | **BUILDABLE** |
| 2 | `t3ThreadProjection` host source — implemented by no host | **NO** | — | A server-side thread-list read: one read-only open of the installed T3 adapter durable state (the same state file the fleet read opens `mode=ro` — `control_plane/t3_attempt_fleet_projection.py::read_adapter_attempt_rows` / `workspace_t3_attempt_fleet_read.py`), projecting `mastermind.t3_thread_projection_list.v1` (schema already frozen in `src/code/t3-thread-projection.ts`: threadId/environment/runState/lastActivity/prLink/repository/companyManaged), honestly empty when the store is missing. One Workspace route. UI host facade wiring (`MastermindMissionHost.t3ThreadProjection`, Tauri command, web client) is **L2 UI-lane consumption** — App composition stays with the sole App author. | **BUILDABLE** (server producer) |
| 3 | Qualified host-capacity producer for `HostTelemetryPanel` (`capacity` prop) | **NO** (pure projector + decoder exist) | Projector: `control_plane/executive_host_capacity.py::project_native_host_capacity` (+ `tests/test_executive_native_host_capacity.py`, inert fixture `research/evidence/native-capacity-owner-projection.json`). Decoder/qualifier: `src/resources/host-capacity.ts`. `src/resources/README.md` records the finding: **no telemetry in the existing Control Room, Mission, plan ceilings or host status document**. | The retained qualified telemetry source itself and the fixed authenticated reader composing it (expected binding from existing Runtime/collector ownership, per README: "Do not derive expectations from the received body, browser selection…"). The telemetry is owned by the live fleet collector/VPS hosts. | **NEEDS-LIVE-RUNTIME** — list only |
| 4 | TS02 Teamlink surface: contract exists, no view consumes it | contract **YES** | `control_plane/teamlink_contracts.py` + `teamlink-contract.ts`. | Not a producer gap: the missing artifact is a consuming **view** plus a surface-owner decision ("a surface owner should be named if the board is promoted"). Both are L2 UI-lane decisions; no upstream producer is absent. | Not a producer build — listed |
| 5a | Conversation-search read | **NO** | — | A searchable conversation corpus + read route. The UI's conversation list composes from the App's own live-conversation state (`src/conversations/conversation-list-source.ts`); the real corpus lives in the live Hermes/Executive conversation runtime. No in-repo store can honestly answer a search read. | **NEEDS-LIVE-RUNTIME** — list only |
| 5b | Routines-schedule read (HC10) | **NO** | — | A routines/schedule store + projection. No routines store or projection source exists anywhere in this repository (`RoutinesPanel` renders the honest "not projected" state by design); the schedule owner is the live Hermes runtime. | **NEEDS-LIVE-RUNTIME** — list only |
| 5c | Provider-configuration read (HC11 `CodeSettingsPanel`) | **NO** | — | A coding-agent provider configuration source (executable/args/defaultModel/connectionAuth per provider — `ProviderConnection` in `src/code/CodeSettingsPanel.tsx`). That truth lives with the installed agent runtimes (Hermes seats / T3 environments); no in-repo store owns it, and a repo-authored YAML would be an invented source under the honest-state law. | **NEEDS-LIVE-RUNTIME** — list only |

## Build plan from this table

Two BUILDABLE producers, one bounded worker each (own branch, contract tests,
honest unknowns, no new listener/queue/registry, read-only over existing
durable state):

- **P1 (ask 1b)** — execution-return/delegated-task Workspace read route.
- **P2 (ask 2)** — T3 thread-list Workspace read route over the installed
  adapter state.

All NEEDS-LIVE-RUNTIME rows (3, 5a, 5b, 5c) are **listed only** — this lane
never builds them; the L2 surfaces keep their honest unavailable states until
their runtime owners exist. Row 1a needs no build (source landed); row 4 is an
L2 decision, not a producer.
