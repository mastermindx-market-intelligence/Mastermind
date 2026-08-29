# Project Workroom Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first safe, deterministic Slack + Linear Project Workroom fabric in which exact Agent OS workstreams map to normalized Linear Projects, selected private Slack workrooms and exact operation threads without making Slack or Linear another lifecycle authority.

**Architecture:** Land the Workroom source law, then build a zero-network desired-state/drift compiler as the first independently useful vertical. Subsequent waves add one least-privilege Workroom Projector app, one inert channel/Canvas/List/bookmark canary, a reviewed multi-workroom evolution of the protected Agent Relay, and finally selected Linear Issue/update plus Steward/Control Room integration. Every wave extends an existing owner and has an explicit current-source, collision, proof and stop gate.

**Tech Stack:** Python 3.12, JSON, pytest, existing Mastermind control-plane patterns, Slack Web API (conversations, canvases, Lists, bookmarks, chat), existing Agent Relay V1/V2, Linear GraphQL/app actor through MAS-64/MAS-66/OSC-C1, Executive Steward/Chairman Control Room, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-29-project-workroom-convergence-design.md`

## Global Constraints

- Protected procedure basis at plan authoring: `mastermindx-market-intelligence/Mastermind@2962759e8abf6bf722a8582f92af8f84013f5f40`, Skillpack `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap major 1.
- Re-pin protected Mastermind and load the current same-SHA Skillpack before every modifying wave.
- Existing Agent OS, Executive OS, GitHub, Linear, Slack, Wake, Capacity, RuntimeBinding and Steward ownership remains unchanged.
- The concurrent Linear Initiative session exclusively owns Initiative creation, membership and live rollout. Consume its final protected SHA/read-back; never duplicate or race it.
- Protected Agent Relay #231 is the sole long-running dialogue runtime foundation. Open #223 remains the sole enrollment/install and single-channel A2 canary carrier until accepted.
- Open #228 remains the sole Executive Steward read-core release carrier; do not touch `control_plane/executive_steward.py` before its exact carrier is protected/reconciled.
- MAS-65 -> MAS-64 -> MAS-66 remains the Linear Project projection chain. MAS-189/OSC-C1 remains the selected Issue/comment/update owner.
- No new database, lifecycle, queue, task registry, watcher registry, retry store, session registry, provider pool or second synchronizer.
- No fuzzy title/channel/project matching. Exact `WS:<KEY>`, immutable Linear Project ID, Slack workspace/channel ID and stable operation identity only.
- No live Slack/Linear mutation before a reviewed dry-run and exact app-actor/credential/canary gate.
- Any write with an ambiguous response becomes `EFFECT_UNKNOWN`; re-read the same target and never blind retry/failover.
- Existing started/effect-unknown `#agent-dispatch` carriers remain where they began. Workrooms initially accept new operations only.
- Slack/Linear/Canvas/List state never proves Executive runtime, GitHub proof or Agent OS completion.
- V1 Workrooms are private by default.
- Custom Slack channel templates are not a dependency while Slack reports custom-template creation/editing unavailable.

---

## File / Owner Map

### Records carrier — Mastermind

- Create: `docs/superpowers/specs/2026-08-29-project-workroom-convergence-design.md`
- Create: `docs/superpowers/plans/2026-08-29-project-workroom-convergence.md`

### WR-P0 pure planner — Mastermind

- Create: `config/project_workroom_strategy.v1.json`
- Create: `control_plane/project_workroom_plan.py`
- Create: `scripts/project_workroom_plan.py`
- Create: `tests/test_project_workroom_plan.py`
- Create: `tests/test_project_workroom_plan_cli.py`
- Create: `research/project_workroom/project_workroom_linear_snapshot_2026-08-29.json`
- Create: `research/project_workroom/project_workroom_slack_snapshot_2026-08-29.json`
- Create: `research/project_workroom/project_workroom_shadow_plan_2026-08-29.json`

### WR-A0 / WR-C0 Workroom Projector — later bounded carrier after WR-P0 acceptance

- Create: `integrations/slack_project_workrooms/__init__.py`
- Create: `integrations/slack_project_workrooms/client.py`
- Create: `integrations/slack_project_workrooms/projector.py`
- Create: `ops/project_workrooms/projector_enrollment.py`
- Create: `ops/project_workrooms/slack_app_manifest.yaml`
- Create: `tests/test_slack_project_workroom_client.py`
- Create: `tests/test_slack_project_workroom_projector.py`
- Create: `tests/test_project_workroom_projector_enrollment.py`

### WR-D0 multi-workroom Agent Relay — later bounded carrier after accepted A2 canary

- Create: `integrations/slack_agent_dialogue/workroom_routes.py`
- Modify: `integrations/slack_agent_dialogue/slack_web_api.py`
- Modify: `integrations/slack_agent_dialogue/runtime.py`
- Modify: `integrations/slack_agent_dialogue/service.py`
- Modify: `ops/executive_os/a2_agent_relay_enrollment.py` only through the accepted successor/reconciliation carrier after #223 closes; never on #223 itself
- Create: `tests/test_slack_agent_dialogue_workroom_routes.py`
- Modify: existing focused Relay client/runtime/service tests

### WR-L0 / WR-CR0 integrations — dependency-gated, existing owners only

- Linear Project resource/link mutation: extend the exact accepted MAS-66 app-actor adapter path after MAS-66 merge; do not create a second Linear adapter.
- Selected Issue/comment/update behavior: extend the exact MAS-189/OSC-C1 carrier after its prerequisites and architecture promotion.
- Steward/Control Room: extend the exact protected OCR-6 / AD-CR1 owner after #228 merges and its gather/projection boundary is accepted.

The dependency-gated paths above are intentionally not guessed before their current owners land. Each receives a separate post-dependency implementation plan whose first step records the exact protected path/interface; no substitute adapter may be created.

---

### Task 0: Protect the Project Workroom architecture and program plan

**Files:**
- Create: `docs/superpowers/specs/2026-08-29-project-workroom-convergence-design.md`
- Create: `docs/superpowers/plans/2026-08-29-project-workroom-convergence.md`

**Interfaces:**
- Consumes: protected #214/#227/#229/#230/#231 and current Linear/Slack read-only estate.
- Produces: one protected source-law design plus this implementation DAG; zero runtime or SaaS mutation.

- [ ] **Step 1: Re-pin protected procedure and inspect collisions**

Read current protected `docs/sol_skills/INDEX.md`, `COLD_START.md`, `RECONCILE_STATE.md`, `REVIEW_RETURN.md` and `CLOSEOUT.md` from the same SHA. Search current/open PRs for `workroom`, `project channel`, Slack Canvas/List projector and multi-channel Relay ownership.

Expected: no existing Project Workroom implementation carrier; #212 remains the parent convergence plan and does not already own these two new paths.

- [ ] **Step 2: Verify records scope**

Run a changed-file census and require exactly:

```text
docs/superpowers/specs/2026-08-29-project-workroom-convergence-design.md
docs/superpowers/plans/2026-08-29-project-workroom-convergence.md
```

- [ ] **Step 3: Open one draft records PR**

Use title:

```text
[ARCHITECTURE][PLAN] Slack + Linear Project Workroom convergence
```

PR body must state:

- no Initiative mutation;
- no Slack/Linear mutation;
- no new OS/database/lifecycle;
- #231/#223/#228/MAS-64/MAS-66/MAS-189 owner preservation;
- WR-P0 is the only immediately eligible code wave;
- live canary remains dependency-gated.

- [ ] **Step 4: Run current protected checks and adversarial records review**

Require exact-head repository `test`, two-file diff, current protected-source reread and no source collision.

- [ ] **Step 5: Merge with expected-head protection**

Merge only the exact reviewed head. Capture the protected merge SHA as `PROTECTED_WORKROOM_SPEC_SHA` for Task 1.

---

### Task 1: Freeze the exact WR-P0 schemas and shadow strategy

**Files:**
- Create: `config/project_workroom_strategy.v1.json`
- Create: `control_plane/project_workroom_plan.py`
- Create: `tests/test_project_workroom_plan.py`

**Interfaces:**
- Produces constants:

```python
STRATEGY_SCHEMA = "mastermind.project_workroom_strategy.v1"
LINEAR_SNAPSHOT_SCHEMA = "mastermind.project_workroom_linear_snapshot.v1"
SLACK_SNAPSHOT_SCHEMA = "mastermind.project_workroom_slack_snapshot.v1"
PLAN_SCHEMA = "mastermind.project_workroom_plan.v1"
```

- Produces:

```python
class ProjectWorkroomPlanError(RuntimeError):
    failures: tuple[dict[str, object], ...]


def canonical_digest(value: object) -> str: ...
def load_document(path: Path, expected_schema: str) -> dict[str, object]: ...
def validate_strategy(strategy: Mapping[str, object]) -> None: ...
def compile_project_workroom_plan(
    *,
    strategy: Mapping[str, object],
    linear_snapshot: Mapping[str, object],
    slack_snapshot: Mapping[str, object],
    generated_at: str,
) -> dict[str, object]: ...
```

- [ ] **Step 1: Write RED schema tests**

Add literal tests requiring:

```python
EXPECTED_WORK_REFS = {
    "WS:CHAIRMAN-CONTROL-ROOM",
    "WS:AGENT-OS",
    "WS:RATES-INFLATION-COMMAND",
    "WS:BIOCATALYST-CORE-PRODUCT",
    "WS:FINANCIAL-INTELLIGENCE-FABRIC",
    "WS:STOCK-IDENTITY",
}
```

Assert exact strategy shape:

```python
assert strategy["schema"] == STRATEGY_SCHEMA
assert strategy["source_design"]["protected_revision"] == PROTECTED_WORKROOM_SPEC_SHA
assert strategy["workspace_id"] == "T0BRD2AQXQV"
assert strategy["channel_prefix"] == "proj-"
assert {row["work_ref"] for row in strategy["workrooms"]} == EXPECTED_WORK_REFS
assert all(row["privacy"] == "private" for row in strategy["workrooms"])
assert all(row["rollout_mode"] == "shadow" for row in strategy["workrooms"])
assert all(row["allow_linear_project_updates"] is False for row in strategy["workrooms"])
assert all(row["allow_linear_thread_sync"] is False for row in strategy["workrooms"])
```

Required surfaces are exactly:

```python
{
    "home_canvas",
    "project_radar",
    "linear_bookmark",
    "control_room_bookmark",
}
```

Add hostile tests for:

```text
strategy_wrong_schema
strategy_duplicate_work_ref
strategy_duplicate_channel_slug
strategy_invalid_work_ref
strategy_invalid_privacy
strategy_invalid_rollout_mode
strategy_unknown_surface
strategy_live_integration_enabled_in_shadow
```

- [ ] **Step 2: Run RED**

Run:

```bash
python3 -m pytest -q tests/test_project_workroom_plan.py
```

Expected: import/config failure because the module/config do not exist.

- [ ] **Step 3: Create the exact strategy JSON**

Use the protected spec SHA captured in Task 0; never type or guess it from an older head.

The six rows use stable channel slugs:

```text
chairman-control-room
agent-os
rates-inflation
biocatalyst
financial-intelligence
stock-identity
```

Every row is `shadow`, private and integration-disabled.

- [ ] **Step 4: Implement strict strategy/document validation**

Use sorted-key canonical JSON and SHA-256:

```python
def canonical_digest(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
```

`ProjectWorkroomPlanError` must preserve ordered machine-readable failure rows and expose no full private snapshot in its message.

- [ ] **Step 5: Run GREEN**

```bash
python3 -m pytest -q tests/test_project_workroom_plan.py
python3 -m py_compile control_plane/project_workroom_plan.py
```

- [ ] **Step 6: Commit Task 1**

```bash
git add config/project_workroom_strategy.v1.json control_plane/project_workroom_plan.py tests/test_project_workroom_plan.py
git commit -m "feat(workrooms): freeze Project Workroom strategy v1"
```

---

### Task 2: Compile exact Linear + Slack Workroom desired state

**Files:**
- Modify: `control_plane/project_workroom_plan.py`
- Modify: `tests/test_project_workroom_plan.py`

**Interfaces:**
- Consumes the four schemas from Task 1.
- Emits a closed `PLAN_SCHEMA` document with:

```text
schema
generated_at
strategy_digest
linear_snapshot_digest
slack_snapshot_digest
workrooms
hard_failures
summary
```

- [ ] **Step 1: Write RED for one clean shadow workroom**

Create a Linear snapshot row with exact `WS:CHAIRMAN-CONTROL-ROOM`, immutable Project ID, one Initiative parent, no Workroom resource link and current observation evidence. Supply an empty Slack channel list.

Expected action set:

```python
{
    "would_create_channel",
    "would_create_home_canvas",
    "would_create_project_radar",
    "would_add_linear_bookmark",
    "would_add_control_room_bookmark",
}
```

- [ ] **Step 2: Write hostile identity/drift tests**

Require exact typed failures for:

```text
initiative_rollout_unavailable
linear_project_missing
linear_project_duplicate
linear_project_unmanaged
linear_project_state_ineligible
unexpected_initiative_membership
slack_workspace_mismatch
duplicate_workroom
workroom_marker_conflict
channel_name_collision
channel_privacy_mismatch
channel_archived_unexpectedly
home_canvas_missing_or_ambiguous
project_radar_missing_or_ambiguous
managed_canvas_block_invalid
managed_radar_schema_invalid
bookmark_duplicate_or_conflict
manual_remote_change
```

Include negative controls proving:

- a channel named correctly without the exact marker does not bind;
- a marker for another Linear Project does not bind;
- a provider/worker/account-named channel cannot become a Workroom;
- `WS:WATCHLIST-PORTFOLIO-CEO` and `Mastermind-X Linear OS` cannot appear through fuzzy matching;
- Linear `In Progress` never becomes runtime state;
- Slack `RESULT` fields are rejected from snapshot schemas;
- no channel ID is accepted from strategy input.

- [ ] **Step 3: Run RED**

```bash
python3 -m pytest -q tests/test_project_workroom_plan.py
```

Expected: the compiler functions/actions/failures are absent.

- [ ] **Step 4: Implement exact joins and normalized actions**

Use the managed marker:

```text
[MMX-WORKROOM:v1 work_ref=WS:<KEY> linear_project_id=<UUID>]
```

A clean observed Workroom produces only missing-surface/update/noop actions. More than one exact marker match is a hard failure; never select newest/name-most-similar.

Sort output by `work_ref`. Sort failures by `(code, work_ref, object_ref)` and actions by a closed precedence list so the same inputs produce byte-identical output.

- [ ] **Step 5: Implement summary counts**

Exact summary keys:

```text
strategy_workroom_count
eligible_workroom_count
held_workroom_count
observed_workroom_count
would_create_channel_count
would_update_count
noop_count
hard_failure_count
```

- [ ] **Step 6: Run GREEN and mutation-oriented negative tests**

```bash
python3 -m pytest -q tests/test_project_workroom_plan.py
python3 -m py_compile control_plane/project_workroom_plan.py
```

Manually alter one test fixture so name similarity would be the only possible join and confirm the suite fails under any attempted fuzzy implementation.

- [ ] **Step 7: Commit Task 2**

```bash
git add control_plane/project_workroom_plan.py tests/test_project_workroom_plan.py
git commit -m "feat(workrooms): compile exact Workroom desired state"
```

---

### Task 3: Add a zero-network CLI and current-estate shadow evidence

**Files:**
- Create: `scripts/project_workroom_plan.py`
- Create: `tests/test_project_workroom_plan_cli.py`
- Create: `research/project_workroom/project_workroom_linear_snapshot_2026-08-29.json`
- Create: `research/project_workroom/project_workroom_slack_snapshot_2026-08-29.json`
- Create: `research/project_workroom/project_workroom_shadow_plan_2026-08-29.json`

**Interfaces:**
- CLI:

```text
python3 scripts/project_workroom_plan.py \
  --strategy config/project_workroom_strategy.v1.json \
  --linear-snapshot <path> \
  --slack-snapshot <path> \
  --generated-at <ISO8601Z> \
  --out <path>
```

- Exit codes:

```text
0 = valid plan and zero hard failures
2 = valid plan containing hard failures
3 = malformed/refused input; no output replacement
```

- [ ] **Step 1: Write RED CLI tests**

Test:

- deterministic output;
- atomic output replacement;
- no clock/environment/network access;
- malformed input leaves prior output untouched;
- hard-failure plan writes the evidence document and exits 2;
- no secret-shaped keys/values are accepted into snapshots;
- `--generated-at` is required and validated.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q tests/test_project_workroom_plan_cli.py
```

Expected: CLI absent.

- [ ] **Step 3: Implement the CLI**

Use same-directory temporary file, `fsync`, `os.replace`, sorted JSON and trailing newline. Print only:

```text
schema
output path
plan digest
summary counts
```

Never print full snapshots.

- [ ] **Step 4: Run GREEN**

```bash
python3 -m pytest -q tests/test_project_workroom_plan_cli.py tests/test_project_workroom_plan.py
python3 -m py_compile scripts/project_workroom_plan.py
```

- [ ] **Step 5: Capture fresh read-only Linear and Slack snapshots**

Use current connected read surfaces. The Linear snapshot includes only the six strategy rows, exact immutable Project IDs, current project state, Initiative membership and resource links. The Slack snapshot includes the exact company workspace plus currently visible channels and managed-surface metadata required by the schema.

Do not claim the snapshot is canonical. Record observation timestamps and source refs. If the concurrent Initiative rollout is not complete, represent it truthfully and expect `initiative_rollout_unavailable` in the shadow plan.

- [ ] **Step 6: Compile the shadow plan**

Run the CLI with the captured snapshots. Expect zero SaaS writes and either:

- six eligible `would_create_channel` rows after Initiative/Project normalization exists; or
- typed holds for the missing/finalizing Initiative rollout / stale Project state.

- [ ] **Step 7: Commit Task 3**

```bash
git add scripts/project_workroom_plan.py tests/test_project_workroom_plan_cli.py research/project_workroom
git commit -m "feat(workrooms): add zero-network shadow planner receipt"
```

---

### Task 4: Integrate WR-P0 into current repository checks and release it

**Files:**
- Modify only the existing current repository test/CI manifest that owns focused Mastermind Python tests after a current-source path census.
- No workflow or CI file path is pre-authorized merely by this plan.

**Interfaces:**
- Produces one protected `BUILT_NOT_PROVEN / production-inert` WR-P0 planner.

- [ ] **Step 1: Census current CI ownership**

Read current protected workflow/test configuration and identify the one existing owner that ensures the two new test files run. If normal repository `test` already discovers them automatically, make zero CI changes.

- [ ] **Step 2: Run complete focused and repository tests**

```bash
python3 -m pytest -q tests/test_project_workroom_plan.py tests/test_project_workroom_plan_cli.py
```

Run current repository required `test` and security checks on the exact head.

- [ ] **Step 3: Adversarial Sol review**

Verify:

- zero network imports/calls;
- zero Slack/Linear write path;
- no lifecycle/status unification;
- no surface_bindings mutation;
- no fuzzy joins;
- deterministic same-input output;
- exact six shadow strategy rows;
- no Initiative mutation;
- no secret or private full-payload logging;
- honest capability state.

- [ ] **Step 4: Merge exact head**

Merge under current expected-head and current-base law.

WR-P0 final state:

```text
BUILT_NOT_PROVEN / production-inert
```

It proves deterministic planning and drift refusal, not live Workrooms.

---

### Task 5: WR-A0 Workroom Projector credential and Slack API boundary

**Entrance gate:** WR-P0 protected; final Initiative rollout receipt consumed; MAS-64/MAS-66 app-actor lessons reviewed; one exact Slack app/admin permission plan approved; current Slack API capabilities/scopes reverified.

**Observable capability:** one dedicated production-disarmed app can be installed and qualified for only selected private channel/Canvas/List/bookmark projection, with no Executive/Dialogue authority and no secret exposure.

**Required sequence:**

1. Write the separate WR-A0 design/implementation plan against the exact then-current files listed in the File/Owner Map.
2. RED-first fixed-origin Slack client and secret-safe enrollment tests.
3. Implement read-only qualification before any create/update method.
4. Prove exact workspace, bot/app identity, reviewed scopes and app channel membership.
5. Install disabled/unarmed; no channel created.
6. Return exact app/scopes/secret-path metadata without secret values.

**Stop:** no WR-C0 channel mutation until Sol exact-head review accepts WR-A0.

---

### Task 6: WR-C0 one inert Project Workroom canary

**Entrance gate:** WR-A0 accepted and credential enrolled; WR-P0 dry-run clean for one dedicated inert canary identity; Slack Canvas/Lists/bookmark capability confirmed; no overlap with real project channels.

**Observable capability:** exactly one inert private Slack Workroom can be created/read/updated/nooped and safely reconciled without duplicate channel/Canvas/List/bookmarks.

**Canary journey:**

1. create one private canary channel with exact managed marker;
2. read back ID/privacy/purpose/app membership;
3. create one Home Canvas tab and exact managed content;
4. create one Radar List with closed schema and zero or fixture rows;
5. add exact Linear-canary and Control-Room-canary bookmarks;
6. rerun same plan -> zero writes;
7. manually change a managed field -> `REMOTE_CHANGED`, zero overwrite;
8. simulate ambiguous response -> exact read-back reconciliation;
9. archive through the reviewed non-destructive path;
10. verify Canvas/List retention/cleanup behavior and record the platform result.

**Stop:** no real Project Workroom and no Agent Relay routing.

---

### Task 7: WR-D0 evolve protected Agent Relay to reviewed multi-workroom routing

**Entrance gate:** #223 accepted, hidden enrollment/verify complete, exact one-channel A2 canary accepted; WR-C0 accepted; protected #231 remains the runtime foundation.

**Observable capability:** one long-running Relay can read/post only in exact allowlisted Workroom channels resolved from operation/workstream identity, while arbitrary caller/model channel selection is mechanically impossible.

**Required implementation laws:**

- one process/token/service;
- immutable/configured workspace;
- reviewed workroom allowlist from explicit input/config evidence;
- route resolver consumes exact work/operation identity;
- client checks resolved channel against allowlist;
- no `#agent-dispatch` fallback;
- one parent/thread per operation;
- same Slack principal may carry distinct operation actors without becoming runtime identity;
- Slack outage/effect-unknown behavior remains fail-closed;
- current A2 one-channel behavior remains a compatibility negative control.

**Stop:** no automatic parent creation beyond existing AD-DLG2 authority and no Linear Issue/update mutation.

---

### Task 8: WR-D1 bind AD-DLG2 parent ensure to the exact Project Workroom

**Entrance gate:** AD-ID1/AD-CHILD1/AD-DLG2 current owner is protected to the point where one deterministic child identity can ensure one parent; WR-D0 route resolution accepted.

**Observable capability:** a newly admitted selected child gets exactly one parent in the correct Project Workroom despite duplicate ingress or write-response loss.

**Acceptance:** cross-ingress duplicate, sister-Sol same-child race, wrong-workroom refusal, two-existing-parents ambiguity, write effect-unknown and stale binding tests.

**Stop:** no provider execution/return projection changes in this child.

---

### Task 9: WR-L0 consume the accepted Linear Project/Issue/update owners

**Entrance gate:** final Initiative rollout protected/read back; MAS-64 and MAS-66 accepted; MAS-189/OSC-C1 architecture promotion accepted; WR-C0 real channel identity exists.

**Observable capability:** exact Workroom link/resource and selected operation thread references appear on the corresponding Linear Project/Issue; selected Project updates post to the correct Workroom without making Slack authoritative.

**Hard boundaries:**

- extend the exact accepted MAS-66/MAS-189 app actor/adapter;
- no second Linear client/synchronizer;
- exact immutable IDs;
- no automatic public channel creation;
- no contextual/fuzzy `@Linear` agent mutation;
- no raw Agent Dialogue mirroring;
- Project/Issue completion remains owning-proof-derived;
- remote/manual Linear edits use optimistic reread/refusal.

**Stop:** no Control Room or runtime mutation.

---

### Task 10: WR-CR0 Steward / Control Room Workroom projection

**Entrance gate:** #228 read core and later accepted gather adapter protected; AD-CR1 current owner reconciled; at least one accepted real Workroom binding receipt.

**Observable capability:** Steward/Control Room answers `open the Project Workroom`, lists selected operations, and explains plan/runtime/proof/turn/attention/transport separately without storing Workroom lifecycle.

**Required source attribution:** Agent OS, Linear, Executive OS, RuntimeBinding, Wake/Inbox, GitHub, Workroom binding/surface read-back.

**Stop:** no Control Room send/admission path unless separately authorized.

---

### Task 11: WR-M0 / WR-S0 real multi-operator pilot and hostile matrix

**Entrance gate:** WR-D1, WR-L0, governed return projection, Wake and exact Sol action-target path accepted for the selected work class.

**Pilot:** one real Project Workroom, one logical Sol Project Steward, at least three disjoint operator/worker operations and one independent reviewer.

**Hostile matrix:**

- 2 / 5 / 14 native sessions behind shared Slack principals;
- same operation duplicate claim;
- distinct operations allowed;
- path and authority collisions;
- worker kill/restart;
- Sol loss/transfer;
- Slack outage during execution and return;
- Linear outage and later reconciliation;
- duplicate RESULT;
- GitHub merge without proof;
- child STOP with parent active/no successor;
- channel rename/archive/manual Canvas/List corruption;
- provider/capacity exhaustion;
- effect-unknown write.

**Pass condition:** zero duplicate effect, zero silent orphan, zero wrong-thread continuation, zero false completion, zero unauthorized sibling Sol/operator action.

---

### Task 12: WR-P1 / WR-P2 / WR-CUTOVER

**WR-P1:** three real Project Workrooms; new operations only; compare against `#agent-dispatch` baseline.

**WR-P2:** ten to fifteen promoted projects; fairness/starvation and attention latency measured; archived/history behavior proven.

**WR-CUTOVER:** ordinary new selected project operations no longer originate in `#agent-dispatch`; that channel remains forensic/legacy transport. Linear + Control Room are the normal Chairman surface; Slack Workrooms are collaboration/detail drill-down.

No stage advances on channel aesthetics, green CI or one successful demo alone.

---

## Plan Self-Review Receipt

### Spec coverage

Every design requirement maps to at least one task/wave:

- exact hierarchy/identity -> Tasks 1-3, 7-9;
- Workroom channel/Home/Radar/bookmarks -> Tasks 5-6;
- multi-workroom Relay -> Task 7;
- operation parent -> Task 8;
- Linear link/update -> Task 9;
- Steward/Control Room -> Task 10;
- multi-operator concurrency/failure -> Task 11;
- staged cutover -> Task 12;
- no-rebuild/security/correction -> Global Constraints and every entrance/stop condition.

### Placeholder scan

No executable WR-P0 step contains TBD/TODO/unspecified error handling. Dependency-gated later waves intentionally require fresh exact post-dependency plans rather than guessing paths owned by code that has not landed.

### Type consistency

The four schemas and planner function names defined in Task 1 are used unchanged by Tasks 2-4. Workroom strategy/snapshot/action/refusal vocabulary matches the governing spec.

---

## Exact execution decision

Execute inline in the current Sol program:

1. finish Task 0 records carrier and protect it;
2. immediately create the separate WR-P0 code carrier from the protected spec SHA;
3. execute Tasks 1-4 through exact-head merge;
4. then reconcile the newly current dependency estate and write/execute the WR-A0 child plan if its entrance gates are true;
5. otherwise advance the exact dependency owner rather than bypass it.