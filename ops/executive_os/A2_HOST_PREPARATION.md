# A2 host preparation

Install the reviewed exact release and its control/worker configs first. Run
`sudo /bin/bash <installed-release>/ops/executive_os/prepare-a2-agent-relay-host.sh --release-root <installed-release>`
from the canonical root-owned release. The script verifies the fixed host identities and paths, then calls the existing autonomy controller before creating any identity or directory.

The controller's `a2-disable-prepare --expected-sha <installed-sha>` requires an unloaded Agent Relay and absent enrollment/service artifacts. It uses the existing global `AUTONOMY_TRANSACTION` archive to record `A2_DISABLE_DISPATCHED` before its single fixed-label disable. It always reconciles the unloaded state and exact persistent disabled override after a command failure or lost response. A positive postcondition completes the transaction; an uncertain result retains it.

After `EFFECT_UNKNOWN`, use the same installed `autonomy-control.sh a2-disable-prepare-reconcile --expected-sha <same-installed-sha>`. This command only reads the existing effect and its archived config identity. It never issues another disable, restores configs, or deletes an unresolved marker. Do not rerun disable manually or remove the marker. A foreign transaction, changed config, loaded service or unreadable/absent/false override stays unresolved.

After reconciliation succeeds, rerun host preparation to finish any missing fixed principal/directories. An already-disabled unloaded Relay introduces no additional disable. Preparation does not enroll credentials or start the service. Continue through the existing human-TTY A2 enrollment and reviewed service activation sequence.
