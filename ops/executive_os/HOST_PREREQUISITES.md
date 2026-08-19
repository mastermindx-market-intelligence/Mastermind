# Executive OS macOS administrator runbook

There are deliberately two stages. Stage 1 is unprivileged review and merge of
the inert implementation. Stage 2 begins only after PR #25 is merged and runs
every administrator action from the exact commit currently at `origin/master`.
This avoids both granting an unmerged branch root authority and pretending that
a PR head is the deployed default branch.

Commands beginning with `sudo` prompt for the Mac login password. macOS shows
no dots or characters while it is typed; that is normal. The administrator must
type that password locally. The device-login step likewise requires the
operator to approve OpenAI's one-time code in a browser. Neither secret should
be pasted into a terminal transcript, issue, PR, or chat.

## Stage 1 — review and merge (no administrator actions)

PR #25 must have a clean pushed head, passing deterministic CI and CodeQL, and
completed security review. It may then be squash-merged as inert code. Do not
run `sudo`, create service accounts, replace Python, create worker credentials,
or load a LaunchDaemon from the unmerged PR checkout. Merge alone is not host
acceptance and does not make Phase 1C-A complete or live.

## Stage 2 — exact `origin/master` provisioning, install, and acceptance

Start in a fresh Terminal after PR #25 merges and paste every Stage 2 block into
that same Terminal, in order. The first line enables fail-closed shell behavior:
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
test "$OPERATOR_USER" != root

git -C "$REPOSITORY" fetch origin
test "$(gh pr view 25 --repo mastermindx-market-intelligence/Mastermind \
  --json state --jq .state)" = "MERGED"
PR_MERGE_SHA="$(gh pr view 25 --repo mastermindx-market-intelligence/Mastermind \
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

Then create and verify a fresh Codex device login directly as the disabled
worker principal:

```bash
sudo /bin/bash "$SOURCE_REPO/ops/executive_os/provision-worker-auth.sh"
sudo /bin/bash "$SOURCE_REPO/ops/executive_os/provision-worker-auth.sh" \
  --verify-only
```

### Dedicated worker authentication

The auth helper runs the pinned native Codex executable as
`_mastermind_worker`, with an otherwise empty environment whose `HOME` and
`CODEX_HOME` are both the worker-only provider home. It verifies the native
signature, OpenAI TeamIdentifier, and exact Codex version before showing the
official device-authorization prompt.

Open the URL shown in that terminal, enter its one-time code, and complete the
OpenAI sign-in in the browser. The helper never reads or copies the operator's
personal `~/.codex/auth.json`; Codex creates a separate
`/var/db/mastermind-executive/workers/codex-01/provider-home/auth.json`
directly as the worker. Do not paste a token, API key, existing `auth.json`, or
device code into the shell, this runbook, a PR, or chat.

Success requires the dedicated file to be a non-empty, regular, non-symlink,
single-link file owned by `_mastermind_worker:_mastermind_worker` with exact
mode `0600` and no ACL. The helper then asks Codex to validate the login while
discarding both output streams and checks the file metadata again. Login status alone is not READY.

`--verify-only` repeats the metadata and login-status checks without starting a
new login or calling the model. A preexisting credential is never overwritten
or repaired unless the administrator passes the explicit `--reauthorize` flag.
`--reauthorize` uses Codex's own `logout` plus device login on a controlling
terminal, then requires the provider inference canary to pass. Do not select a ChatGPT workspace merely because it happens to work; if the intended workspace cannot be bound unambiguously, stop for Chairman/COO ruling.

Pinned Codex `0.147.0` has no `login`/`exec` workspace-selection flag. Do not invent one, and do not hand-edit `auth.json`.

```bash
sudo /bin/bash "$SOURCE_REPO/ops/executive_os/provision-worker-auth.sh" \
  --verify-only
sudo /bin/bash "$SOURCE_REPO/ops/executive_os/provider-inference-canary.sh"
sudo /bin/bash "$SOURCE_REPO/ops/executive_os/provision-worker-auth.sh" \
  --verify-ready
```

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
wrapper for the first start, per-PID canary quarantine, worker-principal live
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
