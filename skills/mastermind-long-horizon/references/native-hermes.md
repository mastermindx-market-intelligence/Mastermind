# Hermes native continuity and always-on integration

This companion is a workflow and read-only context consumer, not a bot runtime, memory provider, admission grant, scheduler or profile migrator. Preserve current Executive/Capacity/Agent OS owners and the actual provider budget. The installed source API was qualified at `NousResearch/hermes-agent@ba4ddf9945a213ede9dda016602a86591ed634f9` plus the explicitly recorded native API byte fingerprint. The checkout has an unrelated local `provide_gateway_turn_context` hook declaration; it was preserved and included in the fingerprint, not misrepresented as pristine upstream. Qualify any changed runtime separately.

## Use the native facilities already present

Hermes already has `todo_list`, persistent goals, completion contracts, additive subgoals, quality gates, wait barriers, skills, profile-scoped memory and scheduled/event-driven facilities. The missing project layer is retention of the entire assigned outcome and evidence across those facilities, not a second implementation of them.

Read the current native todo list before adding or changing an item. Retain stable GitHub task IDs and original native references. One principal task is focused; a task blocked on recovery does not hide independent work. No direct edits to provider task files or session databases.

For an already permitted native goal, preserve its full parent outcome. The native completion contract can name outcome, verification, constraints, boundaries and stop conditions. `/subgoal` adds a criterion without replacing the original goal. Setting a new `/goal` replaces the old goal and clears its subgoals; `/goal draft` also starts the first turn, so it is not an inert preview. Pause, stop and clear remain controlling. A native goal turn counter reset is not a new organizational spend allowance.

Native `/goal gate` commands must be explicitly selected, safe and authorized for the task; never execute a shell string harvested from a plan, result or web page. A deterministic gate complements the judge, but passing a test does not establish whole-product acceptance. Use native original-process wait barriers when already authorized rather than repeated polling or an extra timer. ACP does not advertise the same goal controls as every other Hermes surface; discover the actual surface.

## Native plugin

Source: `integrations/session_bridge/hermes_project_plugin.py`, packaged without an implementation fork alongside the existing `project_task_context.py` and `long_horizon_guidance.py`.

The plugin contributes exactly four items through Hermes's existing registrations:

- A namespaced read-only skill, `mastermind-long-horizon:execute-project`.
- A bounded, stable habits section after native memory. It does not contain changing task status.
- A `pre_llm_call` context read for an explicitly bound native session.
- The read-only `mmx_project_context` tool. It accepts an empty object; the native dispatcher supplies session identity. The model cannot choose a profile, path, contract or another session through arguments.

Read `mmx_project_context` after a material task boundary and after compaction when current progress is needed. The same source-plan contract supports Claude/T3 startup and a `--format prompt` CLI projection; no duplicate task database exists.

The native profile's `plugins.entries.mastermind-long-horizon.settings.session_bindings` maps an inspected native session ID to exactly `workspace_root`, `plan_path`, `workstream`, and `plan_contract_sha256`. These are explicit setup inputs from the current assignment, not defaults to invent. Registration does not populate this mapping or enable an account. Unbound sessions receive no project context. Native profile scope, registration lifetime and the binding are rechecked after the read; revocation or an in-flight change withholds the old data.

Hermes may rotate a session ID during compression. The plugin uses the same profile's native **read-only** `SessionDB.get_compression_lineage` to recover an explicitly configured predecessor. It does not trust a message's parent ID, create an alias registry, or copy settings. Explicit forks, resets, delegated/tool children and other profiles do not inherit this binding. Conflicting ancestor bindings fail closed. Fresh native managers recover from the same persisted lineage after restart.

## Always-on habits

A wake is an opportunity to reassess assigned work, not authorization to start another agent. Recover the source plan, actual active run, outstanding returns and remaining budget. Verify the current dependency, do one useful action, then save and continue within the native permitted turn. If the original effect is uncertain, read it; if nothing actionable changed, do not spend turns repeatedly restating the same blocker.

Keep durable project decisions and evidence with their existing owner. Store a reusable technique as a skill only after a verified successful example; do not turn task-specific snippets into global habits. Use the original bot profile for its identity and memory. A different UI must not silently clone that profile, transfer credentials, or start a second heartbeat owner.

## Build and qualification

`scripts/build_hermes_long_horizon_plugin.py` assembles a new standalone directory from exact source bytes; it does not install, enable or mutate a Hermes profile. Native registration and adoption are separate steps, using the existing plugin installer after protected release and actual owner qualification.

`scripts/qualify_hermes_long_horizon.py` exercises real installed PluginContext/PluginManager/tool registrations and SessionDB compression against disposable profile state. Invoke it with the installed committed dependency-environment interpreter and an explicit inspected Hermes root/SHA and native-API SHA-256. Native files are rechecked after qualification; the receipt lists dirty paths as well as exact bytes. It refuses a bare store interpreter and disables lazy dependency installation only in its qualification process. Its PASS means installed native API compatibility, not a model run, live bot loading, scheduled delivery or product acceptance.

Production proof still requires the exact selected bot/profile/session consuming the skill and plan, continuing through real steering/compaction, preserving stop and original effects, and returning actual acceptance evidence. No script here declares that proof from fixtures.
