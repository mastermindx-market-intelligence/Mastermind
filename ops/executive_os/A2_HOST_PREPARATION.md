# A2 host preparation

Install the reviewed exact release and its control/worker configs first. Run
`sudo /bin/bash <installed-release>/ops/executive_os/prepare-a2-agent-relay-host.sh --release-root <installed-release>`
from the canonical root-owned release. The script verifies the fixed host identities and paths, then calls the existing autonomy controller before creating any identity or directory.

The controller's `a2-disable-prepare --expected-sha <installed-sha>` requires an unloaded Agent Relay and absent enrollment/service artifacts. It uses the existing global `AUTONOMY_TRANSACTION` archive to record `A2_DISABLE_DISPATCHED` before its single fixed-label disable. It always reconciles the unloaded state and exact persistent disabled override after a command failure or lost response. A positive postcondition completes the transaction; an uncertain result retains it.

After `EFFECT_UNKNOWN`, use the same installed `autonomy-control.sh a2-disable-prepare-reconcile --expected-sha <same-installed-sha>`. This command only reads the existing effect and its archived config identity. It never issues another disable, restores configs, or deletes an unresolved marker. Do not rerun disable manually or remove the marker. A foreign transaction, changed config, loaded service or unreadable/absent/false override stays unresolved.

After reconciliation succeeds, rerun host preparation to finish any missing fixed principal/directories. An already-disabled unloaded Relay introduces no additional disable. Preparation does not enroll credentials or start the service. Continue through the existing human-TTY A2 enrollment and reviewed service activation sequence.


## Persisted A2 socket / enrolled-host migration

The Agent Relay's socket parent is a **persistent** root-provisioned directory:
`/var/db/mastermind-agent-relay/socket` (UID 457, GID 457, mode 0710);
the socket is `agent-relay.sock` (UID 457, GID 457, mode 0660).
Its root-owned ancestor `/var/db/mastermind-agent-relay` retains mode 0711.
Never rely on the old volatile `/var/run/mastermind-agent-relay` parent after
reboot. The Agent Relay stays unprivileged and must not repair a foreign or
symlinked socket parent. Its server safely refuses a live/foreign socket;
on restart it may remove only an inert, exact-owner stale socket inode.

For **already-enrolled** hosts only, the existing root host-preparation owner
provides the bounded, credential-free `--ensure-enrolled-socket-parent` option
on the exact installed, reviewed release. It verifies the fixed existing A2
account/group, root/runtime/home directories, and the existence plus metadata
(not contents) of the enrolled token/config/plist. It may create **only** the
missing persistent socket directory. It never calls the A2 disable-preparation
transaction, modifies accounts/credentials, changes the launchd job or
restarts the Relay. Its foreign file, mode, ACL and symlink checks fail closed;
a failed or ambiguous create must be reconciled on the same host/command owner.

### Governed production cutover (not a bootstrap or reboot instruction)

1. Merge the exact reviewed source only after independent security review,
   CI and required merge-queue checks. Install the accepted release via the
   existing Executive release owner; never run a root script out of a draft PR.
2. Before changing the running Relay, verify its installed release SHA,
   launchd label/UID/GID, old socket listener and existing controller
   `terminal_return_armed` state. The installer migrates the **exact**
   historical controller socket path only while the feature is disarmed;
   it refuses an armed or foreign-path source.
3. As root, run the new installed
   `prepare-a2-agent-relay-host.sh --release-root <installed-new-release> --ensure-enrolled-socket-parent`.
   Re-attest `/var/db/mastermind-agent-relay/socket` as `457:457:710`
   with no ACL or symlink. This is preparatory filesystem work; it does
   not prove a new socket listener.
4. Through the existing reviewed service lifecycle owner, stop and prove
   the Relay unloaded/disabled. Using the **new installed exact release's**
   `a2_agent_relay_enrollment.py rebind-release` operation, atomically
   migrate only the config/plist pair. The transaction accepts either the
   new exact canonical pair or the one exact legacy socket-path pair as a
   read-only preimage, not a mixed generation; it never reads the token or
   starts services. Any uncertain rename/rollback keeps the original
   effect fence; no blind retry.
5. Verify that both enrolled A2 files identify the new release and durable
   socket, and the installed controller config points to that same socket.
   Start the A2 service **once** through its existing lifecycle owner, then
   prove `launchctl` running, a real Unix listener, exact ownership/mode,
   and a permitted read-side client interaction. Do not interpret a socket
   path alone as service liveness.
6. Reboot only through a separate authorized host maintenance/remote-recovery
   window, after the control-host recovery-readiness observer reports READY.
   Confirm service auto-start, durable directory ownership and real socket
   client success **without** human mkdir, re-enrollment or kickstart.
   Preserve before/after launchd run count and release identity as proof.
7. If any gate fails, leave acceptance open and reconcile the specific
   installed generation/effect. Do not force-install an older release
   over a successful new A2 generation: old renderers cannot certify the
   new config/plist pair. The installed successor's separately reviewed
   **reverse-rebind-release** command can restore an exact historical
   volatile-socket enrollment pair, but only when the native A2 service
   is unloaded/disabled, the controller return path is disarmed, the
   previous sealed release manifest verifies, and the previous config/plist
   hashes are supplied from a previously captured owner-only backup.
   It uses the existing A2 token-metadata-only lock/CAS transaction;
   it never reads, rewrites or re-enrolls the token. It requires:
   --expected-bot-user-id, --expected-current-release-sha,
   --expected-previous-release-sha, --expected-previous-tree-sha,
   --expected-previous-config-sha256, and
   --expected-previous-plist-sha256. The previous generation must
   correspond to the exact reconstructed historical /var/run A2 pair,
   with the shared scope set and W3C disabled. It is NOT a generic
   downgrade, does NOT select a release, and cannot reverse an armed W3C
   generation. A service start or other control/identity drift freezes
   publication for same-carrier reconciliation; do not retry blindly.
   The full Executive/C1/control restart and any release selection remain
   governed by their separate original owners and admission receipts.
   Rolling forward with a reviewed fix is preferred over an unreviewed
   overwrite. Reboot and app retirement remain separate effects.

This migration does not activate `terminal_return_armed`, W3C, a Job/Attempt,
new broker, watcher or transport plane. A passing source test or green CI
is not the reboot recovery receipt.
