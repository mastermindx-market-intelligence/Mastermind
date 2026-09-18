# Executive OS off-host disaster recovery — runbook (DR-V1)

Frozen architecture: `research/MASTERMIND_EXECUTIVE_DR_V1_ARCHITECTURE_2026-09-01.md`.
Code: `control_plane/executive_dr.py`, `scripts/executive_dr_cli.py`,
`scripts/dr_drill.py`, `scripts/dr_drill_prune_releases.py`,
`.github/workflows/dr-drill.yml`,
`ops/executive_os/com.mastermind.executive.backup.plist.template`,
`ops/executive_os/run_nightly_backup.sh`.

This runbook never grants itself authority. Every step below is either (a) a
command a session can run today against a disposable or already-verified
artifact, or (b) explicitly marked **CHAIRMAN CEREMONY** — a privileged,
credential-provisioning, or host-mutating act that only the Chairman (or an
operator the Chairman has directed) performs, never a fleet session.

## 1. Standing laws (never violated by any step below)

- **No hot standby, no automatic failover, no second live runtime.** This is
  a backup/restore capability, not replication. Litestream stays behind the
  separately gated DR-L0 falsifier.
- **Restore never overwrites the live database as a first step.** Every
  restore path (`restore_backup_offline` in `control_plane/executive_backup.py`)
  preserves the prior database and sidecars as an owner-only rollback set
  *before* the atomic swap, and automatically restores that rollback set if
  post-swap verification fails.
- **Restore ends in a read-only posture with an EFFECT_UNKNOWN worklist.**
  Restoring durable state never proves what a provider (Codex, Claude, a
  broker) did to the outside world after the last durable Event. Only
  Sol/operator review — never automation — releases modifying work after a
  restore. This is unbounded by design: there is no timer, no retry count,
  and no code path that auto-clears an EFFECT_UNKNOWN item.
- **Transport never owns lifecycle.** `control_plane/executive_dr.py` only
  ever reads an already-created, already-verified local backup
  (`control_plane.executive_backup.verify_backup`) and never constructs,
  claims, requeues, or reconciles a Job/Attempt/Event on its own initiative.
- **Create-only, digest-verified, never-delete-by-default transport.** Every
  ship function refuses to overwrite an existing remote object under the
  same identity (same `export_id`/tag + differing digest = typed
  `REMOTE_DIGEST_CONFLICT`, never a silent overwrite); a matching envelope
  alone is never proof of a duplicate — the actual remote CIPHERTEXT bytes
  are re-hashed (directory: re-hash the destination file; GitHub: re-download
  the asset) before ever reporting success, and a missing object under an
  existing envelope/tag is a typed `OFFHOST_ABSENT`, never a false
  "duplicate" success. Every ship also re-downloads and byte-compares BOTH
  the ciphertext AND the envelope assets it just uploaded before declaring
  done. `control_plane/executive_dr.py` carries no delete capability
  anywhere in its public API — the one deliberate, narrowly-scoped exception
  is `scripts/dr_drill_prune_releases.py` (§6a), which is structurally
  incapable of touching a non-draft (production) release regardless of how
  it is invoked.
- **A corrupt or unverifiable local artifact is quarantined, never deleted.**
  `quarantine_artifact()` renames the file aside with a receipt
  (`<name>.quarantined-<UTCstamp>`, plus a `.quarantine-receipt.json`
  sidecar) and leaves both in place for inspection.
- **The master key never enters a model context, git, Slack, Linear, a
  manifest, or a log.** No fleet session generates, copies, or handles key
  material. `control_plane/executive_dr.py` only ever receives a key as an
  in-memory base64 string the *caller* already possesses (a `--key-file`
  path, a `--key-env` variable, or a drill's `os.urandom(32)` ephemeral key)
  — it never originates one. **The standing production key is never stored
  as a GitHub Actions secret** (§6 item 1) — see the consequence in §2.
- **A transport credential is never a plist environment variable.** A
  launchd plist's `EnvironmentVariables` dict ships inside a world-readable
  `0644` file and is silently overwritten on every reinstall. The nightly
  backup daemon's GitHub token is a `0400` **file**
  (`scripts/executive_dr_cli.py ship --token-file`), exactly the same
  custody pattern as the master key, never an env var the plist would have
  to carry.

## 2. Recovery objectives and how drills measure them

| Objective | Target | Measured by |
|---|---|---|
| RPO (max age of newest valid off-host backup) | 24h while production-armed; per-release while production-inert | age of the newest verified export at the target transport; every DR-D1 drill and release ceremony produces one |
| RTO (declared start → verified read-only availability) | ≤ 4h with the **full runbook**, including host provisioning | measured end-to-end by the ceremony drill (a human timing §4 stages 9-11 against a real or rehearsal host loss); `scripts/dr_drill.py`'s `fetch_to_verified_ms` field is a **component measure only** of its own automated fetch→decrypt→verify path (timed from "fetch start" to "verified": envelope + digests + `verify_restore_drill` + logical-state equality) and can never on its own stand as evidence the ≤4h target is met, because it has no host-provisioning step to measure |
| RCO (external-effect reconciliation before modifying work resumes) | explicit, unbounded-by-automation | never measured by a drill — RCO is a human review gate, not a timer |

Every drill's receipt is the evidence — on success **or failure**: a failed
`scripts/dr_drill.py` run still writes a receipt naming the stage reached
and the typed failure state, and retains its work directory instead of
deleting it, so a failure is investigable, not silent. Drift between a
target and a measured value is a failure state to investigate, not a
footnote to ignore.

**CI cold-restore of a PRODUCTION export is not possible by design, and
that is intentional (§6 item 1).** The automated DR-D1 drill proves the
pipeline mechanism against an ephemeral per-run key; it structurally cannot
and does not prove that any particular production backup is restorable
without the Chairman, because the standing key that could decrypt one never
exists anywhere CI can reach. A cold-restore drill of an *actual production
export* is a ceremony/runbook activity performed on a trusted host with the
operator supplying the key file (§6), never an automated workflow step.

## 3. Clean-host drill (DR-D1) — routine, no ceremony required

Runs automatically: `.github/workflows/dr-drill.yml`, weekly
(`0 15 * * 0`, i.e. Sunday 15:00 UTC — outside the reserved 05:00-11:00 UTC
window) plus `workflow_dispatch`. On a hosted, disposable `ubuntu-latest`
runner:

```
python3 -I -S -B scripts/dr_drill.py --receipt-out drill-receipt.json --repo "<owner>/<repo>"
```

This fabricates a production-representative RuntimeStore (same migrations,
a small synthetic Jobs/Attempts/Events workload), backs it up, encrypts it
with a fresh ephemeral key held only in the runner's memory for that run,
ships it as a **draft** GitHub release under the reserved `dr-export/*` tag
namespace (authenticated by the workflow's own repo-scoped `GITHUB_TOKEN` —
mapped explicitly into the run step's `env:`, since Actions does not inject
it into a step's process environment automatically — zero credential
enrollment), **deletes every local copy**, fetches it back, decrypts, runs
`verify_restore_drill`, and asserts the restored workers/jobs/attempts/events
are byte-for-byte equal to what was recorded before the local copies were
deleted. A local, network-free equivalent — this is what the test suite and
CI's own import-graph verification both exercise, since transport selection
does not change what gets imported, only which transport function is
called:

```
python3 -I -S -B scripts/dr_drill.py --offline --receipt-out drill-receipt.json
```

(`--offline` swaps GitHub releases for the local create-only directory
transport — same Stage A-D chain, zero network, used by CI and the test
suite.) Nothing in this section requires root, a key file, or the control
host: it proves the pipeline itself, not the live host's actual database.

**Why draft releases:** a draft creates no git tag/ref in the repository at
all until a human publishes it, so routine weekly/on-demand drills never
accumulate a permanent, undecryptable-elsewhere tag on the product repo.
One real API quirk this depends on: GitHub's "get a release by tag" endpoint
never returns a draft release — `_github_get_release_by_tag` falls back to
listing releases and filtering by `tag_name` when the direct lookup 404s,
bounded to a handful of pages.

## 3a. Drill-lane retention (fixed-count pruning of ephemeral artifacts)

After every successful (non-offline) drill, `.github/workflows/dr-drill.yml`
runs:

```
python3 -I -S -B scripts/dr_drill_prune_releases.py --repo "<owner>/<repo>" --keep 8 --summary-out "$GITHUB_STEP_SUMMARY"
```

This keeps the newest 8 releases that are BOTH `draft=true` AND tagged under
`dr-export/*`, deleting the rest, and logs every deletion to the run's step
summary. It is scoped in **code**, not by argument default: the script only
ever lists+deletes releases matching both conditions, so a production/vault
release (always non-draft, always a different tag prefix by construction)
is structurally unreachable regardless of how this script is invoked. It
never runs after a failed drill (`if: success()`), so a failed drill's
release, if any exists, stays for investigation.

## 4. Restore stages — bound to exact commands

This is the packet's restore-stage list (§8), each stage bound to the exact
command that performs it. **A failed verification at any stage leaves the
live database untouched** — nothing before stage 9 (`restore_backup_offline`)
can mutate the live runtime, and stage 9 itself preserves a rollback set
before it ever touches the live file.

1. **Select exact export.** Decide a target `export_id`/tag: newest valid by
   `created_at`, or an explicit historical one. (§7: the remote store IS the
   catalog — list release tags under `dr-export/*`, or directory-transport
   object names. The production/vault lane's releases are non-draft, so the
   direct by-tag lookup works for them without the drill lane's list-fallback.)
2. **Download to private staging.** Use `--token-file`, pointing at a
   0400 file holding the vault PAT for this one-off restore (the same
   custody discipline as the standing key; `--token-env` remains available
   if an operator has the credential in their own interactive shell instead):
   ```
   python3 -I -S -B scripts/executive_dr_cli.py fetch \
     --tag dr-export/<stamp>-<export_id> --dest-dir /path/to/private/staging \
     --transport github --repo <owner>/<vault-repo> --token-file /path/to/vault-token
   ```
3. **Ciphertext digest check.** Done automatically inside `fetch` (digest
   compared against the envelope before the fetch receipt is returned).
4. **Decrypt (MAC-verified).**
   ```
   python3 -I -S -B scripts/executive_dr_cli.py restore-verify \
     --ciphertext <fetched>.sqlite3.enc --envelope <fetched>.envelope.json \
     --output-dir /path/to/private/decrypted \
     --key-file /path/to/executive-dr-key.b64
   ```
   The MAC is recomputed and compared **before** any decrypt or output file
   is created — wrong key, truncation, a bit-flip, or envelope substitution
   each fail typed with zero plaintext output. This same command also runs
   step 5-7 below via the existing `verify_restore_drill`. If this host's
   `/usr/bin/openssl` is a different family (writes vs omits the classic
   `Salted__` header — LibreSSL writes it, OpenSSL 3.x omits it under the
   identical invocation) than the one that produced the export, decryption
   still works: the stored ciphertext is always normalized headerless, and
   the local binary's family is feature-detected once per process and
   compensated for automatically. Override the binary with
   `--openssl-binary` or the `MASTERMIND_DR_OPENSSL` environment variable if
   this host has more than one and the default `/usr/bin/openssl` is wrong.
5. **Plaintext digest check.** Done automatically inside `decrypt_export`
   (plaintext hash recomputed and compared to the envelope's
   `plaintext_sha256` before the decrypted file is renamed into place).
6. **Single-link regular-file/ownership/mode check.** Enforced by
   `control_plane.executive_backup.verify_backup`'s
   `_assert_private_regular_file` (single hard link, owner = the running
   principal, mode `0600`) via `verify_restore_drill`.
7. **SQLite quick/integrity/foreign-key checks + `verify_restore_drill`.**
   Both run inside the `restore-verify` command above (existing Executive
   verifier — no second verifier, no second manifest schema).
8. **Event-tail + reconciliation preview.** Manual step (human review): open
   the restored database read-only and inspect the tail of `events` plus any
   Attempt whose `status` implies outstanding provider-side effect. This is
   the EFFECT_UNKNOWN worklist — there is no command that auto-generates or
   auto-clears it.
9. **Explicit admin stop/lock proof.** **CHAIRMAN CEREMONY** (or
   operator-directed): stop `com.mastermind.executive.control` and
   `com.mastermind.executive.worker.codex` (`ops/executive_os/service-control.sh
   stop`), confirming the service marker/lock are clear. This step requires
   root and is never run by a fleet session.
10. **Preserve live DB as rollback artifact + one offline atomic restore.**
    **CHAIRMAN CEREMONY.**
    ```
    python3 -I -S -B scripts/executive_os_phase1c.py restore-backup \
      --config <control.json> <backup-name>.sqlite3
    ```
    Internally: `control_plane.executive_backup.restore_backup_offline` —
    verifies, copies the live DB+sidecars aside as a rollback set, stages
    and TX-9-invalidates the incoming database, then performs one atomic
    `os.replace`. A failure after replacement automatically restores the
    preserved rollback set.
11. **Start read-only; reconcile EFFECT_UNKNOWN before any modifying work.**
    **CHAIRMAN CEREMONY / Sol-operator review.** Restart the control service
    only after the stage-8 worklist has been reviewed. There is no
    "resume automatically" path — this is a human decision every time.
    **This is also the point at which the ≤4h RTO target (§2) is measured:**
    time the full interval from declared loss (start of stage 9) to this
    step's completion.

## 5. Failure states

Every failure raised by `control_plane/executive_dr.py` carries a typed
`state` (`DRFailureState`, a closed enum) — never a bare string. Catch
`ExecutiveDRTypedError` and read `.state`. The **Raised by** column marks
whether a state is something the code in this repo can actually produce
today (**CODE**), or whether it names a condition the runbook/ceremony/human
process must recognize on its own (**PROJECTION** — the observability layer
computes it from receipts, not a raised exception; **CEREMONY** — only
meaningful during a privileged operator action this repo's code does not
perform). A row marked PROJECTION/CEREMONY is not a promise the exception
type will ever appear in a stack trace.

| State | Meaning | Typical cause | Raised by |
|---|---|---|---|
| `NO_BACKUP` | No verified local backup manifest to export | `export` run before any backup exists | CODE (`encrypt_export`) |
| `STALE` | An off-host copy exists but exceeds the RPO target | — | PROJECTION (§DR-OBS1 observability only; no function in `executive_dr.py` raises this) |
| `LOCAL_CORRUPT` | A local artifact/envelope failed digest or structural verification | Disk corruption, partial write, tampering, an openssl subprocess failure | CODE |
| `OFFHOST_ABSENT` | No object exists at the requested transport identity, including an envelope that exists with its ciphertext object missing | Wrong tag, never shipped, partial prior write, or already-pruned by a privileged maintenance action | CODE |
| `REMOTE_DIGEST_CONFLICT` | Same identity (tag/export_id) already exists with a **different** digest — including a remote object whose actual bytes don't hash to its own envelope's declared digest | Never overwritten — investigate which export is authoritative | CODE |
| `CREDENTIAL_LOST` | Transport credential (file or env var) unset, empty, or rejected (401/403) | Ceremony not completed, or a rotated/expired token | CODE |
| `KEY_LOST` | The key generation needed to decrypt an old export is gone | Rotation retired a generation before every backup encrypted under it expired | CEREMONY (a key-custody failure mode, not a code path) |
| `KEY_INVALID` | Supplied master key is not valid base64 or not 32 bytes | Wrong file/env content | CODE |
| `REMOTE_UNAVAILABLE` | Network/DNS/5xx from the transport, an unreachable openssl header-family probe, or a non-https redirect target refused outright | Transient — safe to retry manually after investigation | CODE |
| `QUOTA_FULL` | Transport rejected the write for space/quota reasons | Retention policy needs a privileged prune | PROJECTION (GitHub's actual quota-rejection responses are not yet distinguished from other REMOTE_UNAVAILABLE cases; treat any persistent write rejection as possibly this) |
| `UPLOAD_EFFECT_UNKNOWN` | The upload's remote effect could not be confirmed (checksum-after-upload mismatch on EITHER the ciphertext or the envelope asset, or an ambiguous response) | The remote object is **left in place**, never blindly re-put or deleted; reconcile by hand | CODE |
| `PARTIAL_CHAIN` | A multi-stage operation was interrupted partway | Resume from the last confirmed stage; nothing auto-resumes | CEREMONY (a human-recognized runbook state; no function raises this by name) |
| `POINT_AMBIGUOUS` | More than one candidate export matches a selection | Name an explicit `export_id`/tag | CEREMONY (an operator/UI selection concern, not a code path) |
| `RELEASE_SCHEMA_MISMATCH` | A GitHub release's asset/body shape does not match what this code expects | Manual object, or a schema drift; inspect the release directly | CODE |
| `VERIFIER_UNAVAILABLE` | `/usr/bin/openssl` (or the configured `--openssl-binary`/`MASTERMIND_DR_OPENSSL`) could not be invoked, including a failed header-family probe | Host is missing the platform binary, or a sandbox blocked `subprocess` | CODE |
| `SERVICE_MARKER_LIVE` | The Executive service marker is present during an offline-restore attempt | Stop the service first (stage 9) | CODE (in `control_plane/executive_backup.py`, not modified by DR-V1) |
| `DISK_INSUFFICIENT` | Not enough space to stage an export/fetch (ENOSPC mapped explicitly in the write/copy helpers) | Free space or point staging elsewhere | CODE |
| `ROLLBACK_UNAVAILABLE` | A restore rollback set could not be preserved | Investigate before ever attempting the restore again | CEREMONY (a stage-10 failure mode inside `restore_backup_offline`, existing code not modified by DR-V1) |
| `ENVELOPE_INVALID` | Envelope failed the closed-field-set / type / pattern check, including an ingress that exceeds the 64 KiB bound before it is ever written to disk | Unknown/missing key, malformed value — never a partial trust | CODE |
| `MAC_MISMATCH` | Encrypt-then-MAC authentication failed | Wrong key, truncated file, a bit-flip, or envelope substitution — all indistinguishable by design, all refuse to decrypt | CODE |
| `OUTPUT_CONFLICT` | A decrypt/fetch destination path already exists | Choose a fresh destination; nothing here silently overwrites | CODE |

`NO_BACKUP`, `STALE`, `DISK_INSUFFICIENT`, `ROLLBACK_UNAVAILABLE`, and
`PARTIAL_CHAIN` are named by the frozen packet's failure catalog; `KEY_INVALID`,
`ENVELOPE_INVALID`, `MAC_MISMATCH`, and `OUTPUT_CONFLICT` are additions this
build needed for envelope-structural and local-I/O safety that the packet's
explicitly non-exhaustive list ("…") did not itemize.

## 6. Chairman ceremony — standing key + transport provisioning

Everything above this line ships in source today. The items below are the
**one** privileged, one-time (plus periodic rotation) act that turns
`transport_target=github-release`/`retention_class=nightly` from reviewed
material into an armed capability. None of it is performed by a fleet
session.

1. **Generate the standing master key.**
   `openssl rand -base64 32 > executive-dr-key-v1.b64` on a trusted device
   (never inside a fleet session). Store the plaintext in the operator's
   password manager ONLY, plus the 0400 host file below. **Do NOT also store
   it as a GitHub Actions secret** (adversarial review M6): the production
   vault IS a GitHub repo, so a GitHub Actions secret holding the key that
   decrypts that vault's contents would put the same provider in custody of
   both the ciphertext and the key — the exact single-provider collapse
   client-side encryption exists to prevent. This is a deliberate,
   accepted limitation: it means CI can never cold-restore a production
   export (§2) — only the Chairman, from the password manager or the host
   file, can.
2. **Install the host key file.** Copy `executive-dr-key-v1.b64` to
   `/Library/Application Support/MastermindExecutive/config/executive-dr-key.b64`
   (the `DR_KEY_FILE` path `install.sh` already renders into the backup
   daemon's `ProgramArguments`), owned `_mastermind_exec:_mastermind_exec`,
   mode `0400`.
3. **Provision the vault repository.** Create
   `mastermindx-market-intelligence/executive-dr-vault` (private). Mint a
   fine-grained PAT scoped to that ONE repository, Contents: Read and write,
   Releases: Read and write, no other scope. Install it as a **file**, not
   an environment variable:
   `/var/db/mastermind-executive/control/dr/executive-dr-token`
   (the `DR_TOKEN_FILE` path `install.sh` already renders into the backup
   daemon's `ProgramArguments`), owned `_mastermind_exec:_mastermind_exec`,
   mode `0400`. **Never** a broad multi-repo token, never inside this repo,
   and never a plist `EnvironmentVariables` entry (adversarial review B3 —
   that dict lives in a world-readable `0644` file and is clobbered on
   every reinstall besides).
4. **(Optional, preferred for production) Provision T-R2.** Following the
   estate's existing `R2_ATTESTED_HISTORY_*` scoped-token pattern: a
   dedicated bucket `mastermind-executive-dr`, PutObject+GetObject+ListBucket
   only, no delete, versioning on. `control_plane/executive_dr.py` does not
   yet ship an S3-compatible transport function — this is future work behind
   the same typed-failure/create-only contract; do not build ad hoc S3 calls
   outside that module when it lands.
5. **Enable the backup daemon.** Only after 1-3 above:
   ```
   sudo launchctl enable system/com.mastermind.executive.backup
   sudo launchctl kickstart system/com.mastermind.executive.backup   # or wait for the next StartCalendarInterval fire
   ```
   `StartCalendarInterval` fires in the HOST's own local time zone as
   macOS/launchd is configured — the plist's `TZ` environment entry affects
   only the spawned process, never launchd's scheduling clock. The shipped
   default (09:15 local) assumes a US Pacific host and lands at 16:15-17:15
   UTC across PDT/PST, outside the reserved 05:00-11:00 UTC render window in
   both cases; re-verify with `systemsetup -gettimezone` on the actual
   control host and re-pick Hour/Minute in the plist if it differs.
   Confirm the first run's receipts in `$RUNTIME_ROOT/control/dr-receipts/`
   all read `"status": "OK"` before considering this ceremony complete.
6. **Key rotation.** Generate a new key, install it under a new `--key-id`
   (e.g. `v2`), update the daemon's config to the new generation. Retain the
   old key file until every retained backup encrypted under it has expired
   per the retention policy (§Retention, packet §12) — deleting an old key
   before then makes those backups permanently unrecoverable, which is
   exactly the `KEY_LOST` state above. (There is no GitHub secret copy to
   retire in parallel — see item 1.)

## 7. Reference: files and what owns what

| File | Owns |
|---|---|
| `control_plane/executive_dr.py` | Envelope schema, crypto (encrypt-then-MAC with cross-openssl-family normalization), GitHub/directory transports, quarantine. Carries no delete capability. |
| `scripts/executive_dr_cli.py` | Operator CLI: `export`, `ship`, `fetch`, `verify-envelope`, `restore-verify`, `drill-local` |
| `scripts/dr_drill.py` | DR-D1 clean-host drill driver (fabricate → backup → export → ship → discard → fetch → verify); writes a receipt on success OR failure |
| `scripts/dr_drill_prune_releases.py` | Fixed-count retention for the drill lane's draft `dr-export/*` releases ONLY — structurally cannot touch a production/vault release |
| `.github/workflows/dr-drill.yml` | Weekly + on-demand CI drill, plus post-drill pruning |
| `ops/executive_os/com.mastermind.executive.backup.plist.template` | Nightly launchd daemon definition (ships disabled) |
| `ops/executive_os/run_nightly_backup.sh` | The daemon's actual sequence: phase1c `backup` → `verify-backup` → `executive_dr_cli.py export` → `ship`; retains the local export to a survives-process-exit directory on ship failure |
| `control_plane/executive_backup.py` | Everything this runbook calls "existing" — online/offline backup, manifest, `verify_backup`, `verify_restore_drill`, `restore_backup_offline`. **Not modified by DR-V1.** |
