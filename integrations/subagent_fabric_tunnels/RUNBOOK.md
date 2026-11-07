# Subagent Fabric tunnel-client recovery — source runbook (FTR-2/3/4)

Status: **SOURCE ONLY — NOT INSTALLED, NOT PRODUCTION-PROVEN.**
Plan: `RECOVERY_PLAN.md` (same directory), commit
`6dd11e7015235eff3c0242ef90dea554f4f4c58d` on
`sol/fabric-tunnels-autoheal-20261030-01`; source-law pin
`bb85b429f2ffffd38408080ce4df7d6378c34100` (Skillpack 1.0.1).

Scope is exactly five EXISTING user LaunchAgents on m2studio —
`com.mastermind.subagent-fabric-tunnel.{c1,c2-business,c2-personal,c3,c4}` —
plus one NEW repo-owned watchdog label,
`com.mastermind.subagent-fabric-tunnel.health`. Nothing else in the family is
adoptable; a family plist outside these six labels makes install and health
recovery refuse until a human resolves it. The Desktop Commander carrier
(`com.mastermind.desktop-commander.remote`) is a permanently forbidden action
target in every code path and is never parsed or rewritten. No sudo, no
security/SIP change, no CURRENT.json selection, no host-pull repin, no
additional queue or process watcher exists in this integration.

## Files

| File | Role |
| --- | --- |
| `fabric_tunnel_common.py` | Scope/allowlist fences, launchd argv builders (forbidden-label asserted), redaction, atomic writes, runner seam |
| `fabric_tunnel_identity.py` | FTR-2 identity verification, policy delta, private qualification manifest |
| `fabric_tunnel_install.py` | FTR-2 install/verify/rollback: backup → CAS policy-trio mutation → bootout/bootstrap reload |
| `fabric_tunnel_health.py` | FTR-3 one bounded pass: classify, cooldown-bounded kickstart, alerts; watchdog agent install |
| `test_fabric_tunnel_identity.py` | Hermetic suite: allowlist/argv/symlink/ownership/manifest rejects |
| `test_fabric_tunnel_install.py` | Hermetic suite: idempotence, backup privacy, rollback, drift/rogue refusals, exit-0 restart policy |
| `test_fabric_tunnel_health.py` | Hermetic suite: PID/heartbeat/generation/telemetry/repair discrimination, cooldown, escalation |
| `tests/test_subagent_fabric_tunnels_source.py` | Hosted-CI gate that runs the colocated suites + compile/fence checks |

## Source run commands (already executed; see "Test evidence")

```bash
# from a repo checkout at the branch commit
python3 -m unittest discover -s integrations/subagent_fabric_tunnels \
    -p 'test_fabric_tunnel_*.py'            # focused hermetic suite
python3 -m unittest discover -s tests \
    -p 'test_subagent_fabric_tunnels_source.py'   # CI gate, 4 tests
python3 -m compileall -q integrations/subagent_fabric_tunnels
```

## Host procedure (requires separately authorized host gates — FTR-6/7)

### 1. Qualify (the single sanctioned qualification entrypoint)

`verify` is NOT qualification: it reads back a manifest that does not exist
on a fresh host. The real entrypoint is the `qualify` subcommand, which
derives all five installed identities from the ACTUAL plists, enforces
distinct argv AND distinct executable identity, validates a CLOSED
operator-facts schema, and writes the private 0600 manifest:

```bash
# 1a. First-install dry run from an EMPTY manifest — reads only, writes nothing,
#     proves the install path is feasible before anything is authorized:
python3 integrations/subagent_fabric_tunnels/fabric_tunnel_install.py --home ~ \
    qualify --dry-run --facts-file ~/ftr-facts.json

# 1b. Actual qualification (explicit operator confirmation):
python3 integrations/subagent_fabric_tunnels/fabric_tunnel_install.py --home ~ \
    qualify --confirm --facts-file ~/ftr-facts.json

# 1c. Readback after install (requires the manifest; never a substitute for 1b):
python3 integrations/subagent_fabric_tunnels/fabric_tunnel_install.py --home ~ verify
```

The facts file is an operator-written JSON document (0600, never committed,
group/world-WRITABLE modes are refused); qualification validates it against a
closed schema and refuses unknown fields — nothing is invented, hardcoded, or
guessed:

```json
{
  "seats": {
    "com.mastermind.subagent-fabric-tunnel.c1": {
      "heartbeat_mode": "first_party_cli_control_plane_poll",
      "heartbeat_profile_file": "/absolute/path/to/that-seats-profile.json",
      "heartbeat_kind": "tunnel-client-control-plane-last-seen",
      "heartbeat_proof_note": "how the operator proved the profile's health.url_file + control_plane_poll value is the first-party last-seen signal"
    },
    "com.mastermind.subagent-fabric-tunnel.c2-business": {
      "heartbeat_path": "/absolute/path/to/that-seats-heartbeat",
      "heartbeat_kind": "tunnel-client-control-plane-last-seen",
      "heartbeat_proof_note": "how the operator proved this file is the first-party last-seen signal"
    }
  },
  "host": {
    "native_store_path": "/absolute/native-code-releases/path",
    "host_pull_telemetry_dir": "/absolute/telemetry/root",
    "host_pull_telemetry_files": ["lane-a.json", "lane-b.json"],
    "pinned_generation": "<64 lowercase hex>",
    "stale_telemetry_seconds": 900,
    "repair": {"files": {"ext/remote_sub_exec.py": "<64 lowercase hex>"}}
  }
}
```

Every fact is optional; every ABSENT fact becomes an explicit
`*_unqualified` health alert instead of a guessed default. Facts that ARE
provided are validated hard: absolute paths, existing regular non-symlink
files (including each heartbeat at qualification time — a client that has
never written its heartbeat cannot be qualified yet), ≤32 telemetry files
with relative POSIX paths and a `.json` suffix, 64-hex pinned generation and
repair digests. `heartbeat_kind` requires `heartbeat_proof_note`: a heartbeat
file's mtime is never treated as the tunnel-client/control-plane last-seen
signal, with or without that operator first-party attestation (B6). The
mtime is a diagnostic observation only.

#### Heartbeat modes (strictly typed; modes are exclusive per seat)

`heartbeat_mode` selects the last-seen evidence source and must be one of
exactly two spellings — anything else refuses (`facts_heartbeat_mode_unknown`):

- `file_mtime_attested` — the legacy mode, also the meaning of an ABSENT mode
  on a safe legacy manifest. Requires `heartbeat_path`; the file must exist as
  a regular non-symlink file at qualification. Per pass the file's mtime is a
  DIAGNOSTIC OBSERVATION ONLY: it can never establish health, never reset the
  attempt ladder, and never authorize a stale forced restart — NOT even with
  the operator attestation above. The legacy mode reports
  `heartbeat_mtime_diagnostic_only` for a fresh mtime and
  `stale_heartbeat_unproven_alert_only` for a stale one. Health and every
  heartbeat-derived action come from the CLI-poll mode below.
- `first_party_cli_control_plane_poll` — the stronger first-party proof.
  Requires `heartbeat_profile_file` (the seat's own per-seat client profile,
  a JSON file) and refuses `heartbeat_path`. Qualification, before anything
  is written:
  - the seat's installed identity is verified as always (argv, executable
    path, executable digest) — the probe later runs ONLY that pinned
    executable, never a path from facts;
  - the profile is verified: bounded size, seat-owned, not group/world
    writable, symlink-free lexical ancestors, no foreign seat identity in the
    path, valid JSON with a `health.url_file` entry;
  - the derived URL locator (`health.url_file`) is verified the same way
    (bounded, seat-owned, safe modes, symlink-free ancestors, no traversal,
    no foreign seat identity) and recorded in the PRIVATE manifest as
    `heartbeat_url_locator`. It is DERIVED, never an accepted operator fact —
    a manifest cannot be steered to an unvetted URL file through facts;
  - cross-seat isolation: two seats may never share a profile file or a URL
    locator;
  - ONE read-only live probe per seat must return the known-good shape:
    `<pinned executable> health --url-file <pinned locator>
    --require-control-plane-poll --json` → rc 0, `result=ok`,
    `healthz.ok=true`, `readyz.ok=true`,
    `control_plane_poll.ok=true` with a numeric Unix-seconds value. A probe
    that times out, errors, or fails schema validation refuses the whole
    qualification (`facts_cli_poll_probe_failed`) — an evidence source that
    never worked is never recorded.
  Mixing the modes on one seat refuses; a hand-edited manifest that mixes
  them is alerted (`heartbeat_mode_ambiguous`) and never classified.

Refusals that must be resolved by a human before anything else:
`foreign identity 'chatgpt1'`, `argv_tuple_duplicated`,
`executable_identity_duplicated`, `rogue_family_labels_present`,
`*_drift_since_qualification`, `label_mismatch`, `*_plist_owner_unsafe`,
`facts_*` (including `facts_heartbeat_mode_unknown`,
`facts_poll_profile_duplicated`, `facts_poll_locator_duplicated`,
`facts_cli_poll_probe_failed` / `facts_cli_poll_probe_refused`).
Qualification fails closed: any refusal means nothing is written — and for
CLI-poll seats, no probe ever ran against a manifest that was refused.

### 2. Install (the only plist mutation this integration performs)

```bash
python3 integrations/subagent_fabric_tunnels/fabric_tunnel_install.py \
    --home ~ install --confirm
```

Per seat: preimage backup (private, 0600, digest sidecar) → apply exactly
`RunAtLoad=true`, unconditional `KeepAlive=true` (boolean; any dict form is
replaced because the tunnel client may exit 0 after SIGTERM),
`ThrottleInterval>=10` (a larger incumbent is preserved) → atomic rename with
parse-back → `launchctl bootout gui/<uid>/<label>` when loaded, then
`launchctl bootstrap gui/<uid> <plist>`. On bootstrap failure the preimage is
restored and the original plist re-bootstrapped (`install_failed_rolled_back`);
if even that fails the seat hard-alerts (`install_failed_rollback_also_failed`).
Idempotent: an already-compliant seat is reported `already_compliant` with no
write and no reload. Every action target is asserted against the immutable
allowlist before any argv is built.

The batch is TRANSACTIONAL (B5): every mutation is fully derived before the
first write, and a failure on any seat rolls every previously installed seat
back through its validated preimage CAS (status `batch_rolled_back`), leaving
unattempted seats reported `not_attempted`. Only a fully installed or fully
already-compliant batch exits 0; partial states are never silent and never
survive a failed run.

Mutation custody ( tightened): the batch preflight hash-check is re-asserted
IMMEDIATELY before each seat's mutation — the on-disk bytes AND mode must
still be the EXACT qualified predecessor pinned in the manifest. A concurrent
external writer that lands after preflight makes that seat refuse
(`install_pre_mutation_drift_refused`); the intervening bytes are preserved
untouched, no launchd action is taken, and the rest of the batch aborts.
This CAS on the qualified bytes is the single mutation-owner enforcement; no
second lifecycle or lock plane exists. The LEXICAL ancestor chain of every
plist is also re-bound symlink-free at install time
(`*_install_parent_unsafe`), so a `~/Library` swap between qualification and
install refuses instead of resolving through the symlink.

Readback after install:

```bash
python3 integrations/subagent_fabric_tunnels/fabric_tunnel_install.py --home ~ verify
```

### 3. Health loop (one bounded pass per invocation)

```bash
python3 integrations/subagent_fabric_tunnels/fabric_tunnel_health.py pass --home ~
python3 integrations/subagent_fabric_tunnels/fabric_tunnel_health.py last-pass --home ~
```

Installed form: the watchdog is installed and verified through the explicit
operator CLI (not only an importable function):

```bash
python3 integrations/subagent_fabric_tunnels/fabric_tunnel_health.py \
    --home ~ watchdog-install --confirm
python3 integrations/subagent_fabric_tunnels/fabric_tunnel_health.py \
    --home ~ watchdog-verify
```

`watchdog-install --confirm` copies the four modules privately and installs
the watchdog LaunchAgent — `StartInterval=60`, `RunAtLoad=true`,
`ThrottleInterval=10`, **no KeepAlive** (a periodic job must not be
resurrected into a tight loop), python3 resolved from the host at install
time. Each fire is ONE pass; there is no daemon and no retry plane. It
refuses without `--confirm`, without a fresh manifest, or on any unsafe
target; `watchdog-verify` is read-only, performs no launchd call, and fails
closed (exit 4) on any absence, mismatch, or tamper
(`watchdog_plist_unavailable`, `watchdog_plist_not_ours`,
`watchdog_module_mode_unsafe`).

Watchdog install safety (B3, tightened): every target about to CHANGE (the
four copied modules and the watchdog plist) is captured as an exact private
preimage backup BEFORE any edit, and that backup is recorded as THIS
attempt's rollback source; already byte-identical targets are left untouched
(idempotent re-runs write nothing, create no backup churn, and rollback never
resurrects a stale earlier generation into them); symlinked or unsafe
targets REFUSE instead of being overwritten; the LEXICAL ancestor chains of
both write roots are re-bound symlink-free at install time; every write is
verified by read-back digest; and ANY fault — post-write mismatch, write or
chmod exception, or launchd failure — rolls ALL targets changed by this
attempt back to their exact preimage (or restores ABSENCE) under CAS against
this attempt's post digests. External drift after our write is preserved,
never clobbered (`watchdog_rollback_cas_refused_external_drift`). launchd is
reloaded only when the plist itself was actually mutated by the attempt, so
a fault during an earlier module write never starts or stops any job.
Watchdog install remains an install-time mutation and keeps the strict
fresh-manifest requirement.

### Manifest age vs. durable recovery (B1)

The manifest carries a one-day (86400 s) operator attestation bound. It
bounds TRUST of the attestation, not the life of the recovery:

- All MUTATION paths (install, rollback, verify, watchdog install) still
  refuse a manifest past the bound: `manifest_stale_requalify_required`.
  Install-time authorization and the preimage CAS are unchanged.
- The read-only health pass continues past the boundary: each pass re-proves
  every seat's installed identity, program digest/argv, and qualified
  heartbeat path from LIVE host state (`revalidate_stale_identity`) and
  raises a persistent `manifest_stale_revalidated` alert so the operator
  requalifies. A seat whose live identity no longer matches the pinned
  manifest is ALERT ONLY (`seat_identity_tampered_alert_only`; stable reason
  codes `argv_changed` / `executable_path_changed` / `executable_digest_changed`
  / `heartbeat_path_not_regular`) until a human requalifies — tampering never
  earns a kickstart and never disables the other seats' recovery. Nothing in
  this integration touches login, security, reboot, or launchd domain
  configuration.

### Heartbeat first-party proof (B6)

A heartbeat FILE's mtime is DIAGNOSTIC ONLY, with or without the operator
attestation. `heartbeat_kind` + `heartbeat_proof_note` prove that an operator
once correlated the file with the control plane; they do NOT turn a file
mtime into first-party control-plane evidence. So a stale mtime is
`stale_heartbeat_unproven_alert_only` (ALERT ONLY, no forced restart) and a
fresh mtime is `heartbeat_mtime_diagnostic_only` (never `healthy`), in both
cases stating the exact required host proof: the seat must be qualified for
`first_party_cli_control_plane_poll`, whose last-seen comes from the seat's
OWN control-plane poll. A file mtime never establishes health, never resets
the attempt ladder, and never authorizes a restart.
Missing-PID recovery is unaffected — that state is proven by launchd itself,
and it keeps its exact identity and policy guards.
The user-visible error this replaces ("Tunnel-client has not been seen for
300 seconds") is never inferred from an arbitrary file's age.

#### First-party CLI control-plane-poll evidence (per pass)

For a seat qualified with `first_party_cli_control_plane_poll`, every pass
re-proves the evidence source BEFORE the client is invoked, then derives the
last-seen from a REAL control-plane poll instead of any file mtime:

1. The manifest-pinned executable must still be a regular non-symlink file
   digesting to the pinned value (`cli_poll_executable_drift` /
   `cli_poll_executable_digest_changed` otherwise). An arbitrary or drifted
   binary is never executed.
2. The qualified profile is re-parsed and its `health.url_file` must STILL
   equal the pinned locator, with both files re-proven bounded, seat-owned,
   safe-moded, and symlink-free (`cli_poll_profile_unsafe` /
   `cli_poll_profile_locator_changed` otherwise).
3. The EXACT read-only argv `<pinned executable> health --url-file <pinned
   locator> --require-control-plane-poll --json` runs through a bounded
   runner: no shell, stdin detached, hard per-seat deadline of 5 s, and both
   stdout and stderr hard-capped at 16 KiB — past either cap the child is
   killed and the partial output is discarded (`cli_poll_output_oversized`).
4. Only the known-good rc0/ok/ok/ok shape with a finite positive
   Unix-seconds `control_plane_poll.value` is evidence; the last-seen age is
   `now - value`. A value ahead of local time within a 300 s skew clamps to a
   fresh age of zero (fresh evidence authorizes nothing); anything further
   ahead refuses (`cli_poll_value_in_future`), as do non-positive values,
   booleans/strings/NaN, malformed JSON, any `ok` that is not the boolean
   `true`, and nonzero rc / timeout.
5. Every refusal is `control_plane_poll_unproven_alert_only` for that seat:
   fail closed, NO action, NO guessed direction, and no URL, profile path,
   locator, or payload content is ever printed (the stable refusal code is
   in the private pass report).
6. Replay guard: a stale verdict whose (last-seen value, stdout digest) is
   byte-identical to the provenance recorded at the seat's LAST
   evidence-authorized kick (`last_kick_poll_value` /
   `last_kick_poll_digest` in the kick ledger) is
   `control_plane_poll_replayed_alert_only` — consumed evidence may not
   authorize another kick or witness freshness. Advanced evidence that is
   STRICTLY newer than a seat's reservation AND FRESH at the observing pass
   (last-seen age inside the same 300 s window the health rule uses) is a
   bound recovery proof: it releases that acknowledged attempt and the seat
   may act again under the same 1800 s cooldown. A newer-but-STALE
   observation is never a recovery proof, however far it advances the
   timestamp. A consumed attempt is never refunded by anything else.
7. A missing PID still recovers through the launchd-proven route and NO poll
   is executed for that seat; `launchctl print` ambiguity stays alert-only.

The poll is evidence gathering inside the existing bounded pass: no new
scheduler, process watcher, data store, or control plane is introduced, and
the same cooldown/escalation ledger bounds it.

Classification (distinguished exactly as the plan requires):

| Signal | Outcome |
| --- | --- |
| No PID on a qualified job | `missing_pid` → plain `launchctl kickstart gui/<uid>/<label>` (either heartbeat mode; no poll is executed) |
| No PID, 3 persisted attempts without a witnessed fresh heartbeat | `kickstart_escalated_alert`, NO fourth attempt even after cooldown, until a healthy pass witnesses a fresh heartbeat. The ladder is reset only by a witnessed recovery or by the bound first-party release of an acknowledged attempt |
| PID present, CLI-poll last-seen older than 300 s, first-party attested | `stale_heartbeat` → `launchctl kickstart -k` |
| PID present, CLI-poll last-seen older than 300 s, NOT attested | `stale_heartbeat_unproven_alert_only`, NO action, exact required proof in the alert |
| PID present, last-seen fresh (CLI poll) | `healthy`, no action |
| PID present, legacy file mtime fresh (file mode) | `heartbeat_mtime_diagnostic_only`, NO action, never `healthy` |
| PID present, legacy file mtime older than 300 s (file mode, attested or not) | `stale_heartbeat_unproven_alert_only`, NO action, never a forced restart |
| An action was invoked (or refused pre-spawn) and its outcome is not settled | `pending_effect_held_alert_only`: NO further attempt for that seat, ever — not after the cooldown, not because a healthy observation arrived. An ACKNOWLEDGED attempt is held the same way and is released only by a bound first-party poll strictly newer than its reservation AND fresh at the observing pass (last-seen age inside the 300 s window); every other outcome is held for the original owner's own reconciliation |
| CLI poll refused/ambiguous/oversized/timeout/nonzero rc/malformed/future/nonpositive | `control_plane_poll_unproven_alert_only`, NO action, stable refusal code in the private report |
| CLI poll byte-identical to the last kick's recorded provenance | `control_plane_poll_replayed_alert_only`, NO action and NO freshness witness |
| Heartbeat file missing/unreadable (file mode) | `heartbeat_missing` alert, NO action |
| Heartbeat path never qualified | `heartbeat_path_unqualified`, NO action |
| CLI-poll profile never qualified | `heartbeat_poll_profile_unqualified`, NO action |
| Manifest mixes heartbeat modes on one seat | `heartbeat_mode_ambiguous`, never classified |
| Heartbeat recorded but never attested first-party | `heartbeat_first_party_unproven` alert (per pass, until qualified) |
| `launchctl print` nonzero WITHOUT the specific `Could not find service` diagnostic | `launchd_state_uncertain_alert_only`, NO action, zero effect calls (never mistaken for a missing PID) |
| Kick ledger corrupt / unreadable / symlinked / unsafe-permissioned / malformed | `kick_ledger_refused_alert_only` (+ `kick_ledger_refused_recovery_alert_only`): NO recovery for the whole pass; on-disk history preserved, never auto-reset |
| Live seat identity ≠ pinned manifest (only past the day boundary) | `seat_identity_tampered_alert_only`, NO action for that seat; other seats recover |
| Manifest past 86400 s on a health pass | `manifest_stale_revalidated` alert; live revalidation, recovery continues |
| `CURRENT.json` selection ≠ qualified pinned generation | `selected_generation_drift` alert; repin REFUSED, CURRENT.json never rewritten |
| Selected generation missing | `selected_generation_missing` alert |
| Installed generation repair digest ≠ qualified stdin/ARG_MAX repair digest | `stdin_argmax_repair_missing` alert, never an auto selection/publish |
| Qualified telemetry set: oldest required file older than the threshold | `host_pull_telemetry_stale` alert |
| Any qualified telemetry file missing/symlinked/invalid, or file set unqualified | `host_pull_telemetry_unqualified` alert (never a partial freshness proof) |
| Kickstart already performed within cooldown (1800 s) | `kickstart_suppressed_cooldown` |

Host-pull telemetry is read from a bounded CLOSED set of operator-qualified
explicit files (`host_pull_telemetry_files` under `host_pull_telemetry_dir`,
≤32 entries, `.json` suffix, relative POSIX paths, regular non-symlink
files). The OLDEST required file drives freshness: an unrelated freshly
written file under the same root can never mask stale telemetry, and there
is no recursive scan to make the minute watchdog unbounded (B2).

The kick ledger is private (0600), persists across passes, and is what makes
recovery bounded. It also fails CLOSED: a GENUINELY ABSENT ledger initializes
as first use, but an existing ledger that is corrupt, unreadable, symlinked,
non-regular, group/world-writable, or shape-invalid REFUSES the whole pass's
recovery (`kick_ledger_refused_recovery_alert_only`) and is never rewritten —
cooldown/escalation history can never be silently erased to re-enable
unbounded restarts. An existing ledger that VANISHES between the lstat and
the read is not an empty ledger either: it refuses the pass. Every persisted
number is validated as finite and non-negative (a NaN `last_kick_at` used to
defeat the cooldown comparison), and every pending reservation must bind its
row's timestamp and attempt count. For CLI-poll seats each evidence-authorized
kick also records payload provenance (`last_kick_poll_value`, `last_kick_poll_digest`)
so byte-identical consumed evidence can never authorize the next kick; these
fields are validated on load and absent for file-mtime kicks and legacy
ledgers. Host-pull generation alerts never block a qualified seat's
own crash recovery: a dead tunnel client is recoverable even while the host
carrier needs human attention.

#### The pre-effect reservation, the acknowledgement, and the ledger lock

Every action this integration performs is bracketed by the SAME private
ledger that already owned the cooldown and escalation counters. There is no
second store, registry, coordinator, or queue.

1. **Reserve (durable, BEFORE the action exists).** The attempt counter and
   the 1800 s cooldown are consumed and written to the ledger BEFORE the
   action is invoked, together with a `pending` record that binds the row's
   timestamp, the row's attempt count, the trigger, whether the action was a
   forced restart, and the pre-attempt first-party poll provenance (value
   and digest) when the seat runs the CLI-poll mode. The write must prove
   BOTH the file and its parent directory durable; a write that cannot prove
   it refuses the action (`kick_ledger_reservation_failed_alert_only`) — the
   action never runs.
2. **Invoke.** Exactly one `launchctl kickstart`.
3. **Acknowledge (durable, ONE write).** A rc0 means the command was
   ACKNOWLEDGED — that is not a recovery witness, and the attempt stays
   consumed. The reservation is **not deleted**: it MOVES to
   `acknowledged_awaiting_recovery` in the SAME ledger and keeps holding the
   seat. Nothing is ever removed from the ledger on acknowledgement.

The acknowledgement is one write precisely because the durable writer
replaces the target by rename BEFORE it fsyncs the parent directory: a
failed parent-directory fsync therefore leaves the NEW bytes visible on
disk. A transition that DELETED the reservation could leave a readable
ledger with no reservation at all — a seat that looks free to act again
while the acting pass still held it. A transition that only MOVES the
reservation is conservative under every failure of that write: the disk
holds either the previous `reserved` bytes or the new
`acknowledged_awaiting_recovery` bytes, and both hold the seat.

Every outcome that is not a clean acknowledgement stays PENDING and holds
the seat: a generic nonzero exit, a signal exit, a timeout (rc 124, or an
explicit `timed_out` — which holds even against a contradictory rc0), an
OSError from the runner, and an interruption. A pre-spawn refusal (policy or
permission) proves the action was NOT applied, but it stays held too — it is
never auto-retried after a cooldown.

**Only a bound first-party recovery proof releases a seat.** An
acknowledged attempt is released — and its attempt ladder reset — ONLY by a
qualified `first_party_cli_control_plane_poll` whose timestamp is STRICTLY
later than the reservation, which advances any pre-attempt poll recorded
with that reservation, AND whose observation is FRESH at the observing pass
(last-seen age inside the same 300 s window the health rule uses). The proof
must be bound to the exact seat and to the
exact reservation (the seat's whole pinned identity is re-proved by the
poll itself), and its evidence is kept in the SAME ledger (`last_recovery`:
the attempt, the reservation it releases, the proof's timestamp and
provenance). The stored proof is validated against its OWN recorded release
time, so a legitimate historical proof never expires against the current
clock. A fresh-but-pre-attempt timestamp, a newer-but-stale timestamp, a
replayed payload, a wrong
service, a file mtime, a present PID alone, and missing data never reset the
attempt ladder; a healthy observation never clears an ambiguous, refused,
interrupted or still-reserved outcome.

The conservative holding after an acknowledgement is INTENTIONAL: it
replaces the old promise of repeated blind kicks. An acknowledged seat is
NOT retried automatically, not even after the cooldown, and the attempt
ladder does not advance on its own — "no fourth attempt" is therefore a
floor, not a ceiling. A seat whose outcome stayed ambiguous, refused or
interrupted is held until the ORIGINAL OWNER reconciles the ledger by hand;
there is no in-code reconciliation API, and none is added here — a prose
mechanism never refunds budget and never clears a newer pending attempt.

A write that cannot be proven durable stays BLOCKING: the reservation is
never dropped, the pass stops writing and performing, the on-disk state
keeps the unresolved marker, and the CLI exits nonzero
(`kick_ledger_settlement_failed`). There is no blind retry and no automatic
compensation.

One inherited limitation is stated plainly: a ledger file that is ABSENT at
the first `lstat` is treated as a genuine first use. That distinction is
unproven against a real installed ledger and remains an installation
qualification limitation, not a proven first-use signal.

Every ledger-writing pass is serialized by ONE exclusive lock
(`kick-ledger.lock`, adjacent to the ledger in the same private state root,
never the ledger's own replaceable inode, owner/mode/inode qualified).
Contention fails closed: the pass goes alert-only
(`kick_ledger_lock_refused_alert_only`) and performs no action, so two
concurrent passes can never invoke the same action twice. An observation-only
pass NEVER writes the ledger and can therefore never overwrite a pending
state.

### Login/session semantics (documented, never changed)

These jobs are USER LaunchAgents: launchd loads them only when the user's
GUI/console session is established (login, or a re-login after reboot). They
do NOT run at power-on before login, and neither do the watchdog's passes.
After reboot WITHOUT a logged-in console session, no tunnel client, no
watchdog pass, and therefore no automatic recovery exists until someone logs
in; any "recovers after reboot" claim additionally requires a proven
logged-in session owner. This integration documents that fact and does not
and may not change login items, launchd domain configuration, security, or
session behavior to pre-login startup.

### Deliberate stop semantics

With unconditional `KeepAlive=true`, any exit — SIGTERM, crash, or clean
exit 0 — is followed by a launchd restart. A `kill` of the client PID is
therefore NOT a stop; it is a restart request. The only sanctioned deliberate
stop is the launchd owner action:

```bash
launchctl bootout gui/$(id -u)/com.mastermind.subagent-fabric-tunnel.<seat>
# restore:
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.mastermind.subagent-fabric-tunnel.<seat>.plist
```

### Rollback

```bash
python3 integrations/subagent_fabric_tunnels/fabric_tunnel_install.py \
    --home ~ rollback --confirm --label com.mastermind.subagent-fabric-tunnel.<seat>
```

Restores the newest preimage (CAS: refuses if current bytes drifted past the
recorded post digest), re-bootstraps the restored plist, and reports the
result as an alert code, never silently. Backups live under
`~/Library/Application Support/mastermind-subagent-fabric-tunnels/backups/`
(0700 dir, 0600 files) and must never be committed or pasted anywhere.

## Shared-executable identity binding and the Cellar allowance (2026-10-31 repair)

The five incumbent seats legitimately SHARE one user-owned, safe-mode
`tunnel-client` binary (same path, same inode, same SHA-256) installed under
the canonical Apple-Silicon Homebrew prefix, whose `Cellar` directory is
user-owned mode 0775 by Homebrew's own layout. The original blanket
"every seat needs its own binary" rejection is replaced by a stronger,
positive per-seat proof that fails closed:

- Each seat in a shared-executable group must carry a qualified poll profile
  that its INSTALLED plist argv names with EXACTLY ONE absolute
  `--profile-file` option, byte-equal to the operator fact. Missing,
  duplicated, relative, foreign, or mismatched flags refuse before anything
  is written.
- Each bound profile is proven unique per seat by path, `(dev, ino)` inode,
  and content SHA-256; it must be a seat-owned 0600-bounded regular file,
  never a hardlink, with a strictly safe lexical ancestor chain; its derived
  `health.url_file` locator is proven and pinned the same way, uniquely.
- Each profile's `control_plane.tunnel_id` must be present, well-formed
  (bounded, printable, URL-free), and UNIQUE across the five seats. The raw
  id is never stored, logged, or printed — only a domain-separated SHA-256
  digest (`tunnel_id_binding_hash`) is pinned in the private manifest.
- Distinct executable binaries remain fully supported with no binding
  required (legacy shape, byte-for-byte backward compatible manifests).

The global `require_parent_safe` stays strict for every path this
integration touches (plists, profiles, locators, telemetry, manifests,
watchdog roots). The ONLY exception is a caller-local, executable-only walk
(`require_executable_parent_safe`) that allows exactly ONE ancestor — the
directory whose absolute lexical path equals the canonical Homebrew Cellar
prefix — when it verifies as a real (non-symlink) directory, user-owned,
mode EXACTLY 0775 (group-shared, never world-writable, no sticky/setid
bits). At most one ancestor may use the allowance; every other ancestor of
the executable keeps full strict checking. Hermetic tests inject a
controlled fake prefix by patching the module constant; no runtime caller
chooses a prefix. The executable, its parent directory, and the Cellar
allowance directory are pinned by `(dev, ino, uid, mode)` from one nofollow
descriptor observation each, and `seat_identity_drift_problems`
re-proves them against the manifest BEFORE EVERY kickstart and install/rollback
effect — not merely after the manifest's one-day attestation boundary.

**Residual risk, stated honestly:** a group member of the Homebrew Cellar
can still rename/replace entries inside the group-writable directory
between verification and the subsequent launchd effect (a classic
group-member rename/exec TOCTOU in the launchd path), and a sufficiently
lucky delete-and-recreate that reuses an inode number can momentarily evade
a `(dev, ino)` pin (content changes are still caught by the digest pins).
This residual is REDUCED by the per-effect re-proofs above but is NOT
eliminated without host-side permission changes, which this integration is
forbidden to make. The independent reviewer must adjudicate this residual
explicitly rather than assume it away.

### Post-review hardening (2026-10-30) — the HIGH residual is still HOLD_SECURITY

The first independent non-author review returned HOLD_SECURITY with one
HIGH deployment blocker and three bounded code findings. The three bounded
findings are now fixed in source; the HIGH is NOT fixed and its HOLD
remains authoritative for release:

- **MEDIUM (fixed, residual reduced — not closed):** `cli_poll_evidence`
  re-proved the executable file digest but never the pinned
  parent/Cellar-directory identity before each frequent poll. It now runs
  the FULL `seat_identity_drift_problems` engine (plist argv, executable
  path/digest/`(dev, ino, uid, mode)`, pinned parent identity, pinned
  Cellar-allowance identity, and the whole pinned
  profile/locator/tunnel-id binding) as the LAST observation before the
  spawn, fail-closed on any drift (`cli_poll_identity_drift`) and on any
  re-proof exception (`cli_poll_identity_reproof_failed`) — a refused poll
  probes nothing and authorizes no kick. This NARROWS the window but does
  NOT close the group-member path rename between re-proof and spawn; the
  HIGH blocker below still applies to every unattended credentialed
  restart and CLI poll.
- **LOW (fixed):** the verified-identity descriptor opens required
  `os.O_NOFOLLOW` but silently degraded via
  `getattr(os, "O_NOFOLLOW", 0)` on a host without the flag — i.e. a
  symlink-FOLLOWING open. Both `verified_file_identity` and
  `verified_dir_identity` now fail closed with a stable
  `IdentityRejected` when the flag is absent; on the real Darwin/Linux
  targets the flag exists and the open semantics are unchanged.
- **LOW (fixed):** heartbeat attestation keyed on `heartbeat_kind` alone
  let a tampered private manifest mint the forced-restart proof switch
  from a half-written fact. `run_pass`/`classify_seat` now require BOTH a
  non-blank operator-qualified `heartbeat_kind` AND a non-blank
  `heartbeat_proof_note`; kind-only or a blank note is alert-only
  (`stale_heartbeat_unproven_alert_only`) and can never permit a stale
  forced kick. Poll/first-party evidence semantics, the 300 s threshold,
  1800 s cooldown, 3-kick escalation limit, and the replayed-evidence
  block are unchanged.
- **HIGH (UNRESOLVED — deployment blocker, HOLD_SECURITY):** the real
  installed Cellar ancestor is user-owned, group-writable mode 0775 with
  other group members, so a group member can replace the executable path
  in the TOCTOU window before `Popen`/launchd kickstart despite digest,
  inode, and per-effect pins. Unattended credentialed restart/CLI-poll
  operation stays blocked until the risk is accepted by an exact
  authorized human OR an independently reviewed private-executable
  relocation design preserves program behavior. No chmod/SIP/host
  permission change is permitted from this integration, and no operator
  setting may waive the unsafe group-write shape.

### Recovery-ledger hardening (S5) — the HIGH residual is UNCHANGED

The bounded recovery work below changes the health pass's DECISION
boundaries. It does NOT touch the spawn path, the identity pins, the
Cellar allowance, or the privilege model, so the **HIGH HOLD_SECURITY
residual above is unchanged and still blocks unattended credentialed
restart / CLI-poll operation**. Nothing here permits an install or a
restart, and nothing here proves confinement.

- The legacy file mtime is now DIAGNOSTIC ONLY. It can no longer establish
  health, reset the attempt ladder, or authorize a stale forced restart —
  not even with `heartbeat_kind` + `heartbeat_proof_note`. Health and every
  heartbeat-derived action come from the strictly typed first-party
  control-plane poll; the launchd-proven missing-PID route is unchanged and
  keeps its exact identity and policy guards.
- Every invoked action is now preceded by a DURABLE PRE-EFFECT RESERVATION
  in the existing private kick ledger: the attempt and the 1800 s cooldown
  are consumed before the action exists, and the reservation binds the
  row's timestamp, attempt count, trigger, and forced flag. The reservation
  must prove file AND parent-directory durability or the action is refused
  before the spawn.
- Every outcome that is not a clean acknowledgement leaves the seat HELD
  (pending) — generic nonzero, signal, timeout (including an explicit
  `timed_out` against a contradictory rc0), OSError, interruption, and
  pre-spawn refusal alike — and only the original owner's own
  reconciliation of the ledger clears it. A healthy observation can never
  erase it.
- A clean acknowledgement is NOT a release. The reservation is retained in
  the SAME ledger as `acknowledged_awaiting_recovery` and keeps holding the
  seat; nothing is deleted on acknowledgement. The acknowledgement is ONE
  durable write, because the durable writer's rename lands before its
  parent-directory fsync, and a deletion could therefore leave a readable
  ledger with a FREE seat.
- The ONLY in-band release is a bound first-party recovery proof: a
  qualified `first_party_cli_control_plane_poll` strictly newer than the
  reservation that advances any pre-attempt poll AND fresh at the observing
  pass (last-seen age inside the 300 s window), bound to the exact seat
  and reservation, with its evidence kept in the same ledger
  (`last_recovery`). The attempt ladder is reset by that release and by
  nothing else. A newer-but-stale observation leaves the reservation, the
  attempt count, the cooldown anchor and the recorded recovery evidence
  exactly as they were. The resulting holding after an acknowledgement is
  stricter than the old repeated-kick promise and is intentional.
- A write that cannot be proven durable stays blocking, stops the pass's
  writes and effects, and makes the CLI exit nonzero. There is no blind
  retry and no automatic compensation.
- Every ledger-writing pass is serialized by one exclusive, qualified lock
  beside the ledger, so two concurrent passes can never invoke the same
  action twice. An observation-only pass never writes the ledger.

## Secret-safety contract

- Job `EnvironmentVariables` are stored ONLY inside the private manifest and
  private backups; every stdout/evidence surface passes through `redact_value`.
- Identity tables print label, digest prefixes, mode, argv LENGTH — never an
  argv body, never an env value, never a token.
- Pass reports contain no argv bodies; the report file is 0600.
- Control-plane tunnel ids are pinned ONLY as domain-separated SHA-256
  digests; profile JSON, profile paths, and URL locators are never printed.
- No credential, tunnel identity, or path is hardcoded in source; nothing in
  this repo's static text qualifies production (stale snapshots are not
  authority — the plan's own fence).

## What this is NOT

- Not installed anywhere, and no proof of host health.
- Not a CURRENT.json selector, publisher, or generation chooser.
- Not a Desktop Commander carrier observer or modifier.
- Not a pre-login service: recovery exists only inside a live logged-in GUI
  session (see "Login/session semantics").
- Not a heartbeat truth-source by itself: a file mtime is never claimed as
  first-party tunnel-client/control-plane last-seen — not even with an
  operator attestation, and it never establishes health or authorizes a
  restart — and the CLI-poll mode only reports what the seat's own qualified
  binary proved in a re-verified, bounded, read-only probe this pass.
- Not merged/approved: one Draft PR from the branch may exist, but review is
  a separate independent non-authoring Fabric pass (FTR-5) and merge/approve
  stays out of this mission.
