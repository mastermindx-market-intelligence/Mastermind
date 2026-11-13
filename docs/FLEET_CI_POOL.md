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
 workflow: fleet-route action ── fleet-capacity (idle minus queued, per class) ──▶ runs-on
```

* **Pull-based load balancing, no central scheduler.** Each slot registers a runner
  only after its host passes the admission gates. GitHub can dispatch only to
  registered runners, so a busy host stops offering capacity by itself.
* **Admission gates** (`ops/fleet_ci/fleet_gate.py`). Gates for one more runner:
  * memory PSI `some avg10` < `MEM_PSI_MAX`, io PSI `some avg10` < `IO_PSI_MAX`;
  * `MemAvailable` ≥ `SLOT_MEM_FLOOR_GB × (busy slots + 1)`;
  * `load1 / cores` < `LOAD_MAX`.
  Busy slots are slots in `claimed`, `minting` or `registered` (an idle registration
  is reserved capacity) plus any unreadable status file. A `claimed` file older than
  `STALE_CLAIM_S` (default 21600 s = 6 h, the GitHub job timeout) no longer holds
  capacity — the slot died between admitting and minting — and is reported as
  `stale_claims` in the status/admit output; other busy states count regardless of age.
  The check and the `claimed` write happen under one host lock, so two slots cannot
  claim the same headroom. Refused: back off 15 s → 30 s → 60 s, no registration.
  CPU PSI is recorded in the status detail but is not a gate.
* **Honest comparison with `host_pick.evaluate_hosts`** (the Fabric host placer,
  `ops/native_fabric/quota_continuity/source/host_pick.py`):
  * **Same semantics:** the number coercion (`_as_float`/`_finite_nonnegative`), the
    pressure-policy validity (each PSI ceiling within 1..100 percent), "a reading at
    or above a PSI ceiling refuses", "available memory at or above the floor passes",
    and "a missing or unparsable observation fails closed". The pure helpers are
    copied (host_pick is not importable on fleet hosts); a parity test pins them.
  * **Different:** the fleet memory floor scales with busy slots (`× (busy + 1)`);
    host_pick uses a fixed per-host floor. The fleet load gate is **per-core**
    (`load1/cores < LOAD_MAX`); host_pick's load gate is absolute `load1 < load_gate`.
  * **No freshness gate.** host_pick's `fresh` gate is meaningful because it guards
    *stored* probe state (up to `max_age` old). The fleet observes live in the same
    call, so an age check here would be tautological; it was removed.
  * host_pick's roles/mode/window/reachable/disk/lane-ceiling gates have no fleet
    analogue: a fleet host is single-purpose and observed directly.
* **One job per registration** (JIT config), run as `ghrunner-N` (N in **1–32**, the
  same range in the slot script, the gate, the minter and the nft renderer) in the
  slot's `job` child cgroup, with private HOME (`/home/ghrunner-N`), `TMPDIR`
  (`/home/ghrunner-N/tmp`), PrivateTmp/PrivateIPC, hidden procfs, and a per-slot
  port range `FLEET_PORT_BASE=20000+N*100` (`FLEET_PORT_COUNT=100`). Jobs that bind
  fixed ports must move to this range before they run on the fleet.
* **Wipe after every job:** purge cron/at (and assert the crontab spool file is gone),
  kill the job cgroup, remove IPC, scratch files, HOME and the runner tree, verify the
  tarball SHA-256 against the `fleet.conf` pin, then re-extract the runner.
* **Slot status:** every state change atomically rewrites
  `/run/fleet-ci/slot-N.json` (schema `mastermind.fleet_slot_status.v1`: slot, class,
  state, ts, port_base, detail with gate results). States: `starting`, `wiping`,
  `claimed`, `refused`, `minting`, `registered`, `exited`, `stopped`. T3 and operators
  read it; it never holds a secret.
* **Hybrid route:** `.github/actions/fleet-route` returns `runs-on` JSON.
  `off` → `"ubuntu-24.04"`; `fleet-only` → `["self-hosted","Linux","X64","fleet","fleet-<class>"]`
  for a trusted source only; `hybrid` → fleet when idle slots of the class ≥
  `jobs_needed`, or ≥ 1 and `idle/jobs_needed ≥ spill_ratio` (`spill_ratio` < 1 enables
  partial spill; default 1.0), else hosted.

### Trusted-source guard (fork PRs never reach the fleet)

The action takes `is_trusted_source` and `repo_private`. The caller **must** compute
them in the workflow expression:

```yaml
- uses: mastermindx-market-intelligence/Mastermind/.github/actions/fleet-route@<sha>
  id: route
  with:
    mode: ${{ vars.CI_FLEET_MODE }}
    is_trusted_source: ${{ github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository }}
    repo_private: ${{ github.event.repository.private }}
    token: ${{ secrets.FLEET_ROUTE_TOKEN }}
    group_id: ${{ vars.CI_FLEET_RUNNER_GROUP_ID }}
```

Fleet labels are returned **only** when `is_trusted_source` is true — in every mode,
including `fleet-only`. A fork PR (head repo ≠ this repo) always routes hosted.
`repo_private` is recorded for observability; it is not the guard. Once the three
repositories are private there are no outside forks, so the fork exposure disappears;
until then the guard is binding. The default for both inputs is `false` (fail closed).

### The decision runs from the pinned ref, never from the caller's checkout

All decision logic is a single script, `fleet_route.py`, **inside the action
directory**, read through `github.action_path`. It runs the sibling `fleet-capacity`
from the same directory; only that pinned code reads `FLEET_ROUTE_TOKEN`. The two
scripts are byte-identical copies of `ops/fleet_ci/fleet_route.py` and
`ops/fleet_ci/fleet-capacity` (a parity test pins this); there is no reach-out into
`ops/fleet_ci` at runtime.

Callers **must** use the cross-repo form pinned to master or a SHA:
`uses: mastermindx-market-intelligence/Mastermind/.github/actions/fleet-route@<sha>`.
**Never** `uses: ./.github/actions/fleet-route`: a local action reference resolves
`github.action_path` inside the caller's checkout, so a fork PR could replace the
decision code (and exfiltrate the token) with PR-head code.

### Security rules (carried over from the Terminal e2e lane)

Source of these rules: mastermind-terminal `docs/CI_TERMINAL_E2E_SELFHOSTED_LANE.md`.

* The JIT config travels only in `ACTIONS_RUNNER_INPUT_JITCONFIG` into an
  `exec setpriv --reuid/--regid/--init-groups run.sh`; never argv, never echoed or
  logged; the handoff subshell drops every inherited variable and function first.
  This env-only handoff depends on `Runner.Listener` **unsetting the variable after
  reading it on the pinned runner version** — verify it as a canary checklist item
  (below); if a future version keeps it in the environment, the handoff must change.
* The org minting credential is `/etc/fleet-ci/mint/token`, root-owned, readable
  only by the dedicated `fleetmint` user, which runs `fleet-mint` and prints only the
  encoded JIT config. A same-name 409 deletes only a provably stale registration.
  The minter runs via `setpriv --reuid=fleetmint --regid=fleetmint --init-groups`,
  **not sudo**: the unit sets `NoNewPrivileges=yes` and `RestrictSUIDSGID=yes`, and
  sudo is setuid — it refuses to run under NoNewPrivileges. setpriv performs the uid
  change with plain syscalls as root, which NNP allows. For the same reason the
  slot's sudo-rights check inspects `/etc/sudoers` and `/etc/sudoers.d` directly:
  any mention of the slot user or its private group refuses; unreadable policy fails
  closed.
* Slot users have no login shell, no sudo, no supplementary groups (so no `docker`
  group; see open items), no linger, and are listed in `cron.deny`/`at.deny`.
  **cron/at allow files fail closed:** if `/etc/cron.allow` or `/etc/at.allow` exists
  and lists the slot user, the slot refuses to start (an allow file overrides the
  deny file, so an allow-listed user would get cron despite the deny entry).
* **Identity checks on every start:** the slot uid must not be shared with another
  account; the primary group must be private (same name as the user, no members, and
  no other account's primary gid); and `/run/user/$uid` must not exist before the job
  starts (checked again with the pre-mint session/process checks).
* **Runner tarball pin:** `fleet.conf` carries `RUNNER_TARBALL_SHA256`; the slot
  verifies the tarball's SHA-256 against it **before every extraction** and refuses
  to start when no valid pin is set. The example conf ships an all-zero placeholder
  that matches nothing. `RUNNER_GROUP_ID=0` is refused by the gate and the minter.

### Per-slot network isolation (nftables)

`fleet_gate.py render-nft [--slots K]` prints an idempotent nftables ruleset
(table `inet fleet_ci`, chain `egress`, hook `output`, policy `accept`) matched on
the slot uid (`meta skuid "ghrunner-N"`; nft resolves the names at load time, so
create the accounts first). Per slot:

* **Allow the internet** (chain policy accept for everything not denied below).
* **Deny** RFC1918/LAN (10/8, 172.16/12, 192.168/16), link-local (169.254/16),
  CGNAT (100.64/10), this-network (0/8), multicast (224/4) and reserved (240/4);
  IPv6 ULA (fc00::/7), link-local (fe80::/10), IPv4-mapped (::ffff:0:0/96) and
  multicast (ff00::/8).
* **Deny the host's loopback services** (127/8, ::1) **except** two destinations,
  both accepted *before* the loopback drop: the slot's **own port range**
  (`20000+N*100 .. +99`, tcp and udp), so a job can reach the servers it starts
  itself; and **DNS to the systemd-resolved stub `127.0.0.53:53` only** (udp and
  tcp), so name resolution keeps working. No other loopback service is reachable.

These rules filter egress packets; they do not prevent `bind()` — the observable
effect is that out-of-range loopback services and LAN destinations are unreachable.
Provisioning applies the ruleset with `nft -f`; the canary isolation harness verifies
the effect. The bake list therefore carries **no PostgreSQL and no Docker** (a
database or daemon reachable from a job would defeat the isolation); Docker for the
`heavy` class remains a documented open item, not implemented.

### Holds: uncertain registrations stop the unit

An uncertain registration (mint refusal other than API/network, a runner exiting
nonzero within 30 s) calls `hold()`: it writes `/var/lib/fleet-ci/hold-N` explicitly,
`sync`s, reads the file back and compares, then exits **78**. The unit uses
`Restart=on-failure` with `RestartPreventExitStatus=78`, so a hold never restarts.
When the primary marker could not be persisted, `hold()` still exits 78 and leaves
**two** fallback markers — a runtime one `/run/fleet-ci/hold-N` and a best-effort
persistent one `/var/lib/fleet-ci/hold-fallback-N` — and disables the unit. A failed
`systemctl disable` does not change the exit: the markers alone block startup (and a
reboot) until reconciled. The slot refuses to start while **any** of the three markers
exists. Ordinary failures exit 1 and come back after `RestartSec`.

**Hold-reconciliation runbook (operator):**

1. Read the hold: `cat /var/lib/fleet-ci/hold-N` (or the fallbacks
   `/run/fleet-ci/hold-N`, `/var/lib/fleet-ci/hold-fallback-N`).
2. List the registration: `GET /orgs/{org}/actions/runners?name=<name>` where
   `<name>` is `<host>-fleet-<class>-N` (from the hold message / slot status).
3. If the runner is **offline**, delete it: `DELETE /orgs/{org}/actions/runners/{id}`.
   If it is online/busy, or there are several same-name runners, stop and reconcile
   manually — do not delete a runner that may be executing a job.
4. Remove the hold file(s):
   `rm /var/lib/fleet-ci/hold-N /run/fleet-ci/hold-N /var/lib/fleet-ci/hold-fallback-N`.
5. If the unit was disabled by a persistence failure, `systemctl enable` it again.
6. `systemctl start fleet-slot@N` and watch `slot-N.json` cycle
   `wiping → claimed → minting → registered`.

### Routing token choice

Listing org runners needs org-level "Self-hosted runners: read"; the queued-job count
additionally needs "Actions: read" (queued workflow runs and their jobs). The workflow
`GITHUB_TOKEN` cannot read org runners. The router therefore takes a separate
**read-only** fine-grained token as secret `FLEET_ROUTE_TOKEN` (and group id as
variable `CI_FLEET_RUNNER_GROUP_ID`). Missing token, API error or malformed answer →
hosted. Fork PRs get no secrets and, by the trusted-source guard, never get fleet
labels in any mode.

### Capacity: idle minus queued (no over-commit)

`fleet-capacity` counts online idle one-job runners per class, then **subtracts the
queued jobs already targeting fleet labels** (status `queued`/`waiting`, labels
include `fleet` and `fleet-<class>`), clamped at 0. Several workflows routing at once
would otherwise all see the same idle registrations and over-commit the pool.
In-progress jobs are not counted again: their runner already reports `busy`.

The queued read is bounded: **one API page of 100** queued org workflow runs
(`GET /orgs/{org}/actions/runs?status=queued&per_page=100&page=1`), then one page of
jobs per run. Two bounds fail closed to hosted: if the runs page is **full (100)** the
queued count is **saturated** (more fleet jobs may be queued than one page shows); and
at most **20 job-detail API calls** are made per decision — more than 20 queued runs
hits the cap. In either case, or if **any** read fails, the whole result is `ok=false`
and the router falls back to hosted — never over-commit on a partial view. Output
schema `mastermind.fleet_capacity.v1` adds `queued_fleet_jobs` and a per-class `queued`
field; `idle`/`idle_slots` are the effective (post-subtraction) values.

## Sizing

`slots_for_host() = min(cores // 4, (MemTotal_GB − RESERVE_GB) // SLOT_MEM_GB)`,
capped at 32. Examples (reserve 8, slot 8): 24 cores/30 GB → 2; 32 cores/62 GB → 6.
`SLOTS=auto` uses the rule; a number is capped at it. `fleet_gate.py slots` prints
the result. Per-slot `MemoryHigh`/`MemoryMax`/`CPUQuota` come from `fleet.conf`
(`fleet_gate.py render-limits` → `fleet-slot@.service.d/limits.conf`);
`fleet_ci.slice` caps the whole pool below MemTotal − reserve.

## Provisioning (per host, operator-run; not automated here)

1. Prerequisites: cgroup v2, kernel ≥ 5.14, systemd ≥ 249, util-linux `setpriv`,
   nftables, `/proc` mounted `hidepid=invisible` inside the unit (ProtectProc).
2. Bake list (placeholder, final list comes from a job inventory of the three repos):
   * `/opt/hostedtoolcache`: Python 3.11, 3.12, 3.13; Node 20, 22 (layout compatible
     with `actions/setup-python` / `setup-node`; see the toolcache RUNPATH note in the
     fleet runner docs);
   * Playwright browsers and system deps; `gh`; `jq`; build-essential, git, git-lfs,
     curl, unzip, zstd. **No PostgreSQL, no Docker** (see network isolation above).
3. Accounts: `fleetmint` (system, nologin); `ghrunner-1..K` (nologin, private group,
   uid unique, in `/etc/cron.deny` and `/etc/at.deny`, never in `cron.allow`/`at.allow`,
   denied in sshd, never mentioned in sudoers).
4. Files: `fleet-slot` → `/usr/local/sbin/`, `fleet-mint` → `/usr/local/bin/`,
   `fleet_gate.py` → `/usr/local/lib/fleet-ci/`, units → `/etc/systemd/system/`,
   `/etc/fleet-ci/fleet.conf` from `fleet.conf.example` (set the real
   `RUNNER_GROUP_ID` and `RUNNER_TARBALL_SHA256`), runner tarball (pinned version,
   hash recorded in the conf) → `/opt/actions-runner/actions-runner-linux-x64.tar.gz`.
5. Network: `fleet_gate.py render-nft --slots K > /etc/nftables/fleet-ci.nft` and
   apply with `nft -f` (after the accounts exist); persist across reboot via the
   host's nftables service.
6. Credential: install `/etc/fleet-ci/mint/token` (root:fleetmint 0440, directory
   0750) out of band; never in this repo, a log or a chat.
7. GitHub (separate, human-approved): an org runner group `<fleet-group>` limited to
   the three repositories; fine-grained read-only token for `FLEET_ROUTE_TOKEN`
   ("Self-hosted runners: read" + "Actions: read").
8. Enable `fleet-slot@1..K` where K = `fleet_gate.py slots`.

Host names, IPs and user names of the real fleet stay out of this public repository;
`<host-a>`, `<fleet-group>` are placeholders.

## Canary plan

1. One host `<host-a>`, `SLOTS=1`, class `std`; `CI_FLEET_MODE` stays `off`.
   Verify `slot-1.json` cycles `wiping → claimed → minting → registered` and refuses
   under synthetic memory/io pressure (e.g. `stress-ng`) without registering.
   **Canary checklist:**
   * Run `ops/fleet_ci/canary-isolation-check 1 2` as root (needs two provisioned
     slot users and the loaded nft ruleset): every check must PASS — cross-slot
     /proc, /dev/shm and home reads denied, out-of-range loopback and LAN egress
     dropped, internet egress allowed, sudo denied, wipe leaves no residue. The
     harness never remounts the host `/proc`: the cross-read check uses the host's
     existing `hidepid=invisible`, else a private `unshare --mount --pid --fork`
     namespace with its own `/proc`, else reports WARN (host state unchanged).
   * **JIT env handoff:** while a job runs, as root check the runner process
     environment: `tr '\0' '\n' < /proc/<runner-pid>/environ` must **not** contain
     `ACTIONS_RUNNER_INPUT_JITCONFIG` after startup, and no child process may
     inherit it. This verifies `Runner.Listener` unsets the variable on the pinned
     runner version; re-check on every runner version bump.
   * Tarball pin: confirm the slot refuses to start with a wrong/missing
     `RUNNER_TARBALL_SHA256`.
   * Hold drill: force a mint refusal, confirm exit 78 leaves the unit stopped
     (no restart), then reconcile per the runbook above.
2. One non-required workflow in one repository pinned to `fleet-only` via a
   workflow-level override (with the trusted-source inputs wired); compare duration
   and failures with the hosted run.
3. Repository variable `CI_FLEET_MODE=hybrid` in one repository with spill ratio 1.0;
   watch hosted fallback counts and queue time for a week.
4. Add hosts and the `heavy` class; then the other repositories; `fleet-only` only
   after hosted fallback is consistently zero.

## Rollback

Set `CI_FLEET_MODE=off` (or delete it): every routed job returns to `ubuntu-24.04`
on the next run. Then `systemctl disable --now 'fleet-slot@*'` on hosts; registered
idle JIT runners disappear when their slot stops or can be removed in the org UI.

## Open items

* **Docker for the `heavy` class is an open item, not implemented.** Slot users have
  no supplementary groups, so no docker socket, and Docker is off the bake list.
  Options to review later: rootless docker per slot, or a `heavy` class with a
  reviewed exception. Until then, docker-heavy jobs stay on GitHub-hosted runners.
* Fixed-port tests in the three repositories must adopt `FLEET_PORT_BASE`.
* Org policy for public repositories on self-hosted runners must be reviewed before
  any fork exposure is reconsidered; today the trusted-source guard routes all fork
  PRs hosted, and the exposure disappears once the repositories are private.
