# Cursor on M2: Mastermind Agent OS / Fabric integration

## Actual M2 audit — 2026-10-22

Cursor desktop `3.25.9` and Agent CLI `2026.10.12-d47ca18` are installed.
The CLI advertises Composer 2.5, Gemini 3.7 Flash, Grok 4.7, Opus 5.5, Sol
and other models; advertised availability is **not** measured free quota.
The user-local `~/.cursor/mcp.json` retains the existing `paper` binding and
now has `mastermindStudio` pointing to the **read-only** existing guarded
Tailnet `/studio-fabric` route. The Cursor CLI returned:

```text
paper: ready
mastermindStudio: ready
Tools for mastermindStudio (5):
paper_catalog, paper_inspect, paper_read, studio_fleet_status, studio_ping
```

This proves neither seven Fabric dispatch tools nor worker START. The
separate running `subagent-fabric-c3` private service is an existing
account-bound carrier and is **not** a Cursor authorization.

### The native Task failure

A clean Cursor CLI scratch-canary with project-local `.cursor/agents/mmx-repo-explorer.md`
observed a genuine `taskToolCall`, but the imported user-level Claude
`~/.claude/settings.json` PreToolUse hook denied it. A read-only diagnostic
hook captured the distinct Cursor input contract:

```text
tool_name=Task
tool_input keys: description,prompt,run_in_background,subagent_type
top-level: cursor_version,model,workspace_roots,session_id,...
env: CURSOR_VERSION,CURSOR_PROJECT_DIR
```

The inherited Claude guard looked at `tool_input.model` (absent), while
the top-level model identifies the parent, not the child. The model-declared
role must NOT be promoted to proven model selection. The existing installed
Claude guard is a different locally evolved generation from the pinned repo;
replacing it wholesale with the base source would lose active local protections.
The candidate here is **source-only**, pending incumbent owner reconciliation.

Official Cursor references:
- https://cursor.com/docs/subagents
- https://prod.cursor.com/docs/reference/third-party-hooks
- https://cursor.com/docs/sdk/typescript

## Reusable project-local role projection

`install.py` does not install MCP servers or credentials. It pins five
reviewed role/skill source digests, requires an exact existing Git root,
refuses symlinks and incompatible existing targets, preserves user-local and
project-local Paper/MCP/other agents, and supports dry-run/readback.

```sh
python3 integrations/cursor_agent_mastermind/install.py \
  --workspace /absolute/path/to/approved/exact/git/root --mode plan

python3 integrations/cursor_agent_mastermind/install.py \
  --workspace /absolute/path/to/approved/exact/git/root --mode apply

python3 integrations/cursor_agent_mastermind/install.py \
  --workspace /absolute/path/to/approved/exact/git/root --mode verify
```

Installation or verified static configuration is **not** task execution.
Do not apply over another worker's live source/worktree.

The four custom roles are Explorer (Gemini 3.7 Flash, read-only),
Implementation Worker (Composer 2.5), Independent Reviewer (Grok 4.7,
read-only), and Fabric Operator (inherits orchestrator). The operating
skill `mastermind-fabric` explains exact Fabric tools, root/parent custody,
routing economics and same-run result consumption. A native Cursor child
is not an externally admitted Fabric worker. Only the Explorer and Reviewer
are admitted by this source candidate's **read-only** Cursor Task policy.
Implementation Worker and Fabric Operator are NOT authorized native children
by the new hook exception.

## Provider policy integration: not live until reviewed

`ops/executive_os/cursor_native_child_policy.py` is a pure, fail-closed
companion. The existing `provider_orchestrator_guard.py` source now
distinguishes an attested Cursor Task shape from Claude-native Agent/Task
without changing the Claude branch. The incumbent
`provider_orchestrator_policy.py` source installs the companion in its
already-owned hook locations before the guard, and verifies exact bytes.
No second hook/authorization service is created.

The current M2 installed guard at `~/.claude/hooks/mastermind_fabric_routing_guard.py`
was **not replaced**, because it includes host-specific protection and its
effective source lineage must first be reconciled by its owner. Do not
disable third-party hook imports or loosen Claude's existing restriction to
make Cursor tests pass. A model prompt, role name or local file is not grant
or proof of actual child execution.

## MCP readiness and Fabric admission

Run the bounded CLI tool-surface census:

```sh
python3 integrations/cursor_agent_mastermind/qualification.py \
  --server mastermindStudio
```

`READ_ONLY_OR_UNRELATED_MCP` is expected today and returns exit 2.
`FABRIC_CATALOG_EXPOSED_NOT_ADMITTED` can only establish the typed tools
are listed, **not** that a connected provider/session has an admitted root,
identity, quota, or a started worker. This utility never reads secret bytes
or dispatches a worker.

Normal Cursor Fabric onboarding must use the **existing incumbent** authenticated
provider connection/capability owner, with an exact Cursor principal/session
grant and reviewed seven-tool bounded contract. The separate account-bound C3
private service may not be repointed, copied or reused as a proxy. The source
proposal in Mastermind PR #1217 owns related provider projection/Studio access;
reconcile its active owner before editing overlapping runtime endpoints.

### Release/acceptance gates

1. Independent owner review of the source-candidate hook diff, local installed
   guard lineage, required source hashes and loaded effective Cursor/Claude
   hook behavior. Test Claude-native denial remains in force; do not install
   directly over locally divergent M2 guard.
2. Source package tests pass plus review of exact worktree, model/subagent role
   files, and non-conflicting scope.
3. A genuine Cursor CLI Task event **starts** a project-local read-only subagent;
   inspect the tool trace and actual selected child model/fallback. No parent
   doing the work instead.
4. A separately enrolled, authenticated Cursor Fabric MCP connection shows the
   seven typed tools, `fabric_capabilities`, and actual child/root admission.
5. One newly authorized bounded child is requested **once**, reaches proven
   START, returns an exact result through the same carrier, undergoes actual
   independent verification and parent acceptance/readback.
6. Agent OS holds durable mission continuity and GitHub holds implementation,
   independent review and, when owed, real consumer-path proof.

Never treat `QUEUED`, `CONTROLLER_CREATED`, MCP `ready`, green tests or
a declared model as worker START, released source or accepted outcome.
