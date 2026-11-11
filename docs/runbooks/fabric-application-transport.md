# Fabric application transport — closed APPLICATION reverse on the incumbent Chisel owner

This runbook describes the **source** candidate that adds one closed
APPLICATION-purpose reverse to the existing sealed Chisel transport owner, so a
VPS application service can reach the native ordinary-inference endpoint
(`127.0.0.1:4142`) over a private reverse.

It is a source candidate only. Nothing here is installed, granted, started,
reloaded, qualified or proved. The operator commands below are **documented,
never executed** by this candidate. Root alone integrates, releases, qualifies
the runtime and proves one actual private Admin/Brain turn.

## What this candidate is not

- It is not a new transport owner, a second Chisel server, a new Caddy route, a
  worker-scoped SSH tunnel, a proxy or a SOCKS remote.
- It does not touch the incumbent OS relay (`com.mastermind.executive.os-public-tunnel`,
  `mastermind-os`, target `8443`), the OS config, the OS credential, the VPS
  `mm-chisel-server.service` unit arguments, `/etc/chisel/server.key`, the Go
  `go_ctl.sh` lifecycle owner, or any A/B/C/GLM/H/J/consumer/installer source.
- It grants no model permission, no product eligibility and no application
  admission. Chisel authentication is not application admission.
- It creates no per-completion job or lease.

## Closed contract

| Item | Value |
|---|---|
| Reverse (client argv) | `R:127.0.0.1:50142:127.0.0.1:4142` |
| Server ACL remote | `^R:127\.0\.0\.1:50142$` (anchored, this identity only) |
| Server | `https://146-190-142-17.sslip.io`, TLS verification on, exact pinned fingerprint |
| Transport identity | `mastermind-fabric-app:<fresh URL-safe secret>` |
| Client config | `/Library/Application Support/MastermindExecutive/config/application-tunnel.json` |
| Client credential | `/Library/Application Support/MastermindExecutive/config/application-tunnel.auth` (root-private, `0400`) |
| Client label | `com.mastermind.executive.fabric-application-tunnel` |
| Client binary | `/Library/Application Support/MastermindExecutive/transports/chisel/<binary_sha256>/chisel` |
| Schema | `mastermind.application_tunnel.v1` (config), `mastermind.application_tunnel_control.v1` (operation) |

`50142` is a **proposed source constant**, not an observed available or
installed grant. A collision is refused. The port is never searched and never
replaced by another choice.

The credential reaches Chisel only through the `AUTH` environment variable. It
never appears in argv, in the plist, in a public receipt, in a log or in an
error. The config carries no port, host, executable, command, proxy or
credential selector; the CLI exposes no target path, purpose or endpoint
selector either.

The Chisel authfile is a `map[user:pass][]remote-regex`. The merge adds exactly
one key with exactly one anchored remote and preserves every incumbent user and
every incumbent ACL value byte-for-byte in meaning. An incumbent wildcard
(`""` or `"*"`), an incumbent grant that already authorizes `50142`, a
conflicting existing `mastermind-fabric-app` identity, a duplicate JSON key, a
non-finite value, a malformed regex and a key without `user:pass` are all
refused without leaking the key.

## Source files

| File | Role |
|---|---|
| `ops/executive_os/os_tunnel_entry.py` | incumbent file; **additive only** — the OS constants, defaults and `main` are unchanged |
| `ops/executive_os/application_tunnel_entry.py` | thin entry; selects the APPLICATION purpose internally |
| `ops/executive_os/application_tunnel_control.py` | finite stage / apply / reconcile / lifecycle owner and CLI |
| `ops/executive_os/com.mastermind.executive.fabric-application-tunnel.plist.template` | closed launchd definition |
| `tests/test_application_tunnel_entry.py` | compiler and entry proofs |
| `tests/test_application_tunnel_control.py` | qualification, authfile, stage, apply and reconcile proofs |
| `tests/test_application_tunnel_lifecycle.py` | start/stop command-discipline proofs |
| `tests/application_tunnel_ci/` | isolated Linux root fixture and required zero-skip proof |

`ops/executive_os/application_tunnel_control.py` reuses the incumbent
`os_tunnel_entry._read_sealed`, `os_public_edge_publication.canonical/decode/
PrivateDirectory/private`, `os_release_assets` custody helpers,
`install_source_policy.validate_acceptance_source` and
`release_manifest.verify`. It adds no second release store, no installer and no
generic deployment framework.

## Qualification: what the operator must still supply

The installed Chisel **client** and **server** binary digests, versions and
builds are currently **UNPROVEN**. The qualification record is supplied to
`stage` as a sealed file and is bound into the operation; it is not a
catalogue or an entitlement registry.

```
{
  "schema": "mastermind.application_tunnel_qualification.v1",
  "server_fingerprint": "<43 base64 characters + '='>",
  "client_binary": {"sha256": "<64 hex>", "version": "1.12.0", "build": "<observed>"},
  "server_binary": {"sha256": "<64 hex>", "version": "1.12.0", "build": "<observed>"},
  "semantics": {"authfile_rename_reload": true, "new_tunnel_acl_refresh": true},
  "evidence": {
    "repository": "https://github.com/jpillora/chisel",
    "commit": "<40 hex>", "tree": "<40 hex>",
    "paths": ["share/settings/users.go", "share/settings/user.go",
              "share/settings/remote.go", "server/server_handler.go"],
    "files": {"<path>": "<sha256 of that file at that commit>"},
    "mode": "source-tree", "source_root": "<absolute checkout of that commit>"
  },
  "custody": "root-owned source attestation; not a remote signature"
}
```

A version string alone is **not** qualification. The record must also pin the
exact upstream source commit and the per-file digests that establish the two
semantics the server must have:

- **authfile rename reload** — the incumbent server watches the authfile's
  parent directory and reacts to write, create, rename and remove, so an
  atomic rename-replacement is reloaded. The
  [official v1.12.0 release](https://github.com/jpillora/chisel/releases/tag/v1.12.0)
  documents reliable rename reload and ACL refresh for new tunnels.
- **per-new-tunnel ACL refresh** — the server resolves the user's remotes
  against the live user index at handshake time, so a reloaded authfile
  governs new tunnels.

`mode: "attested"` is accepted only when `source_root` is null; the receipt
then records that the upstream binding was operator-attested rather than
re-verified against a checkout. `mode: "source-tree"` re-reads the exact
upstream bytes at the pinned commit and refuses any drift.

Missing, older-than-`1.12.0`, unverified or drifted semantics refuse **before**
any authfile mutation. The shared server is never restarted, reloaded
speculatively or upgraded.

## Operator sequence (documented, not executed here)

All seven commands are root-only. Invoke the exact approved control script
with isolated, no-bytecode Python. The closed target paths are not selectable
on the command line.

```
# 1. Native host — capture the original operation (one credential, created once).
python -I -B <sealed-release>/ops/executive_os/application_tunnel_control.py stage \
    --source-repo <clean protected checkout> --source-sha <40 hex> \
    --release-root <installed sealed release> --release-commit-sha <40 hex> \
    --release-tree-sha <40 hex> --qualification <sealed qualification file>

# 2. VPS host — merge exactly one ACL into the private authfile.
#    The bundle is carried by the EXISTING authorized deploy carrier.
python -I -B <approved-source>/ops/executive_os/application_tunnel_control.py apply-server \
    --bundle <carried bundle> --expected-digest <sha256>

# After interruption, inspect the SAME original server operation. This command
# may fill an exact committed missing receipt; it cannot write another grant.
python -I -B <approved-source>/ops/executive_os/application_tunnel_control.py reconcile-server \
    --bundle <same carried bundle> --expected-digest <same sha256>

# 3. Native host — install only the config, credential and plist.
python -I -B <sealed-release>/ops/executive_os/application_tunnel_control.py apply-client \
    --server-receipt <receipt returned by the carrier>

# 4. Native host — exactly one bounded launchctl operation.
python -I -B <sealed-release>/ops/executive_os/application_tunnel_control.py start-client \
    --server-receipt <receipt returned by the carrier>

# 5. Native host — read-only disposition of the original operation.
python -I -B <sealed-release>/ops/executive_os/application_tunnel_control.py reconcile \
    --server-receipt <receipt returned by the carrier>

# 6. Native host — exactly one bounded launchctl operation.
python -I -B <sealed-release>/ops/executive_os/application_tunnel_control.py stop-client
```

`apply-client` installs files; it does not start a service. `start-client`
requires the server grant receipt for the same operation and the same bundle
digest; a client install without the grant or without a qualified binary
cannot start.

## Distinguishing the states

| State | Evidence |
|---|---|
| staged | the private stage descriptor and its digest |
| file-applied | the target readback, per target, in the operation journal |
| service-started | original command custody, exact launchd arguments, positive PID and actual closed Chisel command/executable observation |
| tunnel-proven | **not** established by this candidate; requires a real private hop |
| application-proven | **not** established by this candidate; root owns the real Admin/Brain turn |

A file readback proves `GRANT_FILE_APPLIED` only. It does **not** prove that
the shared server reloaded, that a tunnel exists, that the application is
eligible or that inference works. The receipts say so explicitly
(`server_reload_proven: false`, `tunnel_proven: false`,
`application_proven: false`). Launchd and listener metadata is never transport
proof.

A successful stop does not settle A/B's in-flight provider effects; the receipt
records `provider_effects_settled: false`.

## Interrupted phases

Every phase writes its intent before its first effect and reads back after it.

- An exact original preimage means the target was not applied.
- An exact candidate plus the original durable intent may be reconciled
  without rewriting, without minting another secret and without repeating a
  command. A lost acknowledgement is recovered by readback.
- Foreign bytes, receipt corruption, lock loss, path/owner/inode swaps and
  uncertain ownership refuse. There is no automatic rollback that deletes
  another writer's file, no unstated retry and no new operation takeover.
- A pending or unknown `launchctl` outcome requires the original
  reconciliation. There is no second bootstrap, bootout, kickstart or PID kill.
- A concurrent stage, apply or start contends on the same purpose custody
  (`application-tunnel/purpose.lock`). The native root is the fixed Executive
  application-tunnel directory. The VPS root is `/etc/chisel/application-tunnel`,
  independent of where a bundle was delivered. These are the two local phases
  of the same operation, with no cross-host atomicity claim.

The credential is created **once**. A repeated stage reuses the original
secret; a supplied different secret is refused as a rotation. Intent precedes
minting. An interrupted intent with no retained credential refuses regeneration.

Settled client target receipts retain their exact file identity. An identical
replacement inode is a conflict. An original committed target whose receipt
was lost remains `COMMITTED_RECEIPT_MISSING` until its same apply continuation
records the readback without rewriting. First apply requires every captured
preimage before creating intent; an independently appearing target is not adopted.

The VPS qualification checks the actual running `/proc` executable hash and
process start identity as well as the installed binary/version and systemd
arguments. Replacing the disk binary does not qualify an older running image.
The application runtime reader uses the existing descriptor ACL observer for
its config, private credential, binary and directory chain. The incumbent OS
reader retains its default behavior; the application path explicitly adds the
ACL observation and same-release filesystem helper.

## What remains unproven for root

1. The installed Chisel client and server binary SHA-256, exact observed
   version and build identity on the native host and on the VPS.
2. The independently observed server key fingerprint for the incumbent
   `146-190-142-17.sslip.io` endpoint.
3. The server-side observation that the shared server actually reloaded the
   replaced authfile and admits the new tunnel. This candidate never restarts,
   reloads or upgrades the shared server, and never claims the reload.
4. The real private hop and the first actual application request. Root
   qualifies one actual private Admin/Brain turn after A/B/C/D and the
   consumers compose.

## Source tests

The suites exercise the real compiler, control and lifecycle functions with
real file hashes, real locks, real atomic writes, a real strict JSON parser, a
real clean protected Git checkout, an exact-SHA sealed release and a real
upstream source checkout. Only the OS service/process observations and the
`launchctl` commands and negative UID/ACL observations are substituted. Actual
file reads, locking, staged/installed inode identity and Linux running-image
observation are exercised.

The mutation path requires root, and the incumbent sealed-path policy refuses a
world-writable ancestor, so the temporary fixtures live under a root-owned,
non-world-writable base rather than a world-writable temporary directory.

```
# In the isolated root fixture (never host sudo):
python -B tests/application_tunnel_ci/require_proof.py
```

The required CI step builds the pinned Ubuntu fixture with Python/pytest/git,
mounts only tracked source read-only, drops every capability, disables network,
and uses disposable `/tmp` and `/fixture` mounts. The proof helper requires
named positive cases, a successful pytest exit and zero JUnit failures/errors/skips.

Source tests establish no installed launch, no grant and no permission to
widen one.


## Ubuntu1 role services use the existing home client

The v2 role aliases bind on the VPS. Ubuntu1 needs its own local forwards to
reach them. The same control module now provides a fixed home-client phase
for the existing mm-chisel-home.service; it does not install another tunnel.

The original home credential is committed by digest and resolved privately
against the VPS's existing authfile. Only the two anchored normal destinations
`127.0.0.2:50142` and `127.0.0.3:50142` are added. Its SSH reverse and unrelated
grants are preserved. Source qualification covers the exact home binary and
normal-forward ACL semantics in addition to the original reverse contract.

Use stage-home, apply-home-server, reconcile-home-server, apply-home-client,
restart-home-client and reconcile-home-client through this existing owner.
The [host integration sequence](../../integrations/hermes_application_fabric/HOST_INTEGRATION.md#ubuntu1-local-application-hop-through-the-existing-home-client)
defines ordering, original v2 custody, active-stream refusal and the single
restart boundary. It also links the real binary proof across three separate
network namespaces. The home phases never reload the server or systemd's unit
definitions; source proof does not activate a held role service.
