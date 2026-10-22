---
name: mastermind-fabric-delegate
description: Use for substantial Mastermind Codex coding, tests, debugging, research or review whenever an independent bounded worker could help. Route eligible leaf work through the already-installed external Subagent Fabric (GLM, Qwen, MiniMax, Grok) before native Codex worker/explorer spawning. Preserve original parent identity, lease, result and acceptance; do not dispatch when unavailable.
metadata:
  short-description: Delegate Codex leaf work through external Fabric
---

# Codex -> existing Mastermind Subagent Fabric

Native Codex `spawn_agent`/full-history forks are **not** external Fabric workers; a parent Sol model may be inherited. The existing Fabric is a separate, shared provider/host pool. Prefer it for independently checkable leaf labor when existing admission and current shell/sandbox allow; keep actual coordinator judgment with the parent. Do not start another orchestrator or separate queue.

## Select the lawful execution path

1. Use the installed M2 shell adapter below directly for new ordinary paid Fabric work when this session's existing shell/network permissions permit it. Executive MCP/plugin, company Mission, RuntimeBinding and idle Wake are optional integrations, not prerequisites for this path.
2. Preserve an operation already submitted through another carrier. A `QUEUED` Executive intent is not worker execution, but never duplicate that same operation through the shell. Keep its original identity and reconcile through its existing path.
3. The adapter reuses `pick.py`, `remote_sub.sh`, host/broker admission and `pool_ledger.py`. Let it choose provider/account/host; do not compose raw SSH or provider calls. Preserve real permission refusals and uncertain effects; do not weaken a sandbox or switch identity/carrier to bypass them.

```sh
FABRIC_ADAPTER="$HOME/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext/fabric_task.py"
test -f "$FABRIC_ADAPTER" || echo 'FABRIC_ADAPTER_NOT_INSTALLED'
python3 "$FABRIC_ADAPTER" --help
```

## Normal task-aware routing

The Chairman ended the temporary Grok quota-use priority after its October 11, 2026 reset. For new ordinary work, omit `--pool grok` and let the installed router select an admitted provider, account and host using task complexity, quality, cost, capacity and review independence. Routine bounded labor uses the normal economical pool order; Grok remains available for suitable complex work and independent review under normal admission. No quota-use deadline or aggressive Grok fan-out instruction remains active.

Keep using the direct shell Fabric adapter; optional Executive integration is not a prerequisite. Retain current host capacity and placement protections. Existing submitted workers keep their original run, provider, root, parent and owner through result review and acceptance; a routing change does not authorize cancellation, replay or replacement.


## Economical decomposition before dispatch

The installed router selects a provider for a supplied task class; it does not invent
independent leaf tasks from a large coordinator assignment. Before choosing native
workers or assigning an entire multi-phase mission to one frontier operator, look for
one or a few *real*, independent, bounded sub-results that another worker can produce
and the parent can check. Decompose only when that lowers end-to-end work plus review
overhead. No arbitrary splits, quota-burning exercises or generic extra reviewers.

- C0 mechanical / census / extract: exact file/symbol inventory, bounded log census,
  specified-data extraction, deterministic configuration comparisons, or narrow
  test-result triage with concrete source inputs and acceptance criteria. Choose
  --class mechanical, --class census or --class extract and
  --task-complexity C0_MECHANICAL when appropriate. This is the principal low-cost
  leaf path; MiniMax M3, Qwen and GLM Flash compete under incumbent admission policy.
- C1 routine bounded: a small owned-path code change with a precise failing test,
  a tightly specified repair, or another single-objective task. Choose the accurate
  class (fix_build for an actual coding fix), --task-complexity C1_ROUTINE_BOUNDED
  and the reproducible test. Do NOT label a census fix_build merely to use a model.
- C2 complex bounded: genuine multistep debugging or a review that requires
  nontrivial judgment; keep its proof and escalation reason explicit.
- C3 frontier judgment: unresolved architecture, integration and high-ambiguity
  coordination stay with a qualified principal/operator; do not dilute them into
  mechanical labels or disguise model/role restrictions.

Every delegated leaf must specify one objective, at most five relevant constraints
when considering MiniMax, source/workspace scope, expected output, deterministic
validation, no effects outside the bound, and an original-root/parent return. Preserve
one source writer per effect scope. Do not force --pool simply to meet a utilization
target. Capacity, model eligibility, safety refusals and reviewed escalations always
win over an economical preference.

For independent code review provide --subject-pool when the subject provider is known,
and check reviewer-not-author/other directional restrictions; omitted provenance
is not independent-review proof. A completed provider process is NOT accepted work.
Consume the retained same-ID result and either verify and accept it with the existing
owner, or explicitly record that no quality verdict was established; do not fabricate
approval or mark a failed run accepted. In Fabric pool stats, the legacy
first_pass_acceptance divides by all outcomes, including outcomes labeled none;
use quality_verdict_coverage, n_quality_verdict and
evaluated_first_pass_acceptance before concluding that a model is poor. Very small
quality samples support no broad conclusion.

When no useful independently checkable C0/C1 sub-result exists, keep the actual work
on its capable operator or coordinator; do not manufacture a cheaper worker.

## Dispatch an admitted, bounded work item

Choose the shallowest useful route: a CEO may assign an eligible operator or worker directly, a native coordinator may assign a worker directly, and an operator may execute its assignment itself. Preserve deeper delegation when its coordination/review saves work.

For a top-level Codex principal, resolve its actual `CODEX_THREAD_ID` as the original root and assigning parent. A native coordinator must verify its native ancestry and the parent's bounded commission, retain that original root, and use its own actual `CODEX_THREAD_ID` as the immediate assigning parent. Never default a native child to a fresh root or treat native session IDs as Runtime Job IDs. Pass verified `--root` and `--parent` explicitly; transport labels are not authentication, admission or additional budget. Decide a new stable child run ID once and keep it for the entire operation. Use remote cwd `~` unless an actual remote workspace is bound to the task; a Mac `$PWD` is not a Linux path. Check that exact ID before first submission. If it already exists, inspect/reconcile; never replay over it.

Classify the bounded child independently: `C0_MECHANICAL`, `C1_ROUTINE_BOUNDED`, or `C2_COMPLEX_BOUNDED` as appropriate; use `C3_FRONTIER_JUDGMENT` only with a specific frontier reason. Common `--class` values include `mechanical`, `fix_build`, `review`, `census`, and `audit`. Let the incumbent router pick qualified provider and host; don't force Sol, an unqualified provider, or a host. Specify review independence when applicable.

```sh
# Substitute the verified original root, actual assigning parent, unique child ID and task class.
# At the top level only, VERIFIED_ASSIGNING_PARENT_ID equals VERIFIED_ROOT_ID.
python3 "$FABRIC_ADAPTER" status "$CHILD_RUN_ID"
python3 "$FABRIC_ADAPTER" request --id "$CHILD_RUN_ID" --class mechanical   --task-complexity C0_MECHANICAL --cwd '~' --root "$VERIFIED_ROOT_ID" --parent "$VERIFIED_ASSIGNING_PARENT_ID" --stdin <<'WORK_PACKET'
OBJECTIVE: one bounded task with named source/input and authorized scope
CONSTRAINTS: no secrets; preserve others' edits, active workers and existing authority
ACCEPTANCE: precise checkable result and evidence; return compact finding/artifact reference
WORK_PACKET
```

After a dispatched request, inspect **only the same stable ID**. `status` and bounded `wait` expose state; `result` returns retained content only when `result_available=true`. Assess test/evidence quality, arrange independent review if required, then use `accept "$CHILD_RUN_ID" --by deterministic` only after deterministic verification, or `--by reviewer` after actual authorized review. A successful exit/`DONE` is **not** automatically acceptance. Current legacy acceptance does not cryptographically attest the bytes originally reviewed.


## Generated files and automatic return

For a generated-file task, add one `--artifact-output <relative-name>` per required file to the new request. Supply source/input in the packet; cwd `~` is not an invitation to edit an unrelated project. The adapter creates the per-run artifact location and supplies the manifest contract to the worker. State the desired task and output; let the router choose an admitted artifact-capable provider and Linux host. Qwen is currently supported, but availability and selection remain routing decisions.

After successful completion, consume and hash the exact retained stdout. Use the adapter's `artifacts` command with the same run, root and parent, the selected host from retained controller evidence, the exact stdout digest, each manifest-advertised absolute `--path`, and a new permitted local `--destination`. Example shape:

```sh
python3 "$FABRIC_ADAPTER" artifacts "$CHILD_RUN_ID" --root "$VERIFIED_ROOT_ID" --parent "$VERIFIED_ASSIGNING_PARENT_ID" --host "$RETAINED_HOST" --stdout-sha256 "$RETAINED_STDOUT_SHA256" --path "$MANIFEST_ARTIFACT_PATH" --destination "$NEW_LOCAL_DESTINATION"
```

Inspect the export receipt and actual bytes; verify the task's promised behavior before acceptance. Save the reviewed stdout/artifact hashes with the parent's adjudication. A receipt or successful exit alone is not validation. Deterministic acceptance means the parent verified objective checks; reviewer acceptance means an actual review was adjudicated, including any required corrections.

For Codex only, new requests may opt into `--native-return` after the user has reviewed/trusted the installed general Stop hook. It binds the actual current native thread to both root and parent and registers before dispatch. This delivers retained results at an active Stop boundary; it does not wake an idle chat. Ordinary requests remain usable without the hook. Never apply this flag to retroactively adopt a retained operation, and do not assume another provider's harness supports Codex hooks.

Do not retry `RUN_EXISTS`, `ACTIVE_OR_WAITING`, `EFFECT_UNKNOWN`, or undelivered results through another ID/host. Don't kill the existing carrier to simulate cancellation. Reconcile uncertain original effects with their actual owner. If this adapter has a real admission, host or permission blocker, continue direct permitted work or report the exact blocker: do **not** silently spawn native Sol workers for routine labor.

For a nested operator, retain the original verified root and use the actual operator run as the immediate parent of its child; do not mint a new root from the nested session. Use the active parent-specific law before producing artifacts or acting on another worktree. The installed global `~/.codex/AGENTS.md` and current protected Mastermind procedures remain controlling.

## Paid operators may delegate bounded leaves

A Grok operator -> separately leased worker -> same Grok operator active Stop return -> original Codex parent has now completed on Ubuntu1/Ubuntu2 and both levels were reviewed and accepted. Evidence: `/Volumes/Mastermind/evidence/fabric-reliability-codex-20261008/recovery-engineering/operator-hook-retention-20261012/GROK_OPERATOR_LIVE_PROOF.json`. The timed Grok priority selected both levels; this is not live GLM Flash/MiniMax proof. GLM operator delegation works, but its active Stop continuation remains separately unproven. No idle Wake or recursive operator claim.

Use an operator when its execution, judgment or coordination saves work. It may complete its assignment itself without manufacturing a child; a child allowance is a ceiling, not a delegation target. Routine single leaves keep using the ordinary adapter. A CEO or native coordinator may assign either route directly within its actual grant. A native coordinator retains its verified original root and uses its own native identity as the immediate parent, without treating native IDs as Runtime Jobs or transport labels as authentication. A local assigned principal may issue one bounded original-root child allowance through the installed `fabric_operator_issue.py authorize-root --root <verified-root> --child-limit <bounded-count> --ttl 7200`. Verify the actual native root first. This is an immutable, once-issued allowance: do not renew/reset an existing one, substitute a root, or treat a refusal as permission to retry. Ordinary leaves do not need it. The original root allowance and per-run operator grant must have enough remaining time for child admission; a 600-second child currently requires 660 seconds of headroom.

For a self-executing operator assignment, leave `POOL_OPERATOR_CHILD_BUDGET` unset or `0`. Use the same adapter with `--class domain_orchestration`, its required `--task-complexity C3_FRONTIER_JUDGMENT`, a concrete `--escalation-reason`, and the verified root/immediate parent. Let normal routing select an eligible provider and host. This route receives no child-launch capability or child-return hook. When bounded child delegation is useful and an eligible original-root allowance exists, explicitly opt in with `POOL_OPERATOR_CHILD_BUDGET=1`. Keep a stable new run ID and a bounded packet. For that opt-in, the controller binds the private capability to the actual lease/account/host/model/support/packet and installs per-run instructions and active Stop integration. Never manually issue/copy capability tokens, reuse the operator lease for a child, or compose remote launch commands. This is direct shell Fabric and does not wait for Executive OS.

Inside an operator with an admitted delegation capsule, discover `mastermindStudio` tools: `fabric_operator_scope`, `fabric_child_request`, `fabric_child_status`, `fabric_child_wait`, `fabric_child_result`, and `fabric_child_acknowledge`. Preserve the original root and use the operator run as the child's immediate parent. Child work is C0/C1, separately leased, and canonical routing selects its provider/account/Ubuntu host. Children cannot become operators or delegate recursively. Normal economical child routing applies; no Grok quota-use override is active. Consume and review exact retained bytes, then acknowledge their SHA to close return attention. Acknowledgment is not ledger acceptance; the original principal separately adjudicates and accepts through the existing adapter. Do not manually invoke the hook or claim continuation from installed files alone.

## Codex operator discovery: launch -> child -> original parent

The M2 Codex principal already uses this single skill. **Do not create a
competing `mastermind-codex-fabric-delegation` skill, a second dispatcher,
or another root.** At startup, load this skill using the existing global
`~/.codex/AGENTS.md` entrypoint. Verify the current authorized native
`CODEX_THREAD_ID` root and any parent commission before using the adapter.
A native Codex `spawn_agent` child is *not* a paid Fabric child, and a
Fabric-spawned **ordinary Codex leaf** has **no** recursive delegation grant.

For a qualified coordinator/operator, use **only** a controller-issued
original-root allowance and a separately admitted Fabric
`domain_orchestration` operator run with `POOL_OPERATOR_CHILD_BUDGET` explicitly
granted. The incumbent `fabric_operator_client.py` currently accepts
GLM 5.3 / Grok 4.6 for that scoped child path. The name "Codex operator"
or the mere existence of this skill **does not** make a Fabric-spawned Codex
model an admitted child-delegating operator; Grok 4.7 is likewise not
admitted through the existing exact model-binding path. Do not weaken
those model or lease checks to claim parity.

When the admitted operator actually exposes `mastermindStudio`:
1. Call `fabric_operator_scope` with `{}`. Require the exact returned
   `root`, `operator_run`, positive `child_budget_remaining` and an
   unexpired grant; installed tool names alone are not permission.
2. Call `fabric_child_request` **once** with this shape, replacing
   placeholders with the actual admitted scope and self-contained bounded task:

```json
{
  "schema": "mastermind.fabric_operator_child_request.v1",
  "root": "<scope.root>",
  "parent": "<scope.operator_run>",
  "run_id": "<new-unique-stable-child-id>",
  "task_class": "mechanical",
  "task_complexity": "C0_MECHANICAL",
  "packet": "<objective; allowed files/source; acceptance check; return limit>"
}
```

3. Use the **same** child ID with `fabric_child_status` or bounded
   `fabric_child_wait` and then `fabric_child_result`. Verify the retained
   work, use `fabric_child_acknowledge` with the **exact result SHA256**,
   and return findings plus that digest to the assigning principal.
   Acknowledgment is not ledger acceptance; the principal retains
   acceptance through the existing Fabric adapter.
4. A lost or ambiguous request is **not** repeatable. No new child ID,
   new provider route, direct shell/SSH fallback, manual lease release,
   or copied bearer capability. Missing `fabric_operator_scope` means
   no child admission; do the permitted direct work and report the gap.

The Codex host installer is **skill-only**: it preserves the original
global Codex instructions, user hooks, MCP registrations, native-subagent
limit and model settings. Installation and static tool names are not
fresh Codex startup/load proof or an admitted two-level runtime canary.
