# Installed Paperclip fleet baseline

**Configuration verified; real task completion is still being qualified.** This directory records
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
| Session context | `persistSession=false`, `quiet=true` on all 13; nonsecret current-run identity uses native Hermes passthrough |
| Memory | Existing `omh` in all 13 profiles; no new memory backend |
| Same-profile concurrency | `maxConcurrentRuns=1`; existing timer heartbeats remain disabled |
| Recovery | Existing hourly database backups, 30-day retention; fresh backup before cutover |
| Experimental flags | Beta skills false; explicitly approved isolated-workspace flag true; other flags preserved |

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

`paperclip_readiness.py` is scoped to this exact company, roster, installed version and
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
python3 ops/paperclip_fleet/paperclip_readiness.py
python3 ops/paperclip_fleet/paperclip_readiness.py --agent Product
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
python3 -m unittest discover -s tests -p test_paperclip_readiness.py -v
```

Ten tests passed during this operation. They cover native snapshot/link
integrity, conflicting-path and later operator-instruction preservation, version/company identity, no secret
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
directory. Existing hourly/30-day policy was preserved. At 04:47:42 UTC the exact
archive passed complete gzip reading and native restoration into a newly created
empty sibling database on an isolated temporary cluster: 301 public tables,
373 applied/journal migrations, zero pending migrations, zero invalid indexes
and zero unvalidated constraints. All thirteen current agent identities and the
existing company matched. One retained terminated agent is excluded by native
list semantics. Temporary process, listener and directory were reclaimed;
production health/listeners and the original archive hash were unchanged.

This is database-only recovery proof. The local encrypted-secrets provider also
requires the same `secrets/master.key`, and local objects live in `data/storage`.
Both paths are included by the existing Time Machine configuration, but no
completed backup covering them is available. The configured volume UUID
`F9E6A707-17C6-40E6-A83D-42519F1D1A1D` is absent from connected disk inventory;
its exact native lookup reports `Could not find disk`. Automatic Time Machine
backups are disabled. Existing Hermes/Executive backup owners do not establish
Paperclip file/key coverage. Recover the existing destination, or resolve a
replacement through the existing backup owner, before claiming file/key restore.
No key contents were read or copied during this diagnosis.

Host AC sleep was already disabled and automatic restart after power loss was
already enabled. Those power settings were inspected, not changed. The service
is a user LaunchAgent in `gui/501`. FileVault is on and no automatic-login user
is configured; availability therefore follows the existing unlock/login path.
Cold boot/login and physical-power-loss recovery have not been tested. No login,
encryption or service-scope settings were changed.

Useful existing surfaces:

- local dashboard: http://127.0.0.1:3100/MAS/agents
- health: http://127.0.0.1:3100/api/health
- native service definition:
  `~/Library/LaunchAgents/ing.paperclip.paperclipai.plist`

## Original consumer test and continuation

Preserve **MAS-2**, issue `4f8769dc-1c3f-41f7-bdec-08f137f551ef`, assigned to
Product. The original native skill-link mismatch was reconciled only for this
operation's four links after complete inventory equivalence. Early runs then
failed before prompt delivery on gateway timeout and workspace classification.

The Chairman subsequently approved the instance-wide isolated-workspace setting
and continuation. The supported API enabled it and saved the original task's
explicit `project_primary` strategy. That approval boundary is resolved.

A single native retry request
`22a758a5-58e7-4dc7-a710-bbe626dba021` led, through Paperclip's native retry
lifecycle, to run `c54dc873-bb58-465e-801b-98c352cf9e5b`. It reached real
glm-5.3 execution, `skill_view` and terminal. Nonsecret run/task identity was
present; temporary API/runtime-tool credentials were absent. Paperclip rejected
the empty-bearer request before effect. Model output and memory-recall logs do
not establish the required Fabric receipt or OMH marker.

The run was cancelled once through its native endpoint at
`2026-11-10T03:13:11.936Z`; the Hermes admission and session are terminal.
No canary remains running. Do not retry until the required credential
capability is installed and read back.

## Credential integration

[HERMES_GATEWAY_INTEGRATION.md](HERMES_GATEWAY_INTEGRATION.md) describes the
implemented source candidate in
[integrations/paperclip_hermes](../../integrations/paperclip_hermes/README.md).
It extends existing local launch custody, plugin registration and finite
admission. The Paperclip declaration stays at the plugin edge. It introduces
no static run keys, daemon credential environment, provider account, memory
backend or lifecycle queue.

The first release supports local/in-process finite execution and refuses
unsupported managed/remote/background/delegated credential scope. Base-source
qualification is superseded by 128 passing native tests on the exact installed
source composition, preserving 85 existing changed/new source files and generated
contract inputs. Six edge-contract and ten readiness fixtures pass separately.
The full native source check still fails on the same 3 footgun and 13 Ruff
findings as the installed baseline; the other 12 checks pass. Test success is
not live activation, and known release holds remain binding.

The plugin matches the producer's 48-hour API JWT and independently expiring
one-hour runtime-tools token. It excludes the persistent agent-identity private
key from launch payload and child environments; identity signing is not provided.

The current gateway identity and work inventory must be read from native
lifecycle control. The 04:58:56 UTC observation found nineteen active work units:
nine chats, four in-process crons and six managed units. All four crons were
restart-unsafe and not wedged. The earlier CEO execution completed/delivered at
04:58:19 UTC; do not replay it. Native restart waiting is not proof that current
work has settled. No source overwrite, drain or
Hermes restart has been performed by this operation. Preserve that work and use
the incumbent guarded lifecycle when the concrete finite cutover is ready.

After activation, require capability and enabled-plugin readback before adding
the nonsecret required-binding marker to the native Paperclip adapter. Complete
the original authenticated same-issue return, runtime-tool call, actual Fabric
route/accounting and OMH write/read proof, followed by a second run/profile and
leadership skill materialization.

## Source and evidence

- Baseline PR #2399 merged at
  `dee7a38a1e184e38cdcdd75889223d5b0ec27414` through native protected controls.
- The exact merged operational helper was installed and hash-verified; the
  follow-up source makes the already applied quiet=true repair reproducible.
  The fleet application was not rerun.
- [Original configuration evidence](evidence/2026-11-10-configuration-qualification.json)
  remains a historical snapshot.
- [Credential qualification evidence](evidence/2026-11-10-credential-qualification.json)
  records exact source/check results and runtime activation limits.
- [Credential implementation and qualification](../../integrations/paperclip_hermes/README.md)
  records source scope, checks and remaining acceptance.
- [Canonical operation plan](../../docs/superpowers/plans/2026-11-09-paperclip-fleet-readiness.md)
  records the current task tree and reconciled effects.

Full fleet readiness remains open until the actual consumer outcomes are proven.
