---
name: mastermind-claude-fabric-delegation
description: Use for an assigned M2 Claude CEO/orchestrator that needs to send bounded work to the existing paid Mastermind Subagent Fabric, recover a child return, or commission an admitted operator with its own economical leaf workers.
---

# M2 Claude -> existing Subagent Fabric

This is an invocation guide, **not** a new tool, root, entitlement, account, queue, lease, or authentication grant. Apply protected Mastermind source law and the actual session's permissions. Never use Claude Agent/Task, raw SSH, direct provider CLIs, copied credentials or an invented Fabric identity as a fallback for a refused or missing Fabric grant.

## First 30 seconds: choose the existing entrypoint

1. From the **current assigned session's trusted binding**, identify the original `root`, your **actual immediate parent** (the current Claude coordinator's admitted run/session binding) and a new unique `run_id` for *one* child. Preserve the original root on every descendant. A filesystem path, model label, project name or prior conversation is **not** an identity. If root/parent cannot be verified, return `FABRIC_IDENTITY_UNVERIFIED` without dispatch.
2. Check the **actually exposed** authenticated tools. If the current session has the existing `fabric_capabilities` / `fabric_request` / `fabric_status` / `fabric_result` / `fabric_accept` tool family, use it; do not assume `mastermindStudio` read/design discovery alone grants submission. Do not manufacture a client or URL.
3. Otherwise, on the **authorized M2 local shell only**, use the installed `fabric_task.py` entrypoint that backs the maintained Fabric service. The incumbent M2 adapter location in this source revision is:
   `$HOME/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext/fabric_task.py`
   Verify that exact file exists and that the currently enrolled runtime points to it. Do not copy or reinstall an adapter from a repository, guess a different home, or switch carriers after an uncertain dispatch. If no authorized entrypoint exists, report `FABRIC_CLIENT_NOT_EXPOSED`; useful direct work may continue.
4. Write one self-contained, bounded work packet: objective, original root, exact allowed source/workspace, baseline SHA, acceptance test, forbidden effects, and return format. Use cheap `C0_MECHANICAL` / `C1_ROUTINE_BOUNDED` workers for routine work. Use higher complexity only with a concrete reason under the current router. Never select a provider/account/host to bypass Capacity.

## Existing M2 CLI example (substitute *verified* binding values)

```sh
FABRIC_ADAPTER="$HOME/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext/fabric_task.py"
test -f "$FABRIC_ADAPTER" || { echo "FABRIC_CLIENT_NOT_EXPOSED"; exit 1; }
# ROOT, PARENT, CHILD and PACKET must already be positively verified/assigned.
python3 "$FABRIC_ADAPTER" request --id "$CHILD" --class mechanical \
  --task-complexity C0_MECHANICAL --packet "$PACKET" --cwd '~' \
  --root "$ROOT" --parent "$PARENT"
python3 "$FABRIC_ADAPTER" status "$CHILD"
# Only after the same child actually has a retained result:
python3 "$FABRIC_ADAPTER" result "$CHILD" --max-bytes 8192
# Only after independent verification/authorized review, and for the actual resolved child:
python3 "$FABRIC_ADAPTER" accept "$CHILD" --by reviewer
```

The original `request` may have executed if its tool response times out. **Never retry, change child ID, or switch to the MCP entrypoint** before same-carrier reconciliation. A controller PID, queued receipt or pending status is not START. Reuse the exact `run_id` for status/result; it is not a request replay. Review concrete artifacts, tests and source custody before acceptance. Unknown/partial results are not accepted. Return exact worker ID, source revision, outcome and remaining effects.

## Existing private Fabric MCP (only when actually granted)

Invoke `fabric_request` **once**, supplying `run_id`, `root_id`, `parent_id`, `task_class`, `task_complexity`, and `work_packet`. The normal sequence is `fabric_status` -> `fabric_result` -> parent review -> `fabric_accept` with the returned digest and verification summary. `fabric_wait` is a short bounded observation, not a scheduler. Never treat a text receipt as original-root identity authentication.

## Parent recovery status is staging-only, not an auto-resume command

A source-proposed `parent_recovery` value on the Web `fabric_status` or
`fabric_wait` response is diagnostic-only. The installed native status remains
the owner, and an attended Mastermind OS DTO consumer does not automatically
receive this optional Web facade field. `root_id:null` can retain an observed
failure/active disposition while `root_verified:false` **forbids parent
attention**. A prelaunch `request_root_id` provides correlation only. All
projection `wake_proven`, `retry_authorized`, `dispatch_authorized`, and
`result_consumption_authorized` flags stay false; no source merge or suggested
disposition can override them. Reconcile the **same original controller**;
never spawn, switch providers or accept a result based on the projection.
Only the existing authorized Executive/Agent OS wake and session-binding
owners may subsequently prove a true parent delivery and consumption.

## To commission an operator that can itself delegate

An ordinary leaf gets no descendant tools. A `domain_orchestration` operator can request C0/C1 descendants **only** when the controller has issued an immutable original-root allowance and its admitted launch has an opt-in `POOL_OPERATOR_CHILD_BUDGET`, a supported model/harness, a bound per-run capability and enough deadline/budget. Refer to `integrations/session_bridge/paid_operator/OPERATOR_QUICKSTART.md` for the incumbent original-root allowance and opt-in. The original principal keeps acceptance and any reserved decisions; do not mint a second root to extend the budget.

Inside the admitted operator, first call `mastermindStudio.fabric_operator_scope` (no arguments). Use returned `root` and `operator_run` as exact child `root` and `parent`. Then call `fabric_child_request` once with schema `mastermind.fabric_operator_child_request.v1`, a new stable `run_id`, `task_class` from the allowed set, `task_complexity` C0/C1 and a bounded `packet`. Observe with `fabric_child_status` / `fabric_child_wait`, consume `fabric_child_result`, review, then call `fabric_child_acknowledge` with the **exact** result SHA256. Acknowledgment closes attention only; original-parent acceptance stays separate. If the scope tool is missing or refused, no child launch is authorized. Do not read/export the private capability, run nested CLIs, or create an operator under an operator.

**Current qualification limit:** the existing paid operator loader admits GLM 5.3 and Grok 4.6 under exact bound grants. A Grok 4.7 example is **not** evidence that Grok 4.7 has been admitted on this route. Use only the actually qualified installed provider route; extending the model catalog needs its own admission and live proof.

## Proof ceiling

Installed skill != loaded skill != authenticated tool != admitted Fabric START != reviewed accepted result. For rollout, verify the provider-home installation, a freshly started Claude session loading this skill, and one source-custody-safe root -> worker -> result -> review/accept path. For the nested path require real operator scope, child START, exact return to the same operator, its acknowledgement, and principal adjudication. Keep any missing evidence explicit.

## Fresh Claude identity and authenticated tool preflight

Before launching a child, check the current **fresh** Claude Code session's
actual authenticated state using `claude auth status` (read-only) and the
workspace's native trust ceremony. An installed
`mastermind-claude-fabric-delegation` skill, an existing user-home directory,
or a model label does **not** establish a fresh authenticated session, loaded
guide, original root or immediate parent.

- If `loggedIn=false`, the CLI reports `OAuth session expired and could
  not be refreshed`, or the workspace trust dialog is pending, return
  `CLAUDE_LOGIN_REQUIRED` and **dispatch nothing**. Only the actual account
  owner may complete interactive OAuth login and approve the native workspace
  trust dialog. Do not edit `~/.claude.json` to suppress trust, borrow a
  Parallel-app account, read/replace credentials or pivot providers.
- After authentication, the session itself must demonstrate loading this
  guide and resolve its original Fabric root and immediate assigning parent
  from trusted current binding. Missing evidence remains
  `FABRIC_IDENTITY_UNVERIFIED`, even when `fabric_task.py --help` works.
- If its shell sandbox denies Fabric packet retention, follow the same
  no-replay, same-run reconciliation and explicit authority boundary described
  by `FABRIC_ADAPTER_SANDBOX_DENIED` in the Codex Fabric skill. Do not switch
  a refused operation to MCP or a less restrictive shell.
