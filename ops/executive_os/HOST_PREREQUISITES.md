# Executive OS macOS administrator runbook

There are deliberately two stages. Stage 1 is unprivileged review and merge of
the inert implementation. Stage 2 begins only after the delivery pull request
is merged and runs every administrator action from the exact commit currently
at `origin/master`.
This avoids both granting an unmerged branch root authority and pretending that
a PR head is the deployed default branch.

Commands beginning with `sudo` prompt for the Mac login password. macOS shows
no dots or characters while it is typed; that is normal. The administrator must
type that password locally. The device-login step likewise requires the
operator to approve OpenAI's one-time code in a browser. Neither secret should
be pasted into a terminal transcript, issue, PR, or chat.

## Stage 1 — review and merge (no administrator actions)

The delivery pull request must have a clean pushed head, passing deterministic CI and CodeQL, and
completed security review. It may then be squash-merged as inert code. Do not
run `sudo`, create service accounts, replace Python, create worker credentials,
or load a LaunchDaemon from the unmerged PR checkout. Merge alone is not host
acceptance and does not make Phase 1C-A complete or live.

## Stage 2 — exact `origin/master` provisioning, install, and acceptance

Start in a fresh Terminal after the delivery pull request merges and paste every
Stage 2 block into that same Terminal, in order. The first line enables fail-closed shell behavior:
any failed merge, ancestry, SHA, cleanliness, provisioning, or acceptance check
stops the sequence before later commands run. If the Terminal closes or any
command fails, begin again at this first block rather than skipping ahead.
`mktemp` gives every attempt a unique worktree parent, so a prior interrupted
run cannot collide with it.

```bash
set -euo pipefail
test "$(/usr/bin/id -u)" -ne 0
REPOSITORY=/absolute/path/to/Mastermind
OPERATOR_USER="$(/usr/bin/id -un)"
DELIVERY_PR=<delivery-pr-number>
test "$OPERATOR_USER" != root
test "$DELIVERY_PR" -gt 0

git -C "$REPOSITORY" fetch origin
test "$(gh pr view "$DELIVERY_PR" --repo mastermindx-market-intelligence/Mastermind \
  --json state --jq .state)" = "MERGED"
PR_MERGE_SHA="$(gh pr view "$DELIVERY_PR" --repo mastermindx-market-intelligence/Mastermind \
  --json mergeCommit --jq .mergeCommit.oid)"
MERGE_SHA="$(git -C "$REPOSITORY" rev-parse refs/remotes/origin/master)"
git -C "$REPOSITORY" merge-base --is-ancestor "$PR_MERGE_SHA" "$MERGE_SHA"

ACCEPTANCE_PARENT="$(/usr/bin/mktemp -d /private/tmp/mastermind-phase1c-acceptance.XXXXXX)"
SOURCE_REPO="$ACCEPTANCE_PARENT/source"
git -C "$REPOSITORY" worktree add --detach "$SOURCE_REPO" "$MERGE_SHA"
test "$(git -C "$SOURCE_REPO" rev-parse HEAD)" = "$MERGE_SHA"
test "$(git -C "$SOURCE_REPO" rev-parse refs/remotes/origin/master)" = "$MERGE_SHA"
test -z "$(git -C "$SOURCE_REPO" status --porcelain=v1 --untracked-files=normal)"
sudo -v
```

Bootstrap the fixed disabled service accounts and private directories. This is
idempotent: a rerun verifies the identities rather than creating alternates.

```bash
sudo /bin/bash "$SOURCE_REPO/ops/executive_os/bootstrap-host.sh" \
  --operator-user "$OPERATOR_USER"
```

Provision and immediately re-verify the dedicated root-owned Python runtime.
The helper refuses to replace Python while any process has the existing 3.12
framework or executable open; it prints the PIDs and exits without swapping, so
close or await those Python-based apps and rerun instead of killing them.

```bash
sudo /bin/bash "$SOURCE_REPO/ops/executive_os/provision-python-runtime.sh"
sudo /bin/bash "$SOURCE_REPO/ops/executive_os/provision-python-runtime.sh" \
  --verify-only
```

### Dedicated worker authentication

The auth helper runs the pinned native Codex executable as
`_mastermind_worker`, with an otherwise empty environment whose `HOME` and
`CODEX_HOME` are both the worker-only provider home. The primary identity is a
company ChatGPT workspace **service account** with a finite-lived Codex access
token. Before enrollment, a workspace administrator must attest out of band:

- the intended Mastermind company workspace and its workspace ID;
- that the service account is a member of that workspace and has Codex access;
- that the plan supports service accounts/access tokens and is a reviewed
  company plan; and
- the token expiry and rotation owner.

The local receipt records only the class
`company-workspace-admin-attested`. The exact workspace name/ID is
administrator evidence, not something `account/read` can observe, and is never
invented or forced locally.

Store the finite-lived token in the operator's Keychain under the reviewed
service/account labels. After `sudo -v` has already established administrator
credentials, pipe it directly from Keychain into the helper:

```bash
sudo -v
/usr/bin/security find-generic-password -w \
  -a mastermind-executive-codex-service \
  -s mastermind-executive-codex-access-token \
| sudo -n /bin/bash "$SOURCE_REPO/ops/executive_os/provision-worker-auth.sh" \
    --enroll-service-account
sudo /bin/bash "$SOURCE_REPO/ops/executive_os/provision-worker-auth.sh" \
  --verify-only
```

The token crosses only that stdin pipe after sudo credentials are established.
It is never placed in argv, an environment variable, a temporary file, a shell
variable/command substitution, a log, or a receipt. Enrollment calls pinned
Codex `login --with-access-token`, then checks exact credential metadata and an
output-discarded `login status`. It does **not** call inference and is not READY.
The helper never reads or copies the operator's personal `~/.codex/auth.json`;
Codex creates a separate
`/var/db/mastermind-executive/workers/codex-01/provider-home/auth.json`
directly as the worker.

Success requires the dedicated file to be a non-empty, regular, non-symlink,
single-link file owned by `_mastermind_worker:_mastermind_worker` with exact
mode `0600` and no ACL. The helper then asks Codex to validate the login while
discarding both output streams and checks the file metadata again. Login status alone is not READY.

`--verify-only` repeats metadata and login status without mutation or inference.
A preexisting credential is never overwritten unless the administrator passes
`--replace-existing` with an explicit enrollment mode. A rotation invalidates
the prior readiness receipt before Codex logs out; a failed replacement remains
fail-closed and never restores or copies credential bytes.

Before the recorded expiry, replace the Keychain item through the approved
workspace-admin workflow, re-establish sudo, and rotate explicitly:

```bash
sudo -v
/usr/bin/security find-generic-password -w \
  -a mastermind-executive-codex-service \
  -s mastermind-executive-codex-access-token \
| sudo -n /bin/bash "$SOURCE_REPO/ops/executive_os/provision-worker-auth.sh" \
    --enroll-service-account --replace-existing
```

The rotated credential is again only enrolled, not READY; install/attestation
must still be current and the single `--verify-ready` provider-readiness command
below must mint a new composite receipt before any later formal acceptance.

An access token for a named human in the same company workspace is an explicit
fallback only (`--enroll-personal-access-token`); pinned Codex `login status`
must classify it exactly as `personalAccessToken`. Device auth is the last
explicit fallback (`--reauthorize-device`); it must bind the
administrator-attested company workspace and later classify exactly as
`chatgpt`. Service-account access-token auth must classify exactly as
`agentIdentity`. The same initialized App Server validates the account plan and
proves from `config/read` with all layers included that no forced workspace or
forced login policy was applied. Neither fallback is implicit. Personal,
API-key, platform API-key, `CODEX_ACCESS_TOKEN` runtime injection, forced
workspace IDs, operator credential copying, and manual `auth.json` edits are
forbidden. Pinned Codex `0.147.0` has no reviewed workspace-selection flag; do
not invent one and never silently fall back to Personal.

The live canary CLI does not accept `--probe-root`, `--operator-home`, or
`--receipt-path`. Duplicate copies of those options cannot redirect the probe.
The disposable `/private/tmp/mastermind-provider-canary.*` root is owned by
`_mastermind_worker:_mastermind_worker` with exact mode `0700` before privilege
drop. It is not group- or world-traversable. The root process removes that tree
after the run. A local filesystem preflight failure is `isolation_violation`,
not a provider `process_failed`.

The inference canary uses the exact installed `codex-0.147.0` binary as
`_mastermind_worker`, the dedicated `CODEX_HOME`, production model
`gpt-5.6-sol`, and an inert disposable workspace. It does not start services,
open Executive SQLite, write production workspaces/runs, or print credentials.
A completed inference lifecycle is required for READY. `invalid_workspace_selected`
is a typed provider-readiness refusal, not a control-plane quarantine.

The Python helper prints the exact runtime root, binary, and TeamIdentifier to
use in Stage 2. Record those three non-secret values. The expected default
locations are:

```text
/Library/Frameworks/Python.framework/Versions/3.12
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12
BMM5U3QVKW
```

The helper downloads the pinned, notarized Python.org 3.12.10 package, verifies
its exact SHA-256, installer certificate, PSF TeamIdentifier, Gatekeeper status,
framework code signature, Mach-O signatures, ownership, modes, ACLs, and
contained symlinks before changing `/Library`. The PSF executable has an
absolute framework load path, so a copied tree under Application Support would
not be isolated. The helper instead installs the exact signed framework at its
native path, hardens both framework ancestors, and proves the live executable,
prefixes, standard library, extension modules, and loaded framework all resolve
inside that same root.

An existing Python 3.12 framework is never deleted. It is atomically retained
under the root-only directory
`/Library/Application Support/MastermindExecutive/python-archive/`. If the new
runtime fails after mutation begins, the partial candidate is archived and the
prior framework is restored. `--package /absolute/python.pkg` permits a cached
official package, while `--verify-only` performs no download or mutation.

The installer deliberately has no ambient Python fallback. The dedicated
Python 3.12 runtime must:

- be signed by the explicitly supplied TeamIdentifier and pass
  `codesign --verify --deep --strict`;
- contain the executable below the supplied runtime root;
- be entirely root-owned, non-symlinked at both entry paths, free of filesystem
  ACLs, and not writable by group or other; any internal runtime symlink must
  resolve back inside the pinned runtime root;
- run with `-I -S -B` and provide the standard-library modules checked by
  `install.sh`; no site-packages or PyYAML dependency is used.

A Homebrew, Conda, or user-owned Python tree does not meet this boundary. The
installer does not copy or re-sign an ambient runtime because that would turn a
mutable, pre-check object into production execution authority.

Install with the exact immutable values that the just-completed provisioner
printed and re-verified:

```bash
PYTHON_RUNTIME_ROOT='/Library/Frameworks/Python.framework/Versions/3.12'
PYTHON_BINARY="$PYTHON_RUNTIME_ROOT/bin/python3.12"
PYTHON_TEAM_IDENTIFIER=BMM5U3QVKW

sudo /bin/bash "$SOURCE_REPO/ops/executive_os/install.sh" \
  --source-repo "$SOURCE_REPO" \
  --expected-sha "$MERGE_SHA" \
  --operator-user "$OPERATOR_USER" \
  --python-runtime-root "$PYTHON_RUNTIME_ROOT" \
  --python-binary "$PYTHON_BINARY" \
  --python-team-identifier "$PYTHON_TEAM_IDENTIFIER"
```

Installation leaves both LaunchDaemons disabled and stopped. Run the installed
release's auth helper exactly once to cross the provider-readiness gate:

```bash
CREDENTIAL_EXPIRES_AT='YYYY-MM-DDTHH:MM:SSZ'
sudo /bin/bash \
  "/Library/Application Support/MastermindExecutive/releases/$MERGE_SHA/ops/executive_os/provision-worker-auth.sh" \
  --verify-ready \
  --expected-credential-kind service-account \
  --workspace-binding-class company-workspace-admin-attested \
  --credential-expires-at "$CREDENTIAL_EXPIRES_AT"
```

### Three isolated Personal Pro readiness slots

The company worker above remains the only installed Executive worker service.
The three Personal Pro slots are additional, independently attested credential
realms; they are **not routed**, started, or available for automatic failover by
this procedure. Their fixed mapping is:

| Worker slot | Multilogin seat | Disabled macOS principal |
|---|---|---|
| `codex-pro-01` | `chatgpt1` | `_mastermind_codex_01` |
| `codex-pro-02` | `chatgpt2` | `_mastermind_codex_02` |
| `codex-pro-03` | `chatgpt3` | `_mastermind_codex_03` |

Each login ceremony must happen one at a time. Keep the normal Mac Codex app
and its browser session untouched. When the helper prints the device URL and
one-time code, approve it only inside the named Multilogin seat in the table.
If macOS opens a default browser, close that page without approving it and use
the named Multilogin seat instead. Never sign the normal browser out or copy
the normal `~/.codex` credential; each helper invocation sets both `HOME` and
`CODEX_HOME` to the selected worker-only home.

Run exactly the slot matching the open Multilogin seat:

```bash
sudo /bin/bash \
  "/Library/Application Support/MastermindExecutive/releases/$MERGE_SHA/ops/executive_os/provision-worker-auth.sh" \
  --slot-id codex-pro-01 --reauthorize-device
sudo /bin/bash \
  "/Library/Application Support/MastermindExecutive/releases/$MERGE_SHA/ops/executive_os/provision-worker-auth.sh" \
  --slot-id codex-pro-02 --reauthorize-device
sudo /bin/bash \
  "/Library/Application Support/MastermindExecutive/releases/$MERGE_SHA/ops/executive_os/provision-worker-auth.sh" \
  --slot-id codex-pro-03 --reauthorize-device
```

Do not add `--replace-existing` on a first enrollment. If the selected slot
already contains a credential, the helper stops with exit 65. Use the
sanitized status command below to confirm the exact slot. Add
`--replace-existing` only for a deliberate rotation of that same slot; it
cannot select or overwrite another slot.

Enrollment proves only safe credential metadata and exact `login status`; it
does not spend inference and is not READY. Give each Personal Pro device login
an explicit Chairman revalidation deadline no more than 24 hours ahead, then
mint one independent readiness receipt per slot:

```bash
PERSONAL_PRO_REVALIDATE_AT='YYYY-MM-DDTHH:MM:SSZ'
sudo /bin/bash \
  "/Library/Application Support/MastermindExecutive/releases/$MERGE_SHA/ops/executive_os/provision-worker-auth.sh" \
  --slot-id codex-pro-01 --verify-ready \
  --credential-expires-at "$PERSONAL_PRO_REVALIDATE_AT"
sudo /bin/bash \
  "/Library/Application Support/MastermindExecutive/releases/$MERGE_SHA/ops/executive_os/provision-worker-auth.sh" \
  --slot-id codex-pro-02 --verify-ready \
  --credential-expires-at "$PERSONAL_PRO_REVALIDATE_AT"
sudo /bin/bash \
  "/Library/Application Support/MastermindExecutive/releases/$MERGE_SHA/ops/executive_os/provision-worker-auth.sh" \
  --slot-id codex-pro-03 --verify-ready \
  --credential-expires-at "$PERSONAL_PRO_REVALIDATE_AT"
```

Finally, inspect all four reviewed realms without opening credential bytes or
printing provider identities, paths, account names, profile IDs, or URLs:

```bash
sudo "$PYTHON_BINARY" -I -S -B \
  "/Library/Application Support/MastermindExecutive/releases/$MERGE_SHA/ops/executive_os/provider-slot-status.py"
```

The status is deliberately narrow: slot and logical seat, filesystem-presence
and metadata booleans, bounded readiness state/refusal, and worker-process
presence. `ready` means that slot's current credential metadata, exact binary,
identity policy, canary, and receipt still match. It does not mean the slot is
routed, capacity-aware, or authorized to spawn sessions.

For a service or personal access token, `CREDENTIAL_EXPIRES_AT` is the exact
nonsecret UTC expiry attested by the workspace administrator; do not estimate or
extend it locally. For the device-auth fallback, it is a Chairman-approved
revalidation deadline. A readiness receipt is valid for no more than 24 hours,
never beyond that deadline, and is refused unless at least 30 minutes remain.
The same exact deadline is required to reuse the receipt, and formal acceptance
rechecks the remaining margin.

`--verify-ready` first repeats metadata and output-discarded login status. If a
passing composite receipt already binds the requested credential kind,
workspace-binding class, current credential lstat, and exact installed Codex
identity, it reuses that receipt and spends no allocation. Otherwise it runs the
pinned identity probe, accepts only `agentIdentity` plus an explicit company
plan for service-account policy, and exclusive-creates a non-passing
`canary_reserved` receipt *before* inference. Only the process holding that
reservation may run **exactly one** inference canary. It then repeats the
identity probe, proves the credential and installed binary remained bound to
the same safe identity, incorporates both subprocess statuses, and atomically
replaces the reservation with the final root-only
`provider-readiness-v2.json` receipt. A typed canary refusal becomes a durable
non-passing receipt. A crash, malformed output, stale identity, or abandoned
reservation remains non-passing and blocks an automatic retry; it never spends
a second canary. There is no separate canary command in this runbook.

A single root-owned transaction lock covers receipt reuse, both identity probes,
reservation, canary, finalization, readiness invalidation, logout, and credential
replacement. A concurrent Terminal fails before mutation or inference. Normal
exit releases the lock. A killed process or host crash leaves it as a fail-closed
marker. Only after independently proving the recorded owner PID is no longer
alive and no readiness or enrollment process remains may an administrator clear
that marker explicitly:

```bash
sudo /bin/bash \
  "$SOURCE_REPO/ops/executive_os/provision-worker-auth.sh" \
  --recover-readiness-transaction
```

Recovery removes only the stale transaction marker. It never removes a receipt,
changes a credential, or authorizes another canary. A reserved or adverse
receipt still requires a newly authorized credential-replacement attempt.

This install-before-readiness order is deliberate, not circular: `install.sh`
requires strong structural auth metadata (exact worker UID/GID, mode `0600`,
nonempty regular non-symlink single-link file with no ACL) and leaves services
stopped; the readiness probe then uses the exact installed, attested binary.
Formal acceptance validates the composite receipt against the current auth
lstat and installed Codex identity before it creates a Job or starts services.

The readiness boundary is also the OAuth/CLI automation boundary. Executive
Jobs, planner prompts, native helpers, MCP tools and plugins never invoke
`codex login`, device authorization, service-token enrollment, credential
rotation or account switching. They may select only the already-ready dedicated
`_mastermind_worker` realm named by the current composite receipt. Credential
expiry or a non-passing/stale receipt removes that slot from readiness; it does
not authorize an interactive login, copy of the operator's provider home, model
request for a secret, or automatic failover to another account.

The G4 planner profile does not create another worker or lifecycle. One Codex
App Server process is still one Executive process generation and its one native
helper is a subordinate thread inside the same Attempt and session tree. The
installed launch must attest the exact
`operator.appserver.readonly.docs-mcp.native-helper.v1` profile: read-only,
approval `never`, shell/tool network disabled, only the reviewed OpenAI Docs MCP
server and two tools, empty plugins and configured skills, hidden per-spawn
role/model/effort, one helper, depth one, and a 60-second helper runtime. Before
the parent candidate is accepted, the worker must reconcile redacted
collaboration events against bounded `thread/list` and exact `thread/read`
lineage. Any unknown or wider state is effect-unknown config drift. A native
helper result is never an independent-review receipt; review remains a separate
Executive Job/Attempt on an excluded worker.

Formal Phase 1C-A acceptance proves the installed lifecycle, principals,
provider readiness and service containment. It does not by itself prove that a
model actually chose the G4 helper. After acceptance and before any general
production claim, run exactly one bounded strict-v2 Chairman intent whose
read-only planner is explicitly instructed to delegate one documentation lookup
to its native helper. Record only non-secret Job/Attempt/epoch/generation/parent
thread/child thread IDs, exact capability/config digests, MCP tool identity,
terminal statuses and receipt hashes. Do not record prompt text, model output,
credential values or provider-home contents. If no child appears, the honest
state is `SERVICE_COMPOSED_UNARMED`/capability unused—not a successful G4 live
proof.

Provider readiness is not Git handoff Gate B. With both LaunchDaemons still
disabled and stopped, run the installed distinct-UID Git preflight exactly once:

```bash
umask 077
GATE_B_RECEIPT="/private/tmp/executive-os-gate-b-$MERGE_SHA.json"
sudo "$PYTHON_BINARY" -I -S -B \
  "/Library/Application Support/MastermindExecutive/releases/$MERGE_SHA/ops/executive_os/git_handoff_preflight.py" \
  --expected-sha "$MERGE_SHA" \
  > "$GATE_B_RECEIPT"
sudo /usr/sbin/chown root:wheel "$GATE_B_RECEIPT"
sudo /bin/chmod 0600 "$GATE_B_RECEIPT"
```

Gate B must emit `mastermind.executive_git_handoff_preflight/v1` with
`passed: true` and the exact installed SHA. Stop here for independent receipt
review. Do not substitute provider readiness, local tests, or an older Gate B
receipt for this distinct-UID Git handoff proof.

Only after that receipt review explicitly releases the stop may the installed
acceptance wrapper perform the first
start, per-PID canary quarantine, worker-principal live
probe, private-socket canary activation, fault injection, cleanup, restore drill, and
no-public-listener proof:

```bash
sudo /bin/bash \
  "/Library/Application Support/MastermindExecutive/releases/$MERGE_SHA/ops/executive_os/acceptance.sh" \
  --source-repo "$SOURCE_REPO" \
  --expected-sha "$MERGE_SHA" \
  --operator-user "$OPERATOR_USER"
```

Success ends with `Phase 1C-A acceptance PASS` and a private receipt root at:

```text
/var/db/mastermind-executive/control/acceptance/<exact-origin-master-sha>/
```

Do not copy provider auth, canary values, database rows, or environment contents
into the follow-up PR. Record only the reviewed receipt paths, hashes, Job and
Attempt IDs, UIDs, exit statuses, and exact SHA.

## Receipt-gated autonomy arm, proof, and credential interlock

Formal acceptance still leaves both installed arm bits false. Do not edit either
JSON config. From the exact installed release, first prove the closed unarmed
state, then run the one root transaction that binds the reviewed Gate B receipt,
formal acceptance, current provider readiness, both configs, exact release and
Runtime quiescence:

```bash
AUTONOMY_CONTROL="/Library/Application Support/MastermindExecutive/releases/$MERGE_SHA/ops/executive_os/autonomy-control.sh"
EXPECTED_CREDENTIAL_KIND='service-account'
WORKSPACE_BINDING_CLASS='company-workspace-admin-attested'
# Reuse the exact finite UTC value already used for --verify-ready.
CREDENTIAL_EXPIRES_AT='YYYY-MM-DDTHH:MM:SSZ'

sudo /bin/bash "$AUTONOMY_CONTROL" status --expected-sha "$MERGE_SHA"
sudo /bin/bash "$AUTONOMY_CONTROL" arm \
  --expected-sha "$MERGE_SHA" \
  --gate-b-receipt "$GATE_B_RECEIPT" \
  --expected-credential-kind "$EXPECTED_CREDENTIAL_KIND" \
  --workspace-binding-class "$WORKSPACE_BINDING_CLASS" \
  --credential-expires-at "$CREDENTIAL_EXPIRES_AT"
sudo /bin/bash "$AUTONOMY_CONTROL" status --expected-sha "$MERGE_SHA"
```

The first status must be exactly `UNARMED`; the post-transaction status must be
exactly `ARMED_READY`. Arm stops both services before committing either config,
starts worker then control, and removes its durable transaction marker only
after exact PID/principal/socket/`READY` proof. Every armed control restart
obtains a fresh same-PID environment/secret canary through the existing worker
broker before entering `READY`; a prior-PID envelope is never reused and no
provider allocation is spent by this boot re-attestation.

Run the bounded strict-v2 Chairman-intent proof described below, then rehearse
the shrink-only rollback and confirm both services stopped and both configs
false:

```bash
sudo /bin/bash "$AUTONOMY_CONTROL" disarm --expected-sha "$MERGE_SHA"
sudo /bin/bash "$AUTONOMY_CONTROL" status --expected-sha "$MERGE_SHA"
```

The second status must be exactly `UNARMED` and the canonical receipt must be
`DISARMED`. A final re-arm is allowed only when the installed release, Gate B,
acceptance, provider-readiness receipt, credential metadata and every frozen
capability digest are unchanged and no new authority appeared. Otherwise stop
for a fresh Chairman decision; never reuse the old arm command as a blind retry.

Credential enrollment, device reauthorization and replacement are explicit
native operator operations and are refused while any arm bit is true, an
autonomy transaction marker exists, or the current `DISARMED` receipt does not
bind both exact configs. Before any later credential rotation, run and verify
`disarm` as above. The credential helper checks this interlock before readiness
invalidation, logout, token stdin or device authorization. Executive Jobs,
workers, MCP tools, plugins and model prompts cannot bypass it.

## If acceptance fails

Do not manually delete `/var/db/mastermind-executive`. The installed release
contains a bounded retry helper that stops both Executive services, sweeps only
the two dedicated service UIDs, and atomically moves prior mutable proof state
to a root-only archive. It does not move or read worker `auth.json`, installed
releases, plists, policy, or pinned runtimes.

```bash
sudo /bin/bash \
  "/Library/Application Support/MastermindExecutive/releases/$MERGE_SHA/ops/executive_os/acceptance-retry.sh" \
  --expected-sha "$MERGE_SHA"
```

The helper prints the retained evidence path below
`/var/db/mastermind-executive-acceptance-archive/<sha>/`, leaves both services
disabled and stopped, and recreates empty canonical runtime roots. Then rerun
the exact same `acceptance.sh` command. An interrupted archive is marked
`INCOMPLETE`; its already moved evidence is retained, canonical directories are
recreated, and running the retry helper again completes preparation without
overwriting the earlier archive.

## Worker refuses to start: Codex binary identity changed

The worker daemon attests the Codex binary once, at install time, and pins
its cheap filesystem identity (inode, size, mtime, ctime, and more) in a
root-owned receipt instead of re-running `codesign`/`--version` on every
start. This is a deliberate availability tradeoff: **any** change to the
installed binary's identity -- even a byte-identical repair that lands on a
new inode -- makes the worker refuse to start, and launchd will keep
respawning and re-refusing it roughly every 10 seconds until fixed.

If the worker LaunchDaemon is respawn-looping and
`/var/log/mastermind-executive/worker/stderr.log` shows `worker broker
error: codex binary identity mismatch at startup: ...` or `codex
attestation receipt is missing or unreadable`, the on-disk Codex binary no
longer matches what was recorded at install time. Common, benign causes: an
operator repaired or replaced the binary in place, a backup restore, a host
migration, or an APFS snapshot rollback.

**Remedy:** re-run `install.sh` for the same release. The receipt is always
rewritten unconditionally from whatever binary is currently installed (see
`ops/executive_os/install.sh`'s codex attestation receipt writer), so a
benign identity change self-heals on the next install run. A genuinely
tampered or wrong binary will instead fail the pre-existing `codesign
--verify --strict` / exact SHA-256 checks in `install.sh` itself before a
new receipt is ever written -- which is the correct, fail-closed outcome.
