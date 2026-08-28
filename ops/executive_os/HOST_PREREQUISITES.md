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

## Alternative B — CF2-H0 complete-source closure repair

This is the selected, bounded source repair for an already prepared H0 host. It is separate from
the broader Stage 2 provisioning procedure below. It rematerializes the accepted Macro commit as
an ordinary complete repository, archives the superseded installed source and generation, and
publishes a new six-file generation without changing the existing topology. Its endpoint is H0
source-closure proof, not P0 acceptance.

The old installed state must match every gate below under the H0 lock before the carrier may
publish its one durable repair intent or mutate installed state:

| Old installed gate | Required identity |
|---|---|
| generation basename and `source-config.json` | `2b05a61f54c876f00c3f03d51bd9df72de4a73e76bc06b2e7bc13a11ee203d60` |
| `components.json` SHA-256 | `02886a6c79f22534ac24234d8adb3224329976342393988541c2a50d7e297f29` |
| `host-preparation-receipt.json` | `51c58d18869663d90c593e416c7fc7833b3725378870f576abd3647f62f40830` |
| `broker-topology.json` | `981e880ba7d21a0003fe2dd8322c5793f2643b815d094374dd6fad3fed31e453` |
| `rollback-contract.json` | `18d83b0e164ac2e917d84c01fe1d53fc5c1ce0c33ac9580f11d684e16e495093` |
| `rollback-drill-receipt.json` | `7efba70495cbbf8bcad0c4e47e894a23f4b1618756d8c3e23cae85ad6b7250ba` |
| receipt outcome | `H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED` |
| topology/release/preparer commit | `e4e44867ace335ac9208a3990a10c163e199492d` |
| accepted Macro commit | `dcdd939c45b23abce5ba04f95e330ac914a3904b` |
| material digest | `35931b4ef965c5d67a7e01444dd483804e48671784716ea8196c94e925466650` |

Any mismatch refuses before installed mutation and returns to Sol. The carrier never rewrites an
intent around a different observed state.

### Nonprivileged v2 transport and inert exact-commit carrier

Complete all Git review, protected merge verification, and any network acquisition before this
block. The local Macro repository must already contain the exact accepted commit and its complete
reachable object graph. The local Mastermind repository must already contain the exact protected
repair merge. This block performs no provider, service, socket, worker, P0, or root action. It
creates a digest-bound Git bundle as inert data; no inode created here is later executed as root.
The `git bundle create` step names the already verified protected ref whose tip is the exact merge.

Set the two repository paths and replace only the repair-merge placeholder with the observed
40-lower-hex protected merge. Do not substitute a PR head, invent a future merge SHA, or precompute
a future generation digest.

```bash
set -euo pipefail
test "$(/usr/bin/id -u)" -ne 0
MACRO_REPOSITORY=/absolute/path/to/macro
MASTERMIND_REPOSITORY=/absolute/path/to/Mastermind
OPERATOR_USER="$(/usr/bin/id -un)"
MACRO_COMMIT=dcdd939c45b23abce5ba04f95e330ac914a3904b
REPAIR_MERGE_SHA='<40-lower-hex-protected-repair-merge-sha>'
test "$OPERATOR_USER" != root
[[ "$REPAIR_MERGE_SHA" =~ ^[0-9a-f]{40}$ ]]

safe_git() {
  /usr/bin/env -i \
    HOME=/var/empty PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_LOCAL=/dev/null \
    GIT_ATTR_NOSYSTEM=1 GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false \
    SSH_ASKPASS=/usr/bin/false GIT_OPTIONAL_LOCKS=0 GIT_NO_LAZY_FETCH=1 \
    GIT_NO_REPLACE_OBJECTS=1 GIT_EXTERNAL_DIFF=/usr/bin/false GIT_ALLOW_PROTOCOL=file \
    /usr/bin/git --no-replace-objects \
      -c protocol.allow=never -c protocol.file.allow=always \
      -c core.hooksPath=/dev/null -c core.fsmonitor=false \
      -c core.attributesFile=/dev/null -c diff.external=/usr/bin/false "$@"
}
safe_git -C "$MACRO_REPOSITORY" cat-file -e "$MACRO_COMMIT^{commit}"
test "$(safe_git -C "$MASTERMIND_REPOSITORY" rev-parse "$REPAIR_MERGE_SHA^{commit}")" = "$REPAIR_MERGE_SHA"
test "$(safe_git -C "$MASTERMIND_REPOSITORY" rev-parse refs/remotes/origin/master)" = "$REPAIR_MERGE_SHA"
safe_git -C "$MASTERMIND_REPOSITORY" diff --no-ext-diff --no-textconv --quiet --exit-code
safe_git -C "$MASTERMIND_REPOSITORY" diff --no-ext-diff --no-textconv --cached --quiet --exit-code

REPAIR_PARENT="$(/usr/bin/mktemp -d /private/tmp/mastermind-h0-source-repair.XXXXXX)"
REPAIR_CHECKOUT="$REPAIR_PARENT/mastermind"
safe_git clone --no-local --no-hardlinks --no-checkout \
  "$MASTERMIND_REPOSITORY" "$REPAIR_CHECKOUT"
safe_git -C "$REPAIR_CHECKOUT" checkout --detach "$REPAIR_MERGE_SHA"
test -d "$REPAIR_CHECKOUT/.git"
test ! -f "$REPAIR_CHECKOUT/.git"
test "$(safe_git -C "$REPAIR_CHECKOUT" rev-parse HEAD)" = "$REPAIR_MERGE_SHA"
test -z "$(safe_git -C "$REPAIR_CHECKOUT" status --porcelain=v1 --untracked-files=all)"
test -z "$(/usr/bin/find "$REPAIR_CHECKOUT" -type l -print -quit)"
test -z "$(/usr/bin/find "$REPAIR_CHECKOUT" -type f -links +1 -print -quit)"

REPAIR_CARRIER="$REPAIR_PARENT/mastermind-exact-commit.bundle"
safe_git -C "$MASTERMIND_REPOSITORY" bundle create \
  "$REPAIR_CARRIER" refs/remotes/origin/master
/bin/chmod 0400 "$REPAIR_CARRIER"
test "$(safe_git bundle list-heads "$REPAIR_CARRIER")" = \
  "$REPAIR_MERGE_SHA refs/remotes/origin/master"
REPAIR_CARRIER_SHA256="$(/usr/bin/shasum -a 256 "$REPAIR_CARRIER" | /usr/bin/awk '{print $1}')"
[[ "$REPAIR_CARRIER_SHA256" =~ ^[0-9a-f]{64}$ ]]
/usr/bin/printf 'repair_carrier_sha256=%s\n' "$REPAIR_CARRIER_SHA256"

TRANSPORT_PARENT="$(/usr/bin/mktemp -d /private/tmp/mastermind-h0-v2-transport.XXXXXX)"
MACRO_TRANSPORT="$TRANSPORT_PARENT/macro-complete-v2.zip"
/usr/bin/python3 -I -S -B \
  "$REPAIR_CHECKOUT/ops/executive_os/capacity_host_artifacts.py" \
  build-source-transport-v2 \
  --source-repository "$MACRO_REPOSITORY" \
  --output "$MACRO_TRANSPORT" \
  --commit "$MACRO_COMMIT" \
  >"$TRANSPORT_PARENT/manifest-build-output.json"
/bin/chmod 0400 "$MACRO_TRANSPORT"
test "$(/usr/bin/stat -f %l "$MACRO_TRANSPORT")" -eq 1
MACRO_TRANSPORT_SHA256="$(/usr/bin/shasum -a 256 "$MACRO_TRANSPORT" | /usr/bin/awk '{print $1}')"
[[ "$MACRO_TRANSPORT_SHA256" =~ ^[0-9a-f]{64}$ ]]
/usr/bin/printf 'macro_transport_sha256=%s\n' "$MACRO_TRANSPORT_SHA256"
```

The builder emits `mastermind.capacity_source_transport/v2`. It requires the exact two-member ZIP,
complete reachable object inventory, frozen eleven-path material projection, and ordinary strict
closure; missing objects, promisor state, alternates, shallow state, replacement refs, grafts,
remotes, filters, or unsafe metadata refuse. Record the emitted manifest, its object count and
semantic inventory digest, the payload digest, and the independently calculated enclosing ZIP
digest. These are per-carrier proof; they are not a future generation identity.

### One offline administrator ceremony

Keep the same Terminal and invoke the checked-in bootstrap once as the unprivileged operator.
`sudo` may open one native administrator dialog, but root never receives a shell, heredoc,
interpreter `-c`, or operator stdin. Before the carrier is authenticated, each privileged call is
one reviewed absolute macOS system-tool argv. The bootstrap copies the inert bundle without
preserving metadata into the exclusive fixed literal
`/private/var/root/mastermind-h0-root-carrier`, authenticates its digest and exact commit with fully
closed Git configuration, and materializes the complete five-file local-module closure into new
root-owned inodes:

- `repair-capacity-source-closure.sh`;
- `capacity_host_artifacts.py`;
- `capacity_source_contract.py`;
- `provider_worker_slots.py`; and
- `provider_identity_policy.py`.

Every retained carrier file is rebound to its expected Git mode and Git blob OID before the first
carrier Python or shell launch. The authenticated Python verifier independently repeats the exact
commit/mode/blob checks from the root-created bare repository. Only then does the bootstrap execute
one repair and two verify-only passes. Their output is buffered until the fixed root namespace has
been removed successfully; cleanup failure is a typed non-success and cannot emit a clean pass.
HUP, INT, TERM, ordinary refusal, and success all enter this same cleanup lifecycle. A preexisting
fixed namespace is unknown residue: the no-replace `mkdir` refuses it and does not delete it.

```bash
/bin/bash "$REPAIR_CHECKOUT/ops/executive_os/bootstrap-capacity-source-closure.sh" \
  "$REPAIR_MERGE_SHA" "$OPERATOR_USER" "$MACRO_TRANSPORT" "$MACRO_TRANSPORT_SHA256" \
  "$REPAIR_CARRIER" "$REPAIR_CARRIER_SHA256"
```

The copied bundle remains inert data. An initially observed symlink refuses before privileged
namespace creation and source-path metadata is never changed. A pre-opened writable descriptor or
source race can only change the operator bundle and therefore either changes the frozen source
relation, loses the copied root inode's recorded SHA-256, or leaves the already copied root inode
unchanged. All privileged Git uses the root-created bundle and bare repository, has
local/system/global config, hooks, fsmonitor, attributes, replacements, external diff/textconv,
prompts, lazy fetch, optional locks, locale, `HOME`, `PATH`, and protocols closed, and permits only
local file transport. No installed release executable or Python module is launched; the reviewed
carrier verifies the preserved release strictly as inert data.

The carrier reuses exactly
`/Library/Application Support/MastermindExecutive/locks/cf2-h0.lock`. While holding it, the repair
verifies the exact old gates and fixed principal/service/socket state, materializes and verifies the
complete candidate, publishes one durable repair intent, performs the archive-only no-replace
source/generation swap, and retains all superseded or failed evidence. It does not install a release
and does not rerender topology. The final generation rename is the last semantic filesystem mutation.
Its immediately following capacity-generations parent `fsync` is the durability barrier.

If the final rename is visible but that parent `fsync` fails or is ambiguous, exit 70 is not
completion and must never trigger rollback. Re-enter only the same carrier, exact merge, intent,
transport, and archive; it fully reverifies the visible committed graph and reconciles forward.
Never create a second intent/carrier/archive, auto-fail over, or restore the archived promisor
source after the visible commit. A precommit definite failure restores only the uniquely
intent-bound old source/generation by no-replace rename and retains the failed candidate in the
same archive; nothing is deleted or overwritten.

The fixed exit, stdout, and stderr grammar is:

```text
0  H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED\n  (repair)
0  H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED\n       (verify-only)
64 INVALID_INVOCATION\n
65 H0_SOURCE_CLOSURE_REPAIR_REFUSED\n
70 H0_SOURCE_CLOSURE_REPAIR_INCOMPLETE_RECONCILE_SAME_CARRIER\n
75 H0_LOCK_HELD\n
77 ROOT_REQUIRED\n
```

Stderr is empty for every fixed carrier outcome. Any other stdout, any stderr, or a mismatched exit
is a refusal, not proof.

### Verify-only mutation and identity proof law

Verify-only performs zero program-directed and zero semantic mutation. Kernel-induced access-time
advancement from required reads is the sole permitted observable metadata delta. Atime is
non-authoritative, may only remain equal or advance, and is never set, restored, decreased, or used
to conceal another change. Namespace, bytes/digests, device/inode identity, type, mode, UID/GID,
links, size, flags, ACLs, xattrs, mtime, ctime, topology/rollback evidence, launchd state, sockets,
and legacy state remain exact. The shared lock is opened read-only and is neither created nor
written by verify-only.

This exception applies only to the fixed installed H0 root. Primary host evidence proves that root
is on writable APFS, is not mounted `MNT_RDONLY`, and its mount does not expose `MNT_NOATIME`;
mandatory full independent content verification necessarily reads installed bytes. The exception
does not apply to any other filesystem, root, provider, or worker surface.

The sanitized proof packet preserves two distinct identity axes:

- `e4e44867ace335ac9208a3990a10c163e199492d` remains the exact current
  topology-preparer/topology-release identity because topology, rollback, release, and preparer
  bytes are unchanged; and
- the observed protected repair merge is the exact source-closure/generation-repair identity.

Record only the exact merge, transport/manifest/payload and semantic inventory identities, intent
and receipt hashes, archive/source/generation semantic digests, new generation basename and six
hashes, unchanged topology/rollback hashes, UID/GID/common-device facts, exact repair sentinel,
both verify sentinels, and the permitted atime observation for each verify pass. Do not record a
provider-home path, account, credential, secret, or invented generation digest.

This H0 principal check is attribute-scoped to fixed record names, UIDs, primary GIDs, and fixed
membership/nonmembership facts. It never requests a home-directory attribute and never resolves,
stats, reads, traverses, or enumerates any provider-home. The later P0 carrier must separately
re-prove provider-home ownership, mode, and non-traversal.

Stop after both verify-only passes. H0 source closure is not P0 acceptance. A distinct P0 re-pin is
required to bind both exact merge/install identities and replace its constant closure assertion
with the pure verifier. P0, provider-home proof, every credential and OAuth ceremony, provider
calls, service mutation/start, socket creation/connection, routing, worker execution, fan-out,
failover, and CF2-I all remain held.

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

## CF2-H0 — grounded capacity-source host preparation

This is a separate credential-free preparation stage. Run it only from the
exact merged `origin/master` history, with the reviewed CF2-H0 merge commit
checked out detached and passed as the explicit expected Mastermind SHA.
H0 installs the grounded Macro source/runtime and exactly three inert Personal
Pro broker definitions. The three new labels stay persistently disabled and
unloaded and their three socket nodes stay absent.

H0 does **not** authenticate a provider, open or create a credential, perform
OAuth/device authorization, execute a worker/provider call, compose the new
brokers with the control runtime, route a job, implement CF2-I, fan out work or
issue CF2-P0 acceptance. Its success outcome is
`H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED`.

### Build the two inert inputs as the authenticated operator

Do all GitHub review, exact-head and hosted-check review before privilege. Use
an already-authenticated local Macro repository to acquire the accepted CF1
commit. Do not give root an anonymous HTTPS remote and do not copy a Macro
checkout recursively across the privilege boundary.

The reviewed `capacity_host_artifacts.py` helper reads immutable Git objects at
the exact commit and produces one data-only custom transport. The ZIP contains
only `manifest.json` and `payload.pack`; it cannot carry the caller's worktree,
index, Git config, hooks, ignored files, credential helpers or credentials.

```bash
set -euo pipefail
test "$(/usr/bin/id -u)" -ne 0
REPOSITORY=/absolute/path/to/Mastermind
MACRO_REPOSITORY=/absolute/path/to/authenticated/macro
OPERATOR_USER="$(/usr/bin/id -un)"
DELIVERY_PR=<cf2-h0-pr-number>
MACRO_COMMIT=dcdd939c45b23abce5ba04f95e330ac914a3904b
test "$OPERATOR_USER" != root
test "$DELIVERY_PR" -gt 0

git -C "$REPOSITORY" fetch origin master
test "$(gh pr view "$DELIVERY_PR" --repo mastermindx-market-intelligence/Mastermind \
  --json state --jq .state)" = MERGED
PR_MERGE_SHA="$(gh pr view "$DELIVERY_PR" \
  --repo mastermindx-market-intelligence/Mastermind \
  --json mergeCommit --jq .mergeCommit.oid)"
MERGE_SHA="$PR_MERGE_SHA"
test "$(git -C "$REPOSITORY" rev-parse "$MERGE_SHA^{commit}")" = "$MERGE_SHA"
git -C "$REPOSITORY" merge-base --is-ancestor \
  "$MERGE_SHA" refs/remotes/origin/master

H0_PARENT="$(/usr/bin/mktemp -d /private/tmp/mastermind-cf2-h0.XXXXXX)"
SOURCE_REPO="$H0_PARENT/mastermind-source"
MACRO_TRANSPORT="$H0_PARENT/macro-cf1-data-only.zip"
PYYAML_WHEEL="$H0_PARENT/pyyaml-6.0.3-cp312-cp312-macosx_11_0_arm64.whl"

git clone --no-local --no-hardlinks --no-checkout "$REPOSITORY" "$SOURCE_REPO"
git -C "$SOURCE_REPO" checkout --detach "$MERGE_SHA"
git -C "$SOURCE_REPO" remote remove origin
git -C "$SOURCE_REPO" config --local core.hooksPath /dev/null
test "$(git -C "$SOURCE_REPO" rev-parse HEAD)" = "$MERGE_SHA"
test -z "$(git -C "$SOURCE_REPO" remote)"
test -z "$(git -C "$SOURCE_REPO" status --porcelain=v1)"

git -C "$MACRO_REPOSITORY" fetch origin master
test "$(git -C "$MACRO_REPOSITORY" rev-parse "$MACRO_COMMIT^{commit}")" = \
  "$MACRO_COMMIT"

MATERIAL_PATHS=(
  config/capability_manifest.yml
  config/metabolism_budget.yml
  engine/codex_lane/runner.py
  engine/codex_provider.py
  engine/llm_auth.py
  engine/metabolism/budget_gate.py
  engine/neuralweb/key_pool.py
  engine/provider_capacity.py
  engine/provider_health.py
  lib/ai_costs.py
  scripts/build_provider_capacity.py
)
MATERIAL_ARGUMENTS=()
for path in "${MATERIAL_PATHS[@]}"; do
  MATERIAL_ARGUMENTS+=(--material-path "$path")
done
/usr/bin/python3 -I -S -B \
  "$SOURCE_REPO/ops/executive_os/capacity_host_artifacts.py" \
  build-source-transport \
  --source-repository "$MACRO_REPOSITORY" \
  --output "$MACRO_TRANSPORT" \
  --commit "$MACRO_COMMIT" \
  "${MATERIAL_ARGUMENTS[@]}"
test -f "$MACRO_TRANSPORT"
test ! -L "$MACRO_TRANSPORT"
test "$(/usr/bin/stat -f '%l' "$MACRO_TRANSPORT")" -eq 1
MACRO_TRANSPORT_SHA256="$(/usr/bin/shasum -a 256 "$MACRO_TRANSPORT" | \
  /usr/bin/awk '{print $1}')"
test "${#MACRO_TRANSPORT_SHA256}" -eq 64

/usr/bin/curl --fail --location --proto '=https' --tlsv1.2 \
  --output "$PYYAML_WHEEL" \
  https://files.pythonhosted.org/packages/89/a0/6cf41a19a1f2f3feab0e9c0b74134aa2ce6849093d5517a0c550fe37a648/pyyaml-6.0.3-cp312-cp312-macosx_11_0_arm64.whl
test "$(/usr/bin/shasum -a 256 "$PYYAML_WHEEL" | /usr/bin/awk '{print $1}')" = \
  fc09d0aa354569bc501d4e787133afc08552722d3ab34836a80547331bb5d4a0
```

The wheel filename and SHA-256 are both frozen. The root preparer copies these
two single-link files into a root-only stage and revalidates the complete
transport, exact material Git blobs, wheel digest, PyYAML `RECORD` and the full
pip-free runtime tree before installation.

### Run the exact merged protected checkout as root

Only now begin the local administrator ceremony. Move the dedicated detached
Mastermind checkout beneath a new root-owned, non-writable parent, remove ACLs
and removable extended attributes from that disposable clone, and make the whole
clone root-owned and non-group/other-writable before root executes it. The
preparer tolerates only macOS's system-maintained `com.apple.provenance` xattr;
every caller-controlled or otherwise unapproved xattr fails closed. Leaving the
clone beneath an operator-writable `/private/tmp` parent is forbidden because
that parent could replace the reviewed tree after preflight. Root must run only
this clean checkout at the exact merged protected SHA; it must not execute the
ordinary user checkout or a copied Macro worktree.

```bash
sudo -v
ROOT_SOURCE_PARENT="$(sudo /usr/bin/mktemp -d /private/var/root/mastermind-cf2-h0.XXXXXX)"
ROOT_SOURCE_REPO="$ROOT_SOURCE_PARENT/mastermind-source"
sudo /bin/mv "$SOURCE_REPO" "$ROOT_SOURCE_REPO"
sudo /bin/chmod -N "$ROOT_SOURCE_PARENT"
sudo /usr/bin/xattr -c "$ROOT_SOURCE_PARENT"
sudo /bin/chmod -RN "$ROOT_SOURCE_REPO"
sudo /usr/bin/xattr -cr "$ROOT_SOURCE_REPO"
sudo /usr/sbin/chown -R root:wheel "$ROOT_SOURCE_REPO"
sudo /bin/chmod -R go-w "$ROOT_SOURCE_REPO"
sudo /bin/bash "$ROOT_SOURCE_REPO/ops/executive_os/prepare-capacity-host.sh" \
  --expected-mastermind-sha "$MERGE_SHA" \
  --operator-user "$OPERATOR_USER" \
  --macro-transport "$MACRO_TRANSPORT" \
  --macro-transport-sha256 "$MACRO_TRANSPORT_SHA256" \
  --pyyaml-wheel "$PYYAML_WHEEL"
sudo /bin/bash "$ROOT_SOURCE_REPO/ops/executive_os/prepare-capacity-host.sh" \
  --expected-mastermind-sha "$MERGE_SHA" \
  --verify-only
```

The preparer installs exactly three realm configs, three per-realm Codex
attestation receipts and three launchd plists. Before and after installation it
proves the new labels are disabled and unloaded and the new socket nodes are
absent. Installing the definitions grants no service-start authority.

One root-only host lock excludes overlapping H0 preparations. If an earlier
process was killed after installing only part of the nine-file topology, the
same carrier proves stopped/absent state, archives every exact partial target
and temporary artifact, records `INTERRUPTED_H0_PARTIAL_RECOVERED`, and resumes
from the sealed inputs. Intent and receipt publication are resumable and
crash-atomic through same-directory candidates, file and directory fsync
barriers and atomic renames; each target move fsyncs both affected parents. It
never overwrites an ambiguous target or revives a service. A completed
generation is never recovered this way; normal follow-up
uses `--verify-only`.

The preparer then performs the real shrink-only rollback drill: it moves all
nine new artifacts to a root-only archive, proves disabled/unloaded service and
absent-socket postconditions, records `SHRINK_ONLY_ROLLBACK_PASS`, and reinstalls
the same nine inert artifacts. Principals, private homes, any later credentials,
immutable releases, grounded Macro source, the capacity runtime, the read-only
telemetry boundary and legacy Phase 1C artifacts are preserved. Rollback does
not delete them and does not start a service.

The immutable six-file H0 generation (including a self-contained copy of the
durable rollback-drill receipt) and installed-host receipt are committed
only after source, runtime, release, topology, legacy-state and rollback proof
pass. The successful install and each successful verification report
`H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED`.

Run `--verify-only` a second time to prove zero-write and zero semantic mutation idempotence under
the sole kernel read-atime observer effect defined above. Then rerun
the independently governed, read-only CF2-P0 census. Proceed only if that
census—not this preparer—emits `GROUNDED_CF1_GIT_RELEASE_PATH_ACCEPTED`. Even
then, CF2-I-A is the next separate carrier. OAuth/device ceremonies,
credentials, provider calls, service start, runtime composition, routing,
fan-out and failover remain held.
