# Native integration and source contract

## Entrypoints

Canonical workflow: `skills/mastermind-long-horizon/SKILL.md`.
Native discoverable wrappers: `.claude/skills/mastermind-long-horizon/SKILL.md` and `.agents/skills/mastermind-long-horizon/SKILL.md`.
Repository `.claude/settings.json` opts into documented task tools using `CLAUDE_CODE_ENABLE_TODO_TOOLS=1`; it does not select a new model, authorize permissions, enable a disabled T3 provider or install a lifecycle hook.

The inspected T3 upstream is `pingdotgg/t3code@2b65ffb641f152fadf443096bad7f4a0677caae4`. Its Claude adapter already projects TaskCreate/TaskUpdate/TaskList and TodoWrite, loads project settings, and reconstructs goal state. ProviderContinuationService and RestartContinuation already own native continuation. The installed app observed as 0.1.7 is not proven identical to that upstream commit. Verify installed capabilities before relying on them.

## One GitHub plan, two binding modes

The existing Markdown file under `docs/plans/` contains exactly one fenced `mastermind-plan` JSON block. The authoritative schema and validators live in `integrations/session_bridge/project_task_context.py`; examples are in `tests/test_project_task_context.py`. Do not maintain another database or mutable copy.

Required root fields: schema `mastermind.project_task_tree.v1`, workstream, objective, requirements, allowed_paths, non_goals, tasks. Each requirement has stable id/text. Each task has id/title/requirement_ids/depends_on/acceptance/state/evidence. Acceptance has id/text. States pending/in_progress/blocked/done are editorial source claims, not Runtime states. Blocked tasks need a blocker. Optional execution_lane delegated plus native_ref preserves an original active child. Multiple principal in-progress tasks are rejected.

An evidence item identifies a criterion, the task definition SHA-256, a canonical ref, and result pass/fail/pending. A changed dependency or requirement invalidates affected task definitions. Link validation is syntactic only. Verify the actual receipt, code revision and criterion before using completion claims. The projection always reports execution_authority=false, mission_accepted=UNOBSERVED and evidence_authentication=NOT_PERFORMED.

An inspected initial source file can yield `contract_digest(parse_plan(raw))`. Retain that expected contract through routine task/status/evidence saves. The current raw source SHA is returned on every read. For a source snapshot that must be byte-identical, use `--plan-sha256` instead. Both modes reject ambiguous binding. A source-contract change is reviewed through `compare_plans`, not auto-approved.

From the assigned repository root, using actual assigned values:

```sh
python3 -m integrations.session_bridge.project_task_context \
  --workspace-root "$ASSIGNED_WORKSPACE" \
  --plan-path "$ASSIGNED_PLAN" \
  --plan-contract-sha256 "$INSPECTED_CONTRACT_SHA256" \
  --workstream "$ASSIGNED_WORKSTREAM"
```

The command is read-only and does not call T3, a provider, Executive or Agent OS. Paths are confined, bounded and no-symlink; malformed source fails with a typed reason. Large task trees need bounded source reads, not silent truncation or removal of requirements.

## Existing startup hook, explicit binding only

`integrations.session_bridge.agentos_session_start` retains its incumbent owner/charter logic and default behavior. It now accepts optional `--plan-path` and exactly one of `--plan-sha256` or `--plan-contract-sha256` alongside existing workspace/workstream binding. The same native SessionStart path can restore the full source mission on startup/resume/compact/clear/fork. This does not reactivate a cleared goal or grant execution.

Do not register a second SessionStart or Stop system. An existing authorized hook installer must bind the exact assigned workspace and contract, then prove the installed runtime consumed it. Unit/CLI fixtures prove module behavior, not actual model obedience or fleet rollout. No global hook activation is included in this change.

## Native goal/task limits

Task tools are provider/model/version dependent. On current documented Claude versions, newer models need the explicit TODO-tools opt-in; older models may include them by default. Do not broaden `--allowedTools`, permissions or sandbox modes just to display a checklist. Task lists can persist compaction and can be explicitly shared by ID; never give unrelated projects a single shared task-list ID.

A native goal is one active condition, not the whole project registry. Replacing it replaces that condition. Its evaluator is transcript-only, and some counters reset on resume. Budget, permission, user stop and existing Executive admission remain controlling. Read original effects after interruption. No wrapper should retry a denied provider launch or substitute another provider.

Primary references, checked 2026-11-09:
- https://code.claude.com/docs/en/tools-reference
- https://code.claude.com/docs/en/interactive-mode
- https://code.claude.com/docs/en/goal
- https://code.claude.com/docs/en/hooks
- https://code.claude.com/docs/en/skills
- https://developers.openai.com/codex/skills
- https://github.com/pingdotgg/t3code/tree/2b65ffb641f152fadf443096bad7f4a0677caae4
