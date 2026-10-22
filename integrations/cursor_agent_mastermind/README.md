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


## Exact M2 installed guard reconciliation candidate (not installed)

The active M2 Claude hook is not equal to the protected-repository guard and
must **not** be replaced wholesale. At the October 22 readback it had
SHA-256 `d1fabbcb39bfd7bfd1552d79acc5ada346f0ac47c887802fb6b021afe84a3840`
and retained eight host-specific functions absent from the source candidate
(including local CI cooldown state and legacy Macro root checks).

`m2_host_guard_overlay.py` is a pure, SHA-gated, **source-only proposal**
against that **exact** installed preimage. It composes a 23-line Cursor Task
classifier before the existing Claude Agent/Task model fence; all original
bytes remain unchanged when that insertion is removed. Candidate digest:
`9c70114886c6ce80fdd1916ece254e6e3fc018d9dbfbd220a191f395f29a0633`.
The companion policy digest at this release is
`d9dd42958800ea888279d62d457814bd16230af4d1e9f6d9bca11c07bf0413dd`.

The M2 local dry-run was executed **only on an isolated candidate copy**.
Original Cursor custom Task denied as before; candidate permitted exactly the
hash-pinned read-only explorer role. Claude Task with inherited
`CURSOR_VERSION` remained denied; changed Cursor version and unadmitted
implementation-worker role remained denied; unrelated Bash hook behavior
matched; original installed hook checksum was unchanged. Actual child model,
paid quota, START and Fabric admission were not proven. Two targeted
follow-up reviewer invocations timed out without any usable verdict;
independent host-overlay review remains **required**.

**Do not install, execute, or copy the composed candidate over the M2 guard
without incumbent policy-owner review and release authorization.** The incumbent provider-policy owner must reconcile against
the same still-current installed SHA, verify the 32-line insertion and companion
under the existing hook policy, obtain independent review and safe canary
admission, and only then perform the original-owner guarded update with backup,
effect reconciliation and live Cursor+Claude tests. Any changed preimage
invalidates this candidate and requires new bounded reconciliation. It is
not an external provider grant or new control plane.


## Cursor native workflow parity hardening (separate from Fabric enrollment)

This package now projects **12 reviewed, hash-pinned files** into one *explicitly
authorized exact Git repository root*: four custom Cursor agents, four
`.cursor/rules/*.mdc` project rules, and four `.cursor/skills/*/SKILL.md`
skills. It does not edit the M2 global Cursor settings, credential store, MCP
binding, installed Claude guard, Executive OS, Agent OS or capacity owner.

Native Cursor features used here follow the [official rules][rules],
[subagents][subagents], [skills][skills], [CLI][cli] and [worktrees][worktrees]
contracts. Project rules are discoverable from `.cursor/rules`; a single
short always-applied core anchors project authority, and three
description-selected rules make planning, model economics and verification
relevant on demand rather than polluting every session's context. Skills
provide actionable multi-phase procedures and can be invoked with
`/mastermind-long-horizon`, `/mastermind-model-routing`, and
`/mastermind-verify-and-close`.

| Capability from Claude/Codex workflows | Cursor-native building block | What is actually proven |
| --- | --- | --- |
| Role and project instructions | `AGENTS.md` plus the short `.mdc` core rule | Source package and disposable project projection; runtime core-rule answer canary |
| Long-horizon plan | Cursor Plan mode and `mastermind-long-horizon` skill | Source/project install proven; real sustained multi-phase session **not** proven |
| Specialized model-aware workers | Native custom subagents with role `model` frontmatter | Role/source/model catalog observed; live user Claude hook still blocks custom Task |
| Delegation to Subagent Fabric | Existing `mastermindStudio` MCP and canonical Executive owner | 5 read-only tools exposed, 0 Fabric typed tools; no dispatch grant |
| Source collision control | Existing `mmx-workspace` admission and operation-owned worktrees | Source workspace provenance observed; Cursor `agent -w` **not** permitted in occupied lanes |
| CI / code review | GitHub checks, `mmx-independent-reviewer`, `mastermind-verify-and-close` | Local tests; independent *host guard* review still outstanding |
| Project recovery | Cursor `agent resume`/ID resumption plus canonical Agent OS frontier | CLI resume advertised; cross-session Agent OS durable handoff not yet exercised |
| Per-project reusable knowledge | `.cursor/skills` and scoped `.cursor/rules` | 12-file projection verified; no Cloud skill sync is implied |
| Browser/desktop tool use | Native Cursor Browser agent, approved MCP/Computer Use when enrolled | **Not** granted or proven by these local role files |
| Environment isolation | Canonical workspace manager and reviewable Git commits | Cursor's own worktree auto-cleanup not permitted to own these registered repos |

### Safe project enrollment and health census

Obtain or reuse the **incumbent** approved Git-linked worktree; do not use
Cursor `agent -w` or automatic worktree creation on an already-leased
Mastermind source lane. From a verified checkout that contains this package:

```sh
python3 integrations/cursor_agent_mastermind/install.py   --workspace /absolute/verified/git/root --mode plan
python3 integrations/cursor_agent_mastermind/install.py   --workspace /absolute/verified/git/root --mode apply
python3 integrations/cursor_agent_mastermind/install.py   --workspace /absolute/verified/git/root --mode verify
python3 integrations/cursor_agent_mastermind/diagnose.py   --workspace /absolute/verified/git/root
```

`plan` never writes; `apply` never overwrites a conflicting file. It
hashes source bytes, preflights *all* targets before writing and opens
each parent directory via non-following directory descriptors to resist
symlink races. Interrupted writes require readback of the exact destination
before another attempt. Project enrollment is a governed source edit: do
not apply to another writer's live worktree or a protected main checkout.

`diagnose.py` is strictly **read-only**. It allowlists four benign CLI
catalog probes, reports requested role IDs against advertised models,
and shows MCP server/tool names without outputting account identity,
secret configuration or arbitrary CLI output. It deliberately returns
`fabric_dispatch_authorized=false`, `native_task_started=false` and
`observed_actual_models=false` until proven elsewhere. No scheduled health
polling, retries, worker dispatch, credentials or extra runtime state exist.

### M2 scratch evidence

A disposable Git-root projection installed/verified all 12 assets and the
read-only diagnostic observed the authenticated Cursor model catalog (265
advertised IDs at the time, **not** quota or usage) while reporting the
5-tool existing Studio MCP as `READ_ONLY_OR_UNRELATED_MCP`. One root
Cursor `--mode=ask` canary with Composer 2.5, no tool calls and no file
reads answered `--force,--yolo`, consistent with consumption of the
always-applied core rule. This is **rule-consistent answer evidence**, not
a guaranteed project-rule injection trace or proof of a custom Task child.
The scratch repository was discarded after the canary.

### Model choice and economics

Cursor `agent --list-models` is a catalog, not a model-dispatch receipt.
Frontmatter selection can be overridden by Cursor plan/team restrictions,
and a native child is not the equivalent of an Executive Attempt. Separate
declared model, actual observed child model, paid pool and end-result
verification. Prefer cheap deterministic operations without spawning,
then qualified bounded work through already-admitted Fabric. Keep C3
architectural judgment under the assigned principal, not automatic
parallel clones.

### Remaining hard gates

- Live imported Claude hook compatibility must be reviewed and reconciled
  with the *exact* installed M2 SHA before any original-owner release.
- Only then prove a real project-local Cursor Task child START, result,
  and actual selected model. A role discovered by Cursor is not START.
- The incumbent #1217 provider owner must enroll the actual Cursor Fabric
  principal, with seven typed tools, exact root/parent and capacity grants.
- An admitted Fabric request must reach START, return, undergo verification
  and be accepted/read back through the existing owners. Browser and
  Cloud/self-hosted capabilities require their own real-path acceptance.

[rules]: https://cursor.com/docs/rules
[subagents]: https://cursor.com/docs/subagents
[skills]: https://cursor.com/docs/skills
[cli]: https://cursor.com/docs/cli/overview
[worktrees]: https://cursor.com/docs/configuration/worktrees


### Headless Plan mode and real Task trace qualification

The M2 `agent --print --mode=plan` scratch canary returned process exit 0,
emitted `createPlanToolCall` and **two `interaction_query` events**,
and never returned a completed two-phase plan. Its fixture was unchanged.
Therefore a *CLI success event is not plan acceptance*. Use **interactive**
Cursor Plan mode where a plan requires an explicit decision/approval; in a
headless path, treat interaction queries as an unresolved input gate and
require actual emitted plan content/artifact plus review before calling it
complete. Do not blindly retry a stateful plan interaction.

An offline, bounded trace checker now makes this failure mode explicit:

```sh
python3 integrations/cursor_agent_mastermind/trace_proof.py   --trace /path/to/an/existing/cursor-stream-json-trace.jsonl
```

This parser reads one existing regular 4-MiB-max trace, exposes only
sanitized event-type and tool-call counts, refuses symlink traces, and
distinguishes root process success, native Task call, Task hook denial and
interactive Plan questions. It **never** claims an actual child START,
selected billed model, Fabric admission, accepted plan or source release
from Cursor's incomplete CLI event stream. Those must be attested by
separate actual parent/child/Runtime and consumer evidence. It stores
no execution history and performs no provider API calls.
