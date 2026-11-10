# Installed Paperclip fleet baseline

**Configuration verified; end-to-end readiness is held.** This directory records
the existing MastermindX Paperclip company and its 13 Hermes agents on the M2
host. It is a one-shot integration baseline, not a second fleet manager.

The current acceptance target remains: an assigned Paperclip task reaches the
correct existing Hermes profile through Capacity Fabric, uses actual tools and
OMH continuity, and returns a durable result to its originating issue. That
complete path has **not yet passed**.

## Installed and verified

| Surface | Observed state |
| --- | --- |
| Paperclip | Official `2026.1106.0`, source `d69631b01b9c658f80bf8bed389863dce82643e1` |
| Instance | `default`, loopback `127.0.0.1:3100`, `local_trusted` |
| Company | MastermindX, `a5f907fc-c4b1-478c-a1b1-1748d32206dd`, 13 existing `hermes_local` agents |
| Service | Native launchd `ing.paperclip.paperclipai`; enabled, RunAtLoad and KeepAlive |
| Managed CLI | Version-pinned payload under `~/.paperclip/cli/installs/npm/2026.1106.0`; `~/.paperclip/cli/current` selects it |
| Instructions | Managed role-aware AGENTS verified for all 13; original profile SOUL remains role owner |
| Model provider | Existing `capacity-fabric` retained in all profiles; adapter provider `auto` leaves selection to Hermes |
| Adapter model | Explicitly mirrors each existing profile: Engineering `claude-fable-5.1`, Marketing `deepseek-v4.1-flash-uncensored`, other 11 `glm-5.3` |
| Adapter executable | Absolute `/Users/chriswong/.local/bin/hermes`, independent of launchd PATH |
| Session context | `persistSession=false`; nonsecret current-run identity enabled through the native Hermes passthrough |
| Memory | Existing `omh` in all 13 profiles; no new memory backend |
| Same-profile concurrency | `maxConcurrentRuns=1`; existing timer heartbeats remain disabled |
| Recovery | Existing hourly database backups, 30-day retention; fresh backup before cutover |
| Experimental flags | Beta skills and isolated-workspace flags remain false |

The managed instructions require the existing Paperclip skill and current
Mastermind source law, preserve live writers and task ownership, and return
evidence to the same issue. Missing run credentials fail closed; they never
authorize unauthenticated board access. External messages, agent hiring and
financial actions retain their actual task authorization.

Existing Hermes tools, native skills and MCP integrations were reused. The final
audit reports 52–69 native skill source entries per profile. These counts and
configured MCP names are inventory evidence, not proof that each tool has been
successfully invoked by Paperclip.

## Skills and plugins

The core `paperclip` skill is materialized and verified in all 13 profiles.
The planning skill is ready in the eight relevant coordinator/planning profiles.
The existing leadership selections `paperclip-board` and
`paperclip-create-agent` each remain pending native materialization for the
three CEOs (six agent/skill entries). The native first-run path owns that step.

The bundled `complain` and `suggestion-box` files remain part of the adapter's
native skill contract, but Hermes' own disabled-skill filter disables them.
No unsolicited external feedback was sent. `para-memory-files` was removed
from Paperclip selections to preserve the existing OMH continuity owner.

No arbitrary marketplace plugin, duplicate scheduler, direct provider key,
profile-wide credential relay or additional memory system was installed.
Existing Paper, browser, Executive and Fabric integrations retain their existing
owners and controls.

## One-shot installer

`readiness.py` is scoped to this exact company, roster, installed version and
local-trusted access mode. It:

- verifies each agent's existing Hermes profile, role file, Capacity Fabric and OMH;
- uses the Paperclip instruction revision API with a base hash;
- preserves unrelated adapter/runtime settings and checks saved values;
- requires an idle/error agent and settled Paperclip runs before applying;
- attests native immutable skill inventories and creates only absent links;
- refuses conflicting files, directories and symlinks without overwriting them;
- leaves missing native snapshots to the supported first-run materializer;
- uses Hermes' key-level configuration writer for the two owned profile settings;
- never retries mutations or enables experimental flags.

Use a host Python environment with the existing PyYAML dependency available.
Run a read-only check before any deliberately authorized application:

```bash
python3 ops/paperclip_fleet/readiness.py
python3 ops/paperclip_fleet/readiness.py --agent Product
```

`--apply` mutates the already-identified instance/profile configuration. It is
not a release, a task retry, a memory migration or a gateway restart. Preserve the
one original mutation carrier and reconcile its actual target after a lost
response; do not blindly rerun an interrupted apply.

The operational copy is
`/Users/chriswong/.paperclip/instances/default/readiness.py`.
The source was applied successfully to all 13 agents and read back after the
managed-service restart. Re-running an unchanged successful installation is
unnecessary.

Focused fixture tests (no service calls or model spend):

```bash
python3 -m unittest discover -s ops/paperclip_fleet -p test_readiness.py -v
```

Nine tests passed during this operation. They cover native snapshot/link
integrity, conflicting-path preservation, version/company identity, no secret
passthrough, feature-gate behavior and native materialization deferral.

## Native service and recovery proof

After zero active Paperclip runs and an exact process/listener check, the old
manual onboarding server was stopped once. The installed native launchd service
then started the same instance and database.

A native managed restart subsequently changed PID 55585 to 82322. Its canonical
report records:

- requested: `2026-11-10T02:21:00.827Z`;
- completed: `2026-11-10T02:22:40.519Z`;
- same Paperclip version before/after;
- no lost, adopted, skipped or finalized-while-down runs;
- healthy/auth-ready/bootstrap-ready API and preserved 13-agent configuration.

**The CLI wait timed out and returned exit 1 after about 69 seconds, while the
actual server recovered after about 100 seconds.** This is a known startup/wait
limitation, not evidence that another restart is needed. Reconcile native status,
the restart report and actual health before any retry.

The fresh pre-cutover database backup was
`paperclip-20261109-181411.sql.gz` (365,501 bytes) under the instance backup
directory. Existing hourly/30-day policy was preserved. Restore into a separate
test instance was not exercised; do not claim disaster-recovery proof.

Host AC sleep was already disabled and automatic restart after power loss was
already enabled. Those power settings were inspected, not changed. The service
is a user LaunchAgent; cold boot/login and physical-power-loss recovery have not
been tested.

Useful existing surfaces:

- local dashboard: http://127.0.0.1:3100/MAS/agents
- health: http://127.0.0.1:3100/api/health
- native service definition:
  `~/Library/LaunchAgents/ing.paperclip.paperclipai.plist`

## Original consumer test and exact hold

Preserve **MAS-2**, issue `4f8769dc-1c3f-41f7-bdec-08f137f551ef`, assigned to
Product. Do not create a replacement task or discard its private workspace.

The initial native skill-sync/runtime mismatch was reconciled only for the four
links owned by this operation, after preimage and full-inventory equivalence.
Run `5c5905a4-f2d6-4a79-a2b6-753e50e6523a` then spawned Hermes, proving that
specific repair. It failed before model input with a gateway TimeoutError;
later read-only gateway attachment succeeded. Neither fact proves a model run.

The subsequent native retry
`75c70f6e-58f3-444b-ae24-00fef35bbbc9` failed workspace validation. Its private
non-Git attempt directory was inferred as a Git worktree. Current binding:

- workspace `d9acdda2-21f5-4ad3-a79e-718d4191be53`;
- binding revision `2`;
- preference `reuse_existing`;
- isolated-workspace mode retained;
- local environment `7addd6ae-551a-4193-977a-753501c54b77`.

A scoped fix to explicitly select `workspaceStrategy.type=project_primary`
was preflighted, not executed. This release strips those fields while the native
instance flag `enableIsolatedWorkspaces` is false.

**Automatic approval review rejected enabling that instance-wide experimental
flag**, because it affects future tasks and the shared fleet beyond this canary,
and it required explicit authorization for that scope. Readback remained false.
Do not retry through another surface, clear isolation, rehome the task or create
a duplicate canary to evade the decision. The exact next approval is permission
to enable that one instance-wide setting, then correct and qualify this same
original workspace/task.

## Remaining harness integration

[HERMES_GATEWAY_INTEGRATION.md](HERMES_GATEWAY_INTEGRATION.md) records the exact
credential/context compatibility findings and a design using Hermes' incumbent
private launch-secret custody. It is **not an implemented or deployed patch**.

The inspected checkout is newer than the running gateway. Existing generic
client-env filtering excludes the two Paperclip run secrets. No supported plugin
hook was found that closes this contract, and a static agent key cannot replace
the run JWT plus runtime-tool grant. Preserve the filter and original issuers.

After the original task's workspace is unblocked, qualify the actual gateway
revision and real path before composing any required patch with user-owned
source changes. Then require two distinct run identities, a Capacity Fabric
receipt, a real permitted tool call, OMH continuity and durable same-issue
return. Representative leadership/delegation, optional skill materialization
and recovery during active work remain acceptance steps.

## Evidence and ownership

- [Post-restart fleet audit](evidence/2026-11-10-configuration-qualification.json)
- [Mission and remaining task tree](../../docs/superpowers/plans/2026-11-09-paperclip-fleet-readiness.md)
- [Gateway compatibility design](HERMES_GATEWAY_INTEGRATION.md)

The audit intentionally contains only nonsecret inventory, hashes and bounded
runtime facts. No private memories or credentials are included. Mastermind
GitHub owns this evidence; Paperclip owns issue/run state; Hermes/OMH retain bot
continuity; Capacity Fabric retains inference admission, routing and accounting.
