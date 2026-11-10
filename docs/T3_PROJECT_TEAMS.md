# T3 project teams: COO, directors and workers

This extension makes a source-owned project definition usable by T3's existing
native project/thread/delegation tools. It does not create another company task
system, scheduler, provider router, memory store or unattended runner.

## What is implemented

A `ProjectTeam` composes the existing `MissionBrief` with a hierarchy of COO,
director and worker assignments. Directors can own directors or workers; workers
are leaves. The compiler checks inherited phase/path scope, complete phase
coverage, ancestry, dependency deadlocks, requested depth and agent ceilings,
and conflicting writers in a shared checkout.

T3 already supplies `delegate_task`, native child returns, persistent threads and
worktree preparation. At native source `0770446869d247a8b28c27d7ed93f47f8ff0c1e4`,
`delegate_task` accepts `isolation: "shared" | "worktree"`. This extension reuses
that facility. A director can request its own worktree; its workers can share it
with disjoint paths or request further native isolation. A role label alone is
not isolation proof: subsequent preparation checks observed native workspace
paths. Path observation is not a filesystem/lease attestation.

The root retains the original objective and DONE_WHEN. Each child receives its
bounded scope, phase checks, descendant assignments, exact root/immediate-parent
identities, dependency evidence, source references and stop conditions. Large
teams use an immutable definition reference and fingerprint rather than silently
truncating the graph. An original 41-role graph is covered by a regression test.

`ProjectTeamClient` composes the incumbent `T3CliClient` for actual root launch
and native reads when an authorized caller supplies its existing runner. It adds
no subprocess manager or authentication flow. Ambiguous native effects propagate
without retry. The standalone CLI only prepares and inspects data.

## The native workflow

```text
Existing project/source owner
  -> validated team definition + immutable source revision
  -> existing T3 root launch (one COO, native isolated workspace)
     -> native delegate_task (director, optional native worktree)
        -> native delegate_task (bounded workers)
        <- original task/thread/run results
     <- director integration and source-owner review
  -> original COO verifies the integrated consumer and remaining DONE_WHEN
```

The native parent invokes `delegate_task`; an external caller cannot impersonate
that parent by putting its ID in a JSON object. Native authentication and existing
Executive/Capacity admission remain authoritative. Requested ceilings are
planning limits, not newly issued budget or atomic reservations. Provider/model
fields are deliberately omitted: consume the existing qualified routing owner,
never invent an alias, silently select another account or inherit a role title
as a frontier-model entitlement.

Worktree children start from the parent's **committed** source; uncommitted edits
are not copied. Before launching a dependent slice, integrate its accepted input
branches through the existing source/review owner and commit that input. An
acceptance-reference link does not itself move code into the new worktree.
Parallel worktrees also do not eliminate later merge conflicts.

## Definition and continuity ownership

The team JSON is an assignment overlay on `MissionBrief`, not a second task
lifecycle. It contains no mutable task status or execution queue. GitHub owns the
source definition. The existing Agent OS/shared-notes/runtime owner retains
`RoleBinding` receipts and dependency evidence. Native T3 owns threads, tasks,
runs and current status.

The adjacent long-horizon source plan and T3/Hermes context work in PR #2375 remain
intact. This extension does not install competing hooks or replace that parser.
Likewise, the active MMOS integration program owns company admission, T3 execution
adapters and runtime deployment; no files on that program's active paths are
replaced here.

An exported observation bundle contains retained bindings, exact native reads,
source evidence and the normalized native inventory:

```json
{
  "bindings": [],
  "observations": {},
  "dependency_evidence": [],
  "uncertain_role_ids": [],
  "native_inventory": null
}
```

`bindings` contain exact native receipts, not guessed IDs. `observations` are
current native `thread show` results keyed by role ID. Dependency evidence must
name the immediate parent reviewer, current team fingerprint and immutable source
reference. The compiler checks consistency, not the reviewer's authentication.
Missing, stale, mismatched or uncertain evidence remains unqualified.

The ordinary `t3 thread list` command filters out subagents at the inspected
native revision. `read_native_inventory` instead calls the existing native MCP
`t3_thread_list` with `includeSubagents: true`, bounded pagination and no status
filter. It requires an injected, already-authorized native reader; it adds no
connection or authentication flow. Complete current inventory is required before
preparing a delegation. Hidden/unbound children, pagination drift, missing native
threads, mismatched runs, stale reads and uncertain effects remain unreconciled.
The 120-second freshness check is not authentication or an atomic snapshot.

The graph separately reports `all_defined_results_available` and
`all_native_results_available`. The latter additionally requires the fresh
native child inventory to match the known bindings. Neither implies acceptance.
Native thread reads retain the native owner's delivery semantics, including its
possible acknowledgement of a child result; this compiler adds no acknowledgement
store or delivery owner.

Resume by reading the original bindings and native runs. Do not launch another
COO because a browser or CLI reply was lost. A stopped/restarted caller retains
the original authenticated namespace: identical request IDs under different
OAuth clients are not a safe replay strategy. Do not overwrite a binding with a
newer run without reconciling the original effect through its native owner.

## Local commands

From the source checkout:

```bash
python3 -m integrations.session_bridge.t3_project_team_cli check \
  examples/t3_project_teams/mastermind-os-template.json

python3 -m integrations.session_bridge.t3_project_team_cli graph \
  examples/t3_project_teams/mastermind-os-template.json
```

The example is explicitly **not a live MMOS commission**. Its paths are
illustrative, its admission reference is unbound, and its stop condition forbids
dispatch until the original project owner supplies the accepted plan, exact
paths, current source and actual budget. Do not create a second MMOS program.

To prepare an actual native launch after those bindings are qualified:

```bash
python3 -m integrations.session_bridge.t3_project_team_cli launch-request \
  path/to/source-owned-team.json \
  --project-id EXACT_NATIVE_PROJECT \
  --environment-id EXACT_NATIVE_ENVIRONMENT \
  --request-id original-project-operation
```

This emits `t3_thread_launch` arguments, an exact source/worktree base and a stable
request identity. `expected_environment_id` is caller-side binding metadata, not
a native forwarding parameter: native `environmentId` selects a linked remote
environment, so it is deliberately omitted for this environment-local adapter.
It reports `NOT_DISPATCHED`. Execute only through the existing
authorized native tool/adapter, retaining that caller namespace and its original
receipt. No profile, default model, credential or thread is changed by preparing
this request.

For a large definition, add `--definition-ref` with the full immutable GitHub
`blob/<40-character-commit>/...` reference. It must identify the complete JSON
whose fingerprint is supplied. The native/source owner verifies the bytes before
delegation; a syntactically valid URL is not an authentication receipt.

Prepare a director or worker request from the existing owner's export:

```bash
python3 -m integrations.session_bridge.t3_project_team_cli delegate \
  path/to/source-owned-team.json --snapshot existing-owner-export.json \
  --parent-role coo --child-role runtime
```

It requires the exact active parent run, known native observations, completed
source-evidence dependencies, no applicable uncertain effect, and room beneath
the requested snapshot ceiling, including conservative headroom for unbound
uncertain effects. It emits a native `delegate_task` request and
retains the intended immediate parent. The function does not reserve capacity or
call a model; native atomic admission remains the final gate.

## Source-bound project help in the root handoff

The optional project-plan arguments attach an exact read selector to the existing
root handoff. They use the incumbent bounded Markdown plan loader and the shared
`coo.project_help.v1` source comparison. Supply all five arguments together:

```bash
python3 -m integrations.session_bridge.t3_project_team_cli launch-request \
  path/to/source-owned-team.json \
  --project-id EXACT_NATIVE_PROJECT \
  --environment-id EXACT_NATIVE_ENVIRONMENT \
  --request-id original-project-operation \
  --plan-workspace-root /path/to/assigned/workspace \
  --project-plan docs/plans/project.md \
  --plan-work-ref WS:PROJECT \
  --plan-source-ref https://github.com/mastermindx-market-intelligence/Mastermind/blob/EXACT_COMMIT/docs/plans/project.md \
  --plan-sha256 EXACT_SOURCE_BYTES_SHA256
```

Replace the commit and digest placeholders with the assigned source identities.
The exact plan URL must equal the team's existing `mission.source_ref`.
`--definition-ref` can still identify a separate immutable team JSON definition.
The loader verifies the selected local bytes and rejects stale digests, escaping
paths and symlinks. The shared contract validates the work reference, path,
content digest and parsed contract digest. A syntactically valid reference is
still a source expectation; the compiler does not authenticate the corresponding
remote commit or an Executive mission.

The resulting `project_help` guidance contains only the expected source plan and
`executive_project_help({"work_ref": "WS:PROJECT"})`. It explicitly says
`read_state: NOT_READ`, `execution_authority: false` and
`native_origin_attested: false`. It contains no Executive root, parent binding,
session receipt, capacity promise or native-origin assertion. The ordinary
model-visible tool on the session's actual authenticated COO MCP connection is
the read consumer. The compiler creates no Executive client or new connection.

That connection must be explicitly enrolled for the new project-help contract
and the exact original mission/source-plan scope. An old COO catalogue or a
Hermes-only registration does not authorize a T3 caller. The authenticated owner
revalidates the current original Executive root and adopted source before and
after the read. The handoff requires the returned `scope.source_plan` to match
its expectation exactly. Missing tool/enrollment, unavailable current source,
or a different plan means project help is unavailable; none permits another
principal, invented root or substitution of the T3 `mission_id`/thread ID.
Returned addressability remains separate from teammate relationships, placement,
execution permission and result consumption.

The same optional arguments work with `check`, `brief` and `actions`; generated
manual check/prepare actions retain them. Neither automatic project hook is
enabled. Programmatic callers pass the actual parser output and exact source URL
as `project_context` and `project_source_ref` to `ProjectTeam.root_handoff`,
`ProjectTeamClient.launch` or `launch_request`. Omitting both preserves the
incumbent handoff bytes. A programmatic dictionary or pasted help result is not
an authenticated reader or authority.

Keep the original prepared message and native receipt when reconciling a lost
launch reply. Do not regenerate a different source expectation and treat it as
a replay of the original effect. This optional read guidance neither performs
that launch nor changes its existing recovery owner.

## Native T3 project actions

Build a portable, standard-library-only CLI from an exact committed generation:

```bash
mkdir -p dist
python3 scripts/build_t3_project_team.py \
  --expected-head "$(git rev-parse HEAD)" \
  --output dist/mastermind-t3-team.pyz
```

The build verifies committed source bytes and refuses to replace an existing
output. It does not install a service or alter the T3 app. The package works in a
fresh Python process outside the source checkout.

Generate the native `t3.json` fragment using the actual package path and project:

```bash
python3 -m integrations.session_bridge.t3_project_team_cli actions \
  path/to/source-owned-team.json \
  --launcher /absolute/path/mastermind-t3-team.pyz \
  --project-id EXACT_NATIVE_PROJECT --environment-id EXACT_NATIVE_ENVIRONMENT \
  --request-id original-project-operation
```

The actions are **Check project team**, **Inspect project graph**, and **Prepare
COO launch request**. They use T3's existing project action mechanism and never
autorun on worktree creation or settlement. Merge/import through the existing
project settings owner; do not overwrite someone else's action list. The sample
`examples/t3_project_teams/t3.json` contains explicit placeholder paths and IDs.

## Portable graph and Mastermind OS integration

`project_graph` emits `mastermind.t3_project_team_graph.v1`: role/dependency edges,
requested workspace partitions, exact native bindings, observed workspace
qualification, original-result availability and unknown/failed/pending states.
No transcripts, provider secrets or new task store are created.

A completed COO thread does not complete the project. The projection only reports
all native results available when every defined descendant has a qualified
original result. Missing children, queued work, different latest runs, unresolved
effects and unqualified workspace claims prevent that roll-up. Even then,
`acceptance` remains `not_evaluated`; original consumer proof and source-owner
acceptance are separate obligations.

The existing Mastermind OS gateway can consume this projection and route actions
to the same native/Executive owners. Do not add a parallel backend just to display
the graph. Cross-environment delegation and active MMOS deployment remain with the
existing integration program; this initial binding contract is environment-local.

## Qualification boundaries

Focused tests exercise the real incumbent Python client with controlled native
responses, negative graph cases, exact-parent binding, uncertain-effect behavior,
workspace claims, hidden-child inventory, stale/partial reads, case/Unicode path
aliases, progressive disclosure, CLI quoting and fresh-process packaging.
`scripts/qualify_t3_project_team.mjs` additionally loads the **actual pinned T3**
project-file parser and native delegation/workspace/prompt schemas. It does not
replace them with a handwritten approximation.

These prove source behavior and native contract consumption. They do not prove
that the live app imported the actions, that an actual COO/director/worker model
team completed a project, that company routing is armed, or that installed T3
0.1.7 has the exact inspected source. Those require original native receipts and
the incumbent runtime/source owner. Never promote a parsed action or prepared
request into START, successful execution or acceptance.
