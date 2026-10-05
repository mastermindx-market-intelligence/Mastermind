# External fleet recovery route acceptance

This is the separate external-network acceptance journey named by
`ops/executive_os/HOST_PREREQUISITES.md`. It does not replace the local
`home-mac-recovery-base/v1` gate and does not create another lifecycle,
scheduler, credential store, SSH configuration owner, or control plane.

A home Mac that is locally `READY` can still be unrecoverable from an operator
away from the home network. Before unattended travel, prove both layers:

1. the target Mac passes its applicable local host-recovery profile; and
2. an operator machine outside the home LAN can traverse an already-approved
   gateway and reach the target using the existing recovery identity.

## Read-only external probe

Run `ops/executive_os/external_recovery_readiness.py` on the operator machine.
The probe accepts route coordinates but never prints them back in its report.
Use only an already-approved gateway, target and recovery key.

```bash
/usr/bin/python3 -I -S -B \
  "$SOURCE_REPO/ops/executive_os/external_recovery_readiness.py" \
  --route-ref "route-<64-lower-hex>" \
  --gateway-host "$GATEWAY_HOST" \
  --gateway-user "$GATEWAY_USER" \
  --gateway-host-key-alias "$GATEWAY_KNOWN_HOST_IDENTITY" \
  --target-host "$TARGET_LAN_HOST" \
  --target-user "$TARGET_USER" \
  --target-host-key-alias "$TARGET_KNOWN_HOST_IDENTITY" \
  --identity-file "$HOME/.ssh/<existing-recovery-key>"
```

The gateway and target host-key aliases are optional trust-coordinate
overrides for cases where transport naming differs from the already-enrolled
`known_hosts` identity. They never enroll or update a host key.

The identity file must be a regular, non-symlink file directly under the
operator's `~/.ssh`, owned by that operator, with no group/other permission
bits. The probe uses `/usr/bin/ssh` directly with:

- `BatchMode=yes`;
- public-key authentication only;
- `StrictHostKeyChecking=yes`;
- `UpdateHostKeys=no`;
- one bounded connection attempt; and
- a fixed remote command of `/usr/bin/true`.

The gateway-to-target leg is an explicit SSH stdio forward. No password,
FileVault recovery material, SSH agent socket, shell payload, route mutation or
host-key enrollment is supplied by the probe.

## Result states

The result schema is `mastermind.external_recovery_readiness/v1`.

| State | Meaning |
|---|---|
| `READY` | The gateway and target both accepted the existing public-key recovery identity. |
| `HUMAN_RECOVERY_REQUIRED` | The gateway worked and the target SSH service was reached, but target public-key authentication was unavailable. This is compatible with the macOS FileVault preboot environment, but can also mean target `authorized_keys` drift. The probe does not guess which. |
| `NOT_READY` | A known gateway/target DNS, route, host-key, connection or gateway-auth failure makes the recovery journey unavailable. |
| `UNKNOWN` | The bounded observation failed in a way the closed classifier does not recognize. |

Exit codes are `0` for `READY`, `3` for
`HUMAN_RECOVERY_REQUIRED`, `4` for `NOT_READY`, `5` for `UNKNOWN`,
and `65` for a refused input.

The report deliberately contains no hostname, user, identity path, raw SSH
stderr or secret. A target key-auth refusal is not projected as "host offline."

## FileVault boundary

On supported Apple-silicon/macOS generations, Remote Login can expose the
preboot FileVault unlock path after a restart while the encrypted data volume
is still unavailable. During that state the normal per-user SSH configuration,
`authorized_keys`, Tailscale, Screen Sharing and user LaunchAgents may not be
available yet.

The external probe must never submit a password or recovery key. If the state is
`HUMAN_RECOVERY_REQUIRED`, an authorized human may use an attended SSH session
through the already-proven gateway and type the local Mac password directly
into that terminal. Never paste that password into chat, logs, scripts, issue
comments, CI variables or the probe.

A FileVault-on Mac therefore has a deliberate human ceremony after a cold
restart. If the business requirement is **zero-human recovery after reboot**,
that is not a monitoring or daemon problem: the Chairman must make the existing
security tradeoff described in `HOST_PREREQUISITES.md` (for example, leaving
FileVault off on a physically controlled always-on host). Do not silently
weaken disk encryption to make a readiness check green.

## Post-unlock recovery boundary

A successful FileVault preboot unlock does not imply that a normal Aqua
console session exists. Immediately after unlock, the normal OS may expose
Remote Login, Screen Sharing/Remote Management, system NetworkExtensions and
other boot services while the console user is still `root` and the
`gui/<uid>` launchd domain is absent.

Treat that state as a normal recovery phase, not proof that a per-user service
installation is corrupt:

1. re-run the external route probe and require normal public-key SSH auth to
   return;
2. verify the host-local recovery profile before admitting heavy work;
3. verify boot/system services separately from user LaunchAgents;
4. never repeatedly `launchctl bootstrap gui/<uid>` when that GUI domain does
   not exist;
5. if an already-reviewed per-user recovery connector has a fixed installed
   runner, an attended operator may start that exact runner directly as the
   owning user to regain temporary control-plane access; do not invent a new
   service, credential, launch label or persistence path;
6. for a headless Mac that has been deliberately qualified for pre-login
   Desktop Commander recovery, prefer one system-domain LaunchDaemon that runs
   the existing fixed runner as the owning user. Preserve the existing device
   identity/session store; this is a launch-domain migration, not a second
   remote bridge or credential;
7. when that system owner is installed, remove the active per-user LaunchAgent
   definition so a later Aqua login cannot create a duplicate bridge. Keep a
   rollback copy, but do not leave both persistence definitions active;
8. prove the pre-login owner while no normal GUI login exists: the system job is
   `running`, its Desktop Commander process has the expected uid and parent
   identity, it carries no inherited `SSH_CLIENT`/`SSH_CONNECTION`, the
   remote device is reachable, and one controlled SIGTERM produces a new
   launchd-owned pid that reconnects without operator intervention;
9. direct vendor stdout/stderr to `/dev/null` or another reviewed bounded sink.
   Vendor console output can contain complete tool arguments/results and must
   not become an unbounded recovery log.

A host without that qualified system owner remains on the older attended
recovery path until a GUI session exists. Do not claim a normal user LaunchAgent
can provide pre-login recovery.

### Low-swap / watchdog incident handling

When a reboot follows repeated Jetsam `low-swap` events or a watchdog panic,
do not classify the incident as a network outage merely because Tailscale,
Screen Sharing and user LaunchAgents disappear behind FileVault.

Before restarting heavy workloads:

- preserve the panic/Jetsam evidence;
- run the canonical host-recovery readiness profile and require the disk-free
  floor to pass;
- restore reviewed power policy such as AC sleep/autorestart through its
  existing privileged owner when drift is proven;
- recover control-plane transport and verify it independently;
- inspect current memory and swap state rather than assuming the pre-crash
  pressure still exists after reboot; and
- keep workload/admission remediation with the existing Capacity/physical
  resource owners. This runbook does not create a local process-killing
  watchdog or new host scheduler.

A passing post-reboot readiness report proves the host is again eligible for
recovery use. It does not explain or erase the workload pressure that caused
the reboot.

### Provider process-storm containment

If incident evidence shows one already-owned provider execution growing an
abnormal process tree, contain that failure inside the existing process owner
rather than adding a host-wide killer daemon.

The process owner should:

- keep the provider in its existing private process group/session;
- sample live owned membership while the provider is still running instead of
  waiting only for timeout or leader exit;
- enforce a reviewed finite member ceiling;
- terminate through the same identity-verified cleanup path already used for
  timeout/cancellation;
- report a distinct runtime-safety refusal rather than an admission/full-capacity
  code that could trigger automatic spill or retry; and
- preserve terminal whole-session reconciliation so descendants cannot survive
  merely because the provider leader exits.

A process-cardinality fuse is one containment layer, not proof that host memory
pressure is impossible. Keep host-capacity, memory/swap and disk-headroom
admission with their existing owners; do not duplicate them inside this
recovery runbook.

### Unprovable execution-host quarantine

If a host's execution runtime, active-marker directory, or other required
pre-effect evidence cannot be read within the bounded recovery probe, do not
write that runtime and do not infer that the host is idle.

Use the incumbent placement registry to remove only the execution eligibility
that depends on the unprovable surface when that registry already models roles
separately. Preserve unrelated duties such as CI or data service. Apply the
hold to healthy dispatch origins with compare-and-swap/readback rather than
copying an entire host registry between machines that may have legitimate
host-local differences.

The hold may be released only after the affected host can again prove all of:

1. its active execution census;
2. the exact required runtime identity or a reviewed installation of it;
3. the normal host admission/readiness gates; and
4. routing eligibility after the role is deliberately restored.

A timeout reading the affected host never authorizes an alternate carrier,
blind runtime overwrite, or whole-host decommission.

### Deployment is not durable publication

A runtime hash read back on live hosts proves those deployed bytes only. It
does not prove that an immutable support release, source repository, installer,
or other durable publication owner contains the same bytes.

Before claiming a runtime hardening durable, separately verify the incumbent
publication artifact and its exact file digest. If the publication mechanism or
digest ceremony cannot be recovered, do not fabricate a new release identifier
or reverse-engineer a guessed publication format. Preserve the verified live
state, keep any stale-publication regression risk explicit, and return the
publication step to its existing custody owner.

## Acceptance discipline

A departure/readiness claim for an externally managed home Mac is valid only
when the applicable local readiness report and this external route report are
both current. A passing result is evidence for the exact observed route only;
it does not prove Worker/Fabric/provider readiness.

Do not make one-off SSH aliases the sole recovery path. Stable operator
configuration may provide convenience aliases, but the acceptance probe must
also be runnable from explicit, current route coordinates so alias drift cannot
turn a healthy gateway into a false outage.

When a route fails:

- host-key refusal is a trust/identity failure, not permission to auto-enroll a
  new key;
- gateway auth refusal is a gateway recovery defect;
- target key-auth refusal after a healthy gateway is a human-recovery boundary,
  not proof of target power/network loss;
- transport ambiguity never authorizes a password retry, key replacement,
  FileVault mutation, or alternate-account bypass.

This journey is read-only. Any repair of power policy, Remote Login, FileVault,
SSH keys, gateway configuration or services stays with its existing reviewed
owner and authority boundary.
