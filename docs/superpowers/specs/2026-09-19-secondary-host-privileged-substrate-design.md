# Secondary Host Privileged Substrate Design

**Status:** DRAFT / HOLD / BUILT_NOT_PROVEN / PRODUCTION_INERT  
**Operation:** `fleet-secondary-privileged-substrate-20260919-sol-001`  
**Protected basis:** `733389933e605e508517732fb6c69b6c18b7fef6`, `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap 1.

## Outcome

Give one already-approved non-control home Mac the minimum existing root actuator needed to perform governed host remediation without installing a second Executive control plane.

The first consumer is PR #846's fixed charger-power action. This preparation is not Fleet enrollment, Worker readiness, Capacity admission, MH1 gateway readiness, provider readiness, or permission to execute a Job.

## Canonical owner composition

This path creates no new lifecycle or authority plane. It composes existing owners:

- `bootstrap-host.sh` owns creation of the reviewed local service/operator principals and is a prerequisite, not reimplemented here;
- `provision-python-runtime.sh --verify-only` owns the exact PSF Python 3.12.10 runtime receipt and bytes;
- `install_source_policy.py` owns exact source admission;
- `release_manifest.py` owns immutable release identity;
- the existing privileged-action broker remains the only root effect owner and receipt/status owner;
- PR #829 remains the read-only secondary-host anti-duplication/physical readiness owner;
- PR #846 remains the only new power-setting semantic action.

## Anti-duplication law

Before any persistent mutation and again after the broker is armed, all three central labels must have neither an installed `/Library/LaunchDaemons/<label>.plist` nor a loaded system launchd job:

- `com.mastermind.executive.control`
- `com.mastermind.executive.mcp`
- `com.mastermind.executive.sol-state-relay`

The preparation script may never disable, boot out, install, enable, bootstrap, or otherwise mutate those labels. Finding one is a role error and a hard refusal, not something this script repairs.

Only `com.mastermind.executive.privileged` may be mutated by launchctl.

## Closed input surface

The script accepts only:

- absolute `--source-repo`;
- exact lowercase 40-hex `--expected-sha`;
- existing `--operator-user` already admitted by `_mastermind_ops`.

There is no caller-selected host, launchd label, executable, command, action, power key/value, Worker, provider, socket, certificate, endpoint, or retry field.

The script must execute from the same direct Git checkout named by `--source-repo`; HEAD must equal the expected SHA and the tree must be clean. Before any root helper is executed from that checkout, the source parent must be root:wheel/non-writable and the checkout must contain no non-root-owned object, group/other-writable object, hard-linked file or filesystem ACL. This prevents a non-root source race across the privilege boundary. The existing source-policy helper must then accept the exact source before mutation.

## Prerequisites

This slice does not create principals or provision Python. The existing host bootstrap and runtime provisioner must already have established:

- `_mastermind_exec` UID/GID 450;
- `_mastermind_ops` GID 453 with the named operator as a member;
- the pinned root-owned PSF Python 3.12.10 runtime and provenance receipt.

Homebrew Python is not a substitute for the Executive runtime.

## Installed surface

For one exact immutable release, and no other Executive service, the script may create/reconcile:

- `/Library/Application Support/MastermindExecutive/releases/<sha>` plus the existing release manifest; a new release is manifested and verified in a private staging directory before one atomic publish to the versioned release path;
- root-only `config/privileged-broker.json` bound to that exact release;
- stable non-root `bin/mmx-admin` status client launcher;
- stable non-root `bin/mmx-secondary-host-power` launcher bound to PR #846's exact-release wrapper;
- `/Library/LaunchDaemons/com.mastermind.executive.privileged.plist`;
- the existing privileged receipt/log/runtime directories and launchd socket.

Existing artifacts are accepted only when their bytes and metadata exactly match the candidate generated from the requested release; mismatches refuse instead of being overwritten. Before completion, the failure trap removes only unpublished staging/temp artifacts and, if this run began broker arming, bootouts/disables only the privileged label. This slice is first-generation/same-generation reconciliation, not cross-generation upgrade authority.

## Arm and proof

The script may enable/bootstrap only the privileged broker. If the arm attempt fails before completion, cleanup may boot out and disable only that privileged label.

Success requires all of:

1. socket metadata is exactly UID 450 / GID 453 / mode 0660;
2. the named non-root operator sends one `mmx-admin status` query with a fixed request ID;
3. the response is exact-schema `NOT_FOUND`, correlated to that request ID and the requested installed release SHA;
4. the three central labels are still absent after all mutations;
5. the release manifest still verifies.

The bounded success claim is only:

`READY_FOR_GOVERNED_POWER_REMEDIATION`

No host readiness or enrollment claim follows. A fresh #829 secondary preflight after #846's receipt-backed power action remains mandatory.

## Dependency / release boundary

Production use is held until #846's exact action/wrapper is protected in the release being installed. The host-preparation source may be reviewed independently, but an installed release lacking `scripts/mmx_secondary_host_power.py` must refuse before arming.

This slice does not install the MH1 gateway, Worker Broker, credentials, certificates, provider homes, Capacity rows, Runtime state, or remote Job execution. Those remain later Fleet stages under their existing owners.
