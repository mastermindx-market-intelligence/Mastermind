# Fleet CI slot pool (load-aware, ephemeral, hybrid-routed)

Status: **source only, default off.** Nothing here changes a host, a runner, a GitHub
setting or a workflow. `CI_FLEET_MODE` unset (or `off`) keeps every job on
GitHub-hosted `ubuntu-24.04`.

Goal: move CI of the three repositories (macro, Mastermind, mastermind-terminal) from
GitHub-hosted runners onto our Linux fleet (Ubuntu 24.04 x64, 24–32 cores, 30–62 GB,
shared with other services) without overloading hosts that also run other work.

## Architecture

```
GitHub queue ──dispatch──▶ registered one-job JIT runners (only on hosts with headroom)
                                  ▲
 per host: fleet-slot@1..K ── ADMIT ─▶ MINT ─▶ RUN one job ─▶ WIPE ─┐
                                  └───────────── refused: back off ◀┘
 workflow: fleet-route action ── fleet-capacity (idle per class) ──▶ runs-on
```

* **Pull-based load balancing, no central scheduler.** Each slot registers a runner
  only after its host passes the admission gates. GitHub can dispatch only to
  registered runners, so a busy host stops offering capacity by itself.
* **Admission gates** (`ops/fleet_ci/fleet_gate.py`) reuse the Fabric host placer's
  semantics (`ops/native_fabric/quota_continuity/source/host_pick.py`,
  `evaluate_hosts`): copied number coercion, PSI ceilings valid only within 1..100,
  a reading at or above a ceiling refuses, memory at or above the floor passes, and
  any missing observation fails closed. Gates for one more runner:
  * memory PSI `some avg10` < `MEM_PSI_MAX`, io PSI `some avg10` < `IO_PSI_MAX`;
  * `MemAvailable` ≥ `SLOT_MEM_FLOOR_GB × (busy slots + 1)`;
  * `load1 / cores` < `LOAD_MAX`;
  * the observation is fresh (taken in the same call).
  Busy slots are slots in `claimed`, `minting` or `registered` (an idle registration
  is reserved capacity) plus any unreadable status file. The check and the `claimed`
  write happen under one host lock, so two slots cannot claim the same headroom.
  Refused: back off 15 s → 30 s → 60 s, no registration. CPU PSI is recorded in the
  status detail but is not a gate (host_pick has no CPU PSI gate; load1/cores covers
  CPU saturation).
* **One job per registration** (JIT config), run as `ghrunner-N` in the slot's
  `job` child cgroup, with private HOME (`/home/ghrunner-N`), `TMPDIR`
  (`/home/ghrunner-N/tmp`), PrivateTmp/PrivateIPC, hidden procfs, and a per-slot
  port range `FLEET_PORT_BASE=20000+N*100` (`FLEET_PORT_COUNT=100`). Jobs that bind
  fixed ports must move to this range before they run on the fleet.
* **Wipe after every job:** kill the job cgroup, purge cron/at, remove IPC, scratch
  files, HOME and the runner tree, then re-extract the runner.
* **Slot status:** every state change atomically rewrites
  `/run/fleet-ci/slot-N.json` (schema `mastermind.fleet_slot_status.v1`: slot, class,
  state, ts, port_base, detail with gate results). States: `starting`, `wiping`,
  `claimed`, `refused`, `minting`, `registered`, `exited`, `stopped`. T3 and operators
  read it; it never holds a secret.
* **Hybrid route:** `.github/actions/fleet-route` returns `runs-on` JSON.
  `off` → `"ubuntu-24.04"`; `fleet-only` → `["self-hosted","Linux","X64","fleet","fleet-<class>"]`;
  `hybrid` → fleet when idle slots of the class ≥ `jobs_needed`, or ≥ 1 and
  `idle/jobs_needed ≥ spill_ratio` (`spill_ratio` < 1 enables partial spill; default
  1.0), else hosted.

### Security rules (carried over from the Terminal e2e lane)

Source of these rules: mastermind-terminal `docs/CI_TERMINAL_E2E_SELFHOSTED_LANE.md`.

* The JIT config travels only in `ACTIONS_RUNNER_INPUT_JITCONFIG` into an
  `exec setpriv --reuid/--regid/--init-groups run.sh`; never argv, never echoed or
  logged; the handoff subshell drops every inherited variable and function first.
* The org minting credential is `/etc/fleet-ci/mint/token`, root-owned, readable
  only by the dedicated `fleetmint` user, which runs `fleet-mint` and prints only the
  encoded JIT config. A same-name 409 deletes only a provably stale registration.
* An uncertain registration (mint refusal other than API/network, a runner exiting
  nonzero within 30 s) writes `/var/lib/fleet-ci/hold-N` and stops the slot; the
  slot refuses to start until an operator reconciles and removes the hold. Unlike the
  Terminal lane the unit uses `Restart=always` (with `StartLimitBurst`), so ordinary
  exits come back but uncertain ones do not re-mint.
* Slot users have no login shell, no sudo, no supplementary groups (so no `docker`
  group; see open questions), no linger, and are listed in `cron.deny`/`at.deny`.

### Routing token choice

Listing org runners needs org-level "Self-hosted runners: read"; the workflow
`GITHUB_TOKEN` cannot read it. The router therefore takes a separate **read-only**
fine-grained token as secret `FLEET_ROUTE_TOKEN` (and group id as variable
`CI_FLEET_RUNNER_GROUP_ID`). Missing token, API error or malformed answer → hosted.
A public-safe status artifact was considered and not chosen: it would need a writer
with the same token plus a publication path, and it adds staleness. Fork PRs get no
secrets and therefore always route hosted in hybrid mode.

## Sizing

`slots_for_host() = min(cores // 4, (MemTotal_GB − RESERVE_GB) // SLOT_MEM_GB)`.
Examples (reserve 8, slot 8): 24 cores/30 GB → 2; 32 cores/62 GB → 6. `SLOTS=auto`
uses the rule; a number is capped at it. `fleet_gate.py slots` prints the result.
Per-slot `MemoryHigh`/`MemoryMax`/`CPUQuota` come from `fleet.conf`
(`fleet_gate.py render-limits` → `fleet-slot@.service.d/limits.conf`);
`fleet_ci.slice` caps the whole pool below MemTotal − reserve.

## Provisioning (per host, operator-run; not automated here)

1. Prerequisites: cgroup v2, kernel ≥ 5.14, systemd ≥ 249, util-linux `setpriv`,
   `/proc` mounted `hidepid=invisible` inside the unit (ProtectProc).
2. Bake list (placeholder, final list comes from a job inventory of the three repos):
   * `/opt/hostedtoolcache`: Python 3.11, 3.12, 3.13; Node 20, 22 (layout compatible
     with `actions/setup-python` / `setup-node`; see the toolcache RUNPATH note in the
     fleet runner docs);
   * Playwright browsers and system deps; Docker engine; PostgreSQL 16; `gh`; `jq`;
     build-essential, git, git-lfs, curl, unzip, zstd.
3. Accounts: `fleetmint` (system, nologin); `ghrunner-1..K` (nologin, private group,
   in `/etc/cron.deny` and `/etc/at.deny`, denied in sshd).
4. Files: `fleet-slot` → `/usr/local/sbin/`, `fleet-mint` → `/usr/local/bin/`,
   `fleet_gate.py` → `/usr/local/lib/fleet-ci/`, units → `/etc/systemd/system/`,
   `/etc/fleet-ci/fleet.conf` from `fleet.conf.example`, runner tarball (pinned
   version + SHA-256) → `/opt/actions-runner/actions-runner-linux-x64.tar.gz`.
5. Credential: install `/etc/fleet-ci/mint/token` (root:fleetmint 0440, directory
   0750) out of band; never in this repo, a log or a chat.
6. GitHub (separate, human-approved): an org runner group `<fleet-group>` limited to
   the three repositories; fine-grained read-only token for `FLEET_ROUTE_TOKEN`.
7. Enable `fleet-slot@1..K` where K = `fleet_gate.py slots`.

Host names, IPs and user names of the real fleet stay out of this public repository;
`<host-a>`, `<fleet-group>` are placeholders.

## Canary plan

1. One host `<host-a>`, `SLOTS=1`, class `std`; `CI_FLEET_MODE` stays `off`.
   Verify `slot-1.json` cycles `wiping → claimed → minting → registered` and refuses
   under synthetic memory/io pressure (e.g. `stress-ng`) without registering.
2. One non-required workflow in one repository pinned to `fleet-only` via a
   workflow-level override; compare duration and failures with the hosted run.
3. Repository variable `CI_FLEET_MODE=hybrid` in one repository with spill ratio 1.0;
   watch hosted fallback counts and queue time for a week.
4. Add hosts and the `heavy` class; then the other repositories; `fleet-only` only
   after hosted fallback is consistently zero.

## Rollback

Set `CI_FLEET_MODE=off` (or delete it): every routed job returns to `ubuntu-24.04`
on the next run. Then `systemctl disable --now 'fleet-slot@*'` on hosts; registered
idle JIT runners disappear when their slot stops or can be removed in the org UI.

## Open questions

* Docker jobs: the slot users have no supplementary groups, so no docker socket.
  Options: rootless docker per slot, or a `heavy` class with a reviewed exception.
* Fixed-port tests in the three repositories must adopt `FLEET_PORT_BASE`.
* Org policy for public repositories on self-hosted runners must be reviewed before
  routing fork PRs (they route hosted today because they get no secrets).
