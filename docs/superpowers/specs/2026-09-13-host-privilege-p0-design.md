# Host Privilege P0 — Unattended Executive Administration Design

**Operation:** `mastermind-host-privilege-p0-20260913-sol-001`  
**Protected source pin:** `9ed16bf0fcc5b47e870350ff2413ff5c8c73b447`  
**Skillpack:** `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap major 1  
**Pilot host:** Mac Studio with existing `MastermindExecutive` installation and `_mastermind_ops` membership  
**Capability target:** `NOT_BUILT -> BUILT_NOT_PROVEN -> PROVEN_LIVE`

## Outcome

Normal Web CEO and Codex CEO operation must not stop merely because a bounded Mastermind host action requires root. The Chairman must never provide, store, paste, or expose the macOS administrator password to a model, MCP server, environment variable, repository, shell history, or 1Password-readable agent context.

P0 establishes a one-time human trust bootstrap followed by passwordless, unattended execution of a small set of already-governed Executive OS administrative operations. Raw `sudo` remains blocked in Desktop Commander. Executive OS remains lifecycle/admission authority; this component is only a host privilege adapter.

## Existing owners reused

- Executive OS owns Job/Attempt lifecycle, CEO admission, autonomy state and its root-only `autonomy_control.py` transaction semantics.
- The installed Executive release and root-owned `control.json` select the exact release SHA. The caller may not choose a release, source root, executable, launchd label, plist, account, or privilege policy.
- `_mastermind_ops` remains the operator identity group. P0 creates no second operator identity.
- macOS `sudoers` remains the operating-system privilege grant mechanism. P0 creates no daemon, root shell server, permission database, queue, lifecycle store or retry plane.
- Remote Desktop Commander remains host transport and continues to deny top-level `sudo`; issue #507 retains its own managed/unmanaged transport ownership.

## Architecture

A root bootstrap installs three root-owned artifacts:

1. `/Library/Application Support/MastermindExecutive/admin/mmx_admin_bridge.py` — the validating privileged adapter.
2. `/usr/local/bin/mmx-adminctl` — an unprivileged client that invokes `/usr/bin/sudo -n` only for the fixed bridge path.
3. `/etc/sudoers.d/mastermind-executive-admin` — one `NOPASSWD` grant from `%_mastermind_ops` to the fixed bridge executable only.

The bridge runs with EUID 0, proves macOS, proves the original sudo caller is a member of `_mastermind_ops`, reads the installed SHA from the root-owned Executive control config, validates the corresponding immutable release identity, and dispatches only a closed verb set.

The client contains no secret. A model invoking `mmx-adminctl` never sees or handles an administrator password. Desktop Commander can continue blocking `sudo` because the transport-visible command is `mmx-adminctl`; the nested non-interactive sudo call is fixed inside a root-owned executable installed during bootstrap.

## P0 verb set

### `status`

Read-only. Returns structured JSON containing schema version, caller, installed release SHA, bridge version, supported actions, and whether the required Executive services are loaded. It never changes host state.

### `autonomy status`

Read-only. Invokes the installed release's existing `ops/executive_os/autonomy_control.py status` with the root-derived installed SHA. The caller cannot supply `--expected-sha`.

### `autonomy arm`

Mutating, but authority remains in the existing autonomy controller. The bridge accepts only the existing admission evidence coordinates:

- `--gate-b-receipt` — must resolve to a direct regular file below `/Library/Application Support/MastermindExecutive/` or `/var/db/mastermind-executive/`; the underlying controller still requires its root ownership/mode/content and exact-SHA validation.
- `--expected-credential-kind` — one of the controller's existing closed values.
- `--workspace-binding-class` — forwarded but remains equality-checked against the existing protected constant.
- `--credential-expires-at` — forwarded and cross-checked by existing provider-readiness evidence.

These values are evidence selectors or mismatch checks; none may mint authority. The installed SHA is always root-derived. The existing transaction/rollback/EFFECT_UNKNOWN semantics remain the mutation owner.

### `autonomy disarm`

Mutating through the existing transaction-safe controller with the root-derived installed SHA. No caller-selected path or release argument exists.

### `service ensure-ready`

Convergent lifecycle repair for exactly `com.mastermind.executive.worker.codex` and `com.mastermind.executive.control`. If the pair is already loaded and the existing Executive status reports a reconciled READY state, return `NOT_APPLIED`. Otherwise invoke only the installed release's fixed `service-control.sh start`, then re-read status. No arbitrary label, plist, domain, verb or shell is accepted.

### `service ensure-stopped`

Convergent lifecycle stop for exactly the same two services. If both are already absent, return `NOT_APPLIED`; otherwise invoke only `service-control.sh stop` and prove both are absent before returning `APPLIED`.

P0 intentionally has no `restart` verb. Repeating an uncertain restart could create a second effect. A later repair action may be admitted only with a pre-effect action identity and same-action reconciliation.

## Installed-release identity

The bridge must never trust a caller path. It reads `/Library/Application Support/MastermindExecutive/config/control.json` and requires:

- direct, non-symlink regular file;
- root owner;
- group `_mastermind_exec`;
- mode `0440` and no filesystem ACL;
- exact `proof_base_sha` shape of 40 lowercase hexadecimal characters;
- direct release directory `/Library/Application Support/MastermindExecutive/releases/<sha>`;
- release identity accepted by the same protected manifest/identity checks used by the existing autonomy owner.

All child executable paths are then constructed beneath that verified release.

## sudo caller boundary

The bridge requires `SUDO_USER` and `SUDO_UID` to describe one non-root local user. It resolves that account through the local directory and verifies supplementary membership in `_mastermind_ops`. A missing, root, inconsistent, or non-member caller is refused before action.

The sudoers grant is only:

`%_mastermind_ops ALL=(root) NOPASSWD: <fixed bridge launcher>`

No `NOPASSWD: ALL`, shell, interpreter, editor, package manager, `launchctl`, `chmod`, `chown`, `cp`, `tee`, `env`, or user-writable script is granted. The bridge and launcher must be root:wheel, non-symlink, single-link regular files, mode `0755`, with no group/other write bits or ACLs.

## Client behavior

`mmx-adminctl` has a closed parser mirroring the P0 verbs. It always uses `/usr/bin/sudo -n` so a missing/invalid installation fails immediately rather than waiting for a password prompt. It never accepts a command string, executable path, environment injection, working directory, shell flag, or arbitrary passthrough after `--`.

The client emits exactly one JSON document to stdout. Failures also produce structured JSON with an explicit code. Exit codes distinguish success, refusal, and uncertain effect without hiding stdout/stderr from the existing mutation owner.

## Effect and failure semantics

Common effect truth remains exactly `NOT_APPLIED | APPLIED | EFFECT_UNKNOWN`.

- Read-only status operations return `NOT_APPLIED`.
- Existing autonomy arm/disarm results are mapped without changing their underlying transaction truth.
- Convergent service operations re-observe the target state before and after action.
- A timeout/lost child result followed by inability to prove the final state returns `EFFECT_UNKNOWN`; the client must not auto-retry that same mutator through another carrier.
- A privilege/setup failure returns `REFUSED` with `effect=NOT_APPLIED` when no child process was dispatched.
- macOS TCC/Full Disk Access, MDM/PPPC, SecureToken/FileVault and other human/OS consent gates are not spoofed as root capability. They return a stable `ADMIN_GATE_REQUIRED`/`HUMAN_OS_CONSENT_REQUIRED` classification for the attention layer.

## Installation and rollback

`ops/executive_os/install-admin-bridge.sh` is the one-time root bootstrap. It must:

1. require EUID 0 and Darwin;
2. require an already-installed, identity-valid Executive release and `_mastermind_ops` group;
3. copy bridge/client bytes only from an exact release root beneath `MastermindExecutive/releases/<sha>`;
4. install via temporary files plus atomic rename;
5. enforce root:wheel ownership, mode and ACL/link constraints;
6. render the sudoers fragment to a temporary root-only file and validate it with `/usr/sbin/visudo -cf` before atomic installation;
7. read back all installed bytes/metadata and print a non-secret receipt;
8. never weaken Desktop Commander configuration.

The same script supports `--uninstall`, removing only the exact P0 sudoers fragment/client/bridge after validating their identities. Uninstall never modifies Executive OS service data, receipts, accounts or transport.

The very first installation requires one Chairman-authorized root ceremony on the pilot Mac because no safe unattended privilege path exists before P0 is installed. After that, normal P0 actions require no password or click.

## Security falsifiers

Tests must prove refusal of:

- arbitrary verbs and extra positional arguments;
- caller-supplied `--expected-sha`, executable, release root, service label or plist;
- gate-B traversal/symlink/outside-root paths;
- malformed/unsafe control config identity;
- non-`_mastermind_ops` caller;
- user-writable bridge/client bytes;
- sudoers content containing `ALL` command authority beyond the one bridge path;
- shell metacharacters treated as data rather than evaluation;
- ambiguous service state reported as `EFFECT_UNKNOWN` rather than silently retried;
- attempts to invoke TCC/privacy mutation as a P0 root verb.

## Production proof

P0 is `PROVEN_LIVE` only when all of the following occur on Mac Studio through the real Web CEO host path:

1. one-time root install completes and readback proves fixed root-owned artifacts;
2. Desktop Commander still reports raw `sudo` blocked;
3. ordinary `chriswong` executes `mmx-adminctl status` successfully;
4. `mmx-adminctl autonomy status` succeeds without a password prompt;
5. one admitted convergent service action proves either `NOT_APPLIED` or `APPLIED` and final state readback;
6. a forbidden verb is refused with `effect=NOT_APPLIED`;
7. a non-member test identity cannot use the sudoers grant, if a safe existing test identity is available; otherwise the parser/membership falsifier remains hermetic and the absence of a test identity is recorded;
8. no administrator password, 1Password item, secret, or raw sudo capability appears in logs or receipts;
9. Executive OS and Remote Desktop Commander canonical ownership remain unchanged.

Codex production proof follows by allowing the single `/usr/local/bin/mmx-adminctl` client in Codex command rules; raw sudo remains denied.

## Non-goals for P0

P0 does not provide arbitrary root shell, arbitrary package installation, arbitrary application installation, arbitrary filesystem ownership/permission mutation, MDM enrollment, TCC bypass, FileVault/SecureToken administration, password retrieval, 1Password secret retrieval, generic service management, generic launchd, a second Executive OS, or a second permission/retry/evidence control plane.

Those recurring administrative jobs may become later typed verbs only after they are concrete, bounded, independently useful capabilities with existing-owner authority and loss-safe reconciliation.
