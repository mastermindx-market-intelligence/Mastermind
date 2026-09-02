# Executive OS Off-Host Disaster Recovery V1 — Architecture & Contracts (DR-C0)

**Operation:** `mastermind-executive-os-offhost-disaster-recovery-20260830-sol-pro-001`
**Program CEO:** Fable COO (Chairman direct-delivery 2026-09-01; Chairman override of same date: continue to full completion without per-step CEO/Chairman rulings)
**Status:** DR-C0 FROZEN pending build (DR-B1/O1/R1) and drill (DR-D1)
**Audit basis:** DR-A0 (macro `fba6b4ef6f81`, `WS:EXECUTIVE-OS-DISASTER-RECOVERY`, `DSC:EXECUTIVE-OS-HAS-NO-OFFHOST-RECOVERY-COPY`)

---

## 0. Ground truth this architecture stands on

1. **There is no off-host copy of Executive lifecycle state and no mechanism that could create one** (DR-A0, verified 2026-09-01): no transport in repo or on host, no backup cadence of any kind, Time Machine has no machine directory, every mounted volume shares the control-host failure domain.
2. **Executive OS is production-inert by design**: both LaunchDaemons report `state=missing` (never enabled), sockets absent — the H0/P0 acceptance posture. The DR capability must therefore land **in source and in the release/install path**, so the next authorized arming ceremony brings backup cadence and off-host transport up *with* the runtime, and must additionally be **provable now** in an isolated environment that does not depend on the control host or on service arming.
3. **The existing Stage-A primitive is correct and is reused, not replaced**: `control_plane/executive_backup.py` — SQLite online Backup API, O_EXCL temp + fsync, 0600, closed manifest `mastermind.executive_backup_manifest/v1` (sha256 + integrity/foreign-key/schema attestations), immediate re-verify; offline-only restore that refuses while the service marker/lock is live.
4. **Fleet shells cannot sudo** (no TTY). Anything requiring root or `_mastermind_exec` context on the control host is ceremony-scoped and must be delivered as reviewed runbook + installer material, never attempted from a session.
5. **Credential reality:** the estate's R2 pattern (scoped per-lane tokens as Actions secrets, e.g. `R2_ATTESTED_HISTORY_*`) exists, but no Cloudflare API token is reachable, so minting a DR bucket/token is a credential-enrollment ceremony. The only write credential available today without enrollment is the fleet GitHub token.

## 1. Authority boundary (restates the packet; binding)

**Executive OS owns:** the canonical live DB; backup creation through its existing API/CLI; schema/application verification; explicit offline restore; startup reconciliation after restore; last known Job/Attempt/Worker/Event truth.

**Backup transport owns:** copying already-created, already-verified backup artifacts; encryption; create-only destination behavior; remote retention; transport receipts.

**Transport must never own:** lifecycle; retry decisions; provider-effect reconciliation; automatic promotion; a second active database; a replacement Event stream; scheduling company work; restoring while the service is live. **No hot standby, no automatic failover, no second runtime — REJECTED_BY_DESIGN for V1.** Litestream remains behind the DR-L0 falsifier and its restore/reset MCP is never exposed on a model-facing tool surface.

## 2. Recovery objectives (frozen for V1)

| Objective | Target | Basis |
|---|---|---|
| **RPO** (max age of newest valid off-host backup) | **24 h** while production-armed; **per-release** while production-inert (a fresh verified export at every release/install ceremony and every drill) | DB is small and low-churn today; nightly launchd cadence is the cheapest reliable unit on this estate |
| **RTO** (declared start → verified read-only Executive availability) | **≤ 4 h** with the full runbook (host provisioning + every restore stage), measured end-to-end by the ceremony drill | single-DB restore + verification chain is minutes; the budget is dominated by host provisioning |
| **RCO** (external-effect reconciliation before modifying work resumes) | **explicit, unbounded-by-automation**: restore ends in read-only posture with an EFFECT_UNKNOWN worklist; only Sol/operator review releases modifying work | packet §RPO/RTO; restoring state never proves what a provider did after the last durable Event |

Targets are re-measured by every DR-D1 drill; drift between target and measured is a failure state, not a footnote. **The automated CI drill (§9) measures and reports `fetch_to_verified_ms` as a COMPONENT of RTO only** (adversarial review M7) — it has no host-provisioning step to measure, so it can never on its own stand as evidence the ≤4h target is met; that requires the full ceremony drill described in the runbook.

## 3. Artifact & manifest contract

- Backup creation stays `create_online_backup` (or `create_offline_backup` while the service is stopped). The DR layer consumes its **existing** artifact + `mastermind.executive_backup_manifest/v1` manifest verbatim — no second manifest schema for local backups.
- The off-host object adds one **export envelope**, `mastermind.executive_dr_export/v1`:
  - `export_id` (uuid4 hex), `created_at` (UTC), `backup manifest` (embedded verbatim), `cipher` (`aes-256-gcm`), `nonce`, `key_id` (opaque label, never key material), `plaintext_sha256`, `ciphertext_sha256`, `byte_size`, `source_release_commit`, `transport_target` (opaque class label, e.g. `github-release` / `s3-immutable`), `retention_class`.
  - No hostnames, usernames, tokens, socket paths, or private filesystem paths beyond what the existing backup manifest already carries.
- **Identity law:** same `backup_id` + same digest = duplicate (idempotent skip); same `backup_id` + different digest = CONFLICT (typed failure, quarantine, never overwrite). Object names are content-addressed: `executive-<UTCstamp>-<backup_id>.sqlite3.age` style naming with the digest in the envelope.
- Corrupt or unverifiable artifacts are **quarantined** (renamed aside with a receipt), never silently deleted.

## 4. Encryption & key custody

- Client-side authenticated encryption **before** any byte leaves the host. **Binding (census 2026-09-01):** the production Executive runtime runs `python3.12 -I -S` — isolated, no site-packages — so pip dependencies (including `cryptography`) structurally cannot reach production code, and no AEAD library exists in base deps. V1 therefore uses the **stdlib + system-openssl encrypt-then-MAC composition**:
  - Per-export random 16-byte salt + nonce; HKDF-style derivation (stdlib `hmac`/`hashlib`, SHA-256) of two independent subkeys (cipher, MAC) from the master key generation.
  - AES-256-CTR via the platform `/usr/bin/openssl` (macOS LibreSSL / Linux OpenSSL — already-present platform binaries, no new supply-chain admission), key material passed via file descriptor or environment, **never argv**.
  - HMAC-SHA256 (stdlib) over `envelope-header ‖ nonce ‖ ciphertext`; MAC verified before any decrypt output is trusted (encrypt-then-MAC). Truncated/tampered/wrong-key inputs fail typed, with zero plaintext emitted.
  - The composition, not the primitive, is the reviewed unit; DR-L0-class falsifier tests cover wrong key, truncated object, bit-flip, and header substitution.
- **The key never enters a model context, git, Slack, Linear, a manifest, or a log — and no fleet session generates or copies key material at all** (session-side key handling is blocked by the harness, and rightly: custody that survives host loss requires the Chairman anyway). Custody design:
  1. **Drill lane:** an **ephemeral per-run key** generated inside the workflow step, held only in the runner's memory/env for that run and never persisted — sufficient to prove the full encrypt→ship→retrieve→decrypt→restore chain in a clean environment. Cross-run cold-restore proof is exercised once the standing key exists.
  2. **Standing key (production):** provisioned in ONE Chairman ceremony command (runbook §ceremony): generate → password-manager/offline copy → install 0400 key file for `_mastermind_exec` on the host. **The standing key is never also stored as a GitHub Actions secret (adversarial review M6, corrects the original DR-C0 draft of this section)**: the vault (production/off-host object store) already IS a GitHub-hosted repo, so a GitHub Actions secret holding the decryption key would put the SAME provider in custody of both the ciphertext and the key that opens it — the exact single-provider collapse client-side encryption exists to prevent. Consequence, stated honestly rather than worked around: **CI cannot cold-restore a production export** — the standing key lives ONLY in the Chairman's password manager and the 0400 host file, never in any CI-reachable secret store. A cold-restore *drill* of an actual production export is therefore a ceremony/runbook activity performed on a trusted host with the operator supplying the key file, never an automated workflow step. The DR-D1 CI workflow instead proves the pipeline itself against an ephemeral per-run key (item 1 above) — that is a complete, sufficient proof of the mechanism, not a proof that any particular production backup is restorable without the Chairman. Until the ceremony is run, the DR-PROMOTE ruler's key-custody item is honestly **PARTIAL**.
- `key_id` in the envelope names the key generation (`v1`, `v2` …); rotation = new secret + new key_id; old generations retained until every retained backup encrypted under them expires. Wrong-key and key-loss behavior are acceptance-tested (typed errors, no partial plaintext).

## 4b. Configuration binding (census 2026-09-01)

`load_control_config` enforces a CLOSED key set (`scripts/executive_os_phase1c.py:219-225`). Offhost settings join `_CONFIG_OPTIONAL` as one all-or-nothing group (`_DR_OFFHOST_CONFIG_KEYS`, precedent: `_CEO_INGRESS_CONFIG_KEYS`): `dr_offhost_target` (target class label), `dr_export_staging_root`, `dr_key_path` (path to the on-host key file, 0400 `_mastermind_exec`; never key material), `dr_vault_coordinate` (opaque remote coordinate, e.g. `owner/repo` or bucket name). Absent group = DR transport disarmed; the runtime never fails on its absence.

## 5. Off-host targets (pluggable; two admitted classes)

**T-GH — GitHub release assets (armed NOW for the drill lane; vault repo for production at ceremony).**
- **Drill lane (no credential provisioning at all):** the DR-D1 workflow ships exports as **DRAFT** release assets (adversarial review M10 — a draft creates no git tag/ref in the repository until published, so routine weekly/on-demand drills never accumulate a permanent, undecryptable-elsewhere tag) on the Mastermind repo itself under the reserved tag namespace `dr-export/*`, authenticated by the workflow's **ephemeral, repo-scoped `GITHUB_TOKEN`** (`permissions: contents: write`) — least-privilege by construction, zero long-lived credential, zero token copying. Census confirms the repo's release namespace is otherwise unused. A deterministic, code-scoped fixed-count retention step (`scripts/dr_drill_prune_releases.py`) keeps the newest 8 of these draft `dr-export/*` releases and deletes the rest after every successful drill — see §12.
- **Production lane:** dedicated private repo `mastermindx-market-intelligence/executive-dr-vault` (created 2026-09-01) as the sole DR object store — one **non-draft** release per export, asset = encrypted artifact, body = envelope JSON — written by a **fine-grained PAT scoped to that one repo**, provisioned by the Chairman at the arming ceremony (runbook item; no broad token is ever stored for this) and delivered to the host as a 0400 token FILE (adversarial review B3), never a plist environment variable or a GitHub Actions secret.
- Rationale: the only failure-domain-independent store writable today without credential enrollment; GitHub already holds the company's implementation bytes, so no *new* trust anchor is introduced; assets are content-checksummed after upload (re-download digest compare, both the ciphertext AND envelope assets).
- Create-only is enforced at the application layer: the uploader refuses when a release tag or asset name already exists with a different digest (conflict = typed failure; a matching digest re-download is the only path to reporting a duplicate). The production/vault lane carries no delete tooling in `control_plane/executive_dr.py` at all — deletion of a production export is a privileged maintenance action with receipts, never automated. The drill lane's separate, narrowly-scoped `scripts/dr_drill_prune_releases.py` (§12) is the one deliberate, code-reviewed exception, and it is structurally incapable of touching a non-draft (production) release.

**T-R2 — S3-compatible immutable object store (preferred production; armed at ceremony).**
- Dedicated R2 (or B2) bucket `mastermind-executive-dr`, scoped token: PutObject + GetObject + ListBucket, **no delete**, following the estate's existing `R2_ATTESTED_HISTORY_*` scoped-token pattern; versioning on; `rclone --immutable`-class behavior validated against the concrete backend before trust.
- Everything except the credential ships in this program (config keys, transport code, tests, runbook §ceremony); the enrollment itself is one bounded Chairman/Sol ceremony.

## 6. Cadence

- **While production-inert:** every DR-D1 drill and every release ceremony produces and ships a verified export; the scheduled CI drill (weekly) keeps the pipeline proven.
- **When production arms:** `com.mastermind.executive.backup.plist.template` — a launchd daemon (`StartCalendarInterval`, nightly, RunAtLoad false) running as `_mastermind_exec`: socket `backup` → `verify-backup` → export/encrypt → ship → receipt. Failure of any step leaves the runtime untouched (transport failure never blocks lifecycle) and writes a typed receipt the observability projection can surface.
- Backup tooling failure modes (remote down, quota full, credential expired, partial upload) end in typed receipts + stale-copy state, never retries that mutate lifecycle state and never un-shipped silent success.

## 7. Recovery catalog

The remote store IS the catalog: object listing + embedded envelopes (content-addressed, signed by digest). Any local index is a cache rebuilt from remote envelopes. Point selection = newest valid by `created_at` + envelope verification, or an explicit historical `export_id`. Clock skew never orders alone — `backup_id`/Event-tail coordinates in the embedded manifest break ties.

## 8. Restore stages (unchanged from packet; bound to existing code)

select exact export → download to private staging → ciphertext digest check → decrypt (AEAD auth) → plaintext digest check → single-link regular-file/ownership/mode check → SQLite quick/integrity/foreign-key checks → `verify_restore_drill` (existing Executive verifier, exact release contract) → Event-tail + reconciliation preview → explicit admin stop/lock proof → preserve live DB as rollback artifact → one offline atomic `restore_backup_offline` → start read-only → reconcile EFFECT_UNKNOWN before any modifying work. **A failed verification at any stage leaves the live DB untouched.** Restore never overwrites as a first step and never rewrites historical Event facts.

## 9. Clean-host drill (DR-D1) — provable without the control host

A scheduled + manually dispatchable GitHub Actions workflow on a **hosted** (disposable, non-control-host) runner:
1. Fabricates a production-representative RuntimeStore DB from the exact release source (same migrations, synthetic Jobs/Attempts/Events workload).
2. Runs the full Stage A–D chain: backup → verify → export/encrypt → ship to the vault → **discard the local copy** → retrieve on the same fresh environment → full restore verification chain → Event-tail equality against the recorded pre-loss state.
3. Measures and publishes the age of the newest valid export and a `fetch_to_verified_ms` component timing (retrieve→verified), and emits a drill receipt artifact — success OR failure (adversarial review M8: a failed drill still writes a receipt naming the stage reached and the typed failure state, and its work directory is retained rather than deleted). **`fetch_to_verified_ms` is a component measure of this automated path only, never the packet's §2 ≤4h RTO target** (adversarial review M7) — that target additionally includes host provisioning and is measured end-to-end by the full ceremony drill in the runbook, not by this CI job alone.
4. Uses only repo source + the workflow's own ephemeral `GITHUB_TOKEN` and an **ephemeral, in-memory, per-run key generated inside the step** (§4 item 1) — by construction zero dependence on the failed host's filesystem AND zero dependence on any standing secret (adversarial review M6: the standing production key is never stored as a GitHub Actions secret, so this CI job cannot and does not prove cold-restore of an actual production export — only of the pipeline mechanism itself, which is what it is designed to prove).
The drill of the *live host's actual DB* additionally requires the `_mastermind_exec` ceremony and is a runbook item for the arming ceremony; the packet's ruler item 1 ("current production-representative backup verified off-host") is satisfied per-release while production is inert, and nightly once armed.

## 10. Failure states

Every case from the packet's failure-state list maps to a typed, receipt-backed state (`NO_BACKUP`, `STALE`, `LOCAL_CORRUPT`, `OFFHOST_ABSENT`, `REMOTE_DIGEST_CONFLICT`, `CREDENTIAL_LOST`, `KEY_LOST`, `REMOTE_UNAVAILABLE`, `QUOTA_FULL`, `UPLOAD_EFFECT_UNKNOWN`, `PARTIAL_CHAIN`, `POINT_AMBIGUOUS`, `RELEASE_SCHEMA_MISMATCH`, `VERIFIER_UNAVAILABLE`, `SERVICE_MARKER_LIVE`, `DISK_INSUFFICIENT`, `ROLLBACK_UNAVAILABLE`, …). No automatic fallback to an older backup without explicit selection + receipt. `EFFECT_UNKNOWN` blocks blind retry and failover — including for uploads: an interrupted upload is reconciled by digest comparison, never blind re-put over an existing object.

## 11. Observability (DR-OBS1)

Derived, low-cardinality projection through existing OBS-F0 seams only (no new monitor store): last local backup success, last off-host verified copy, age vs RPO, upload/remote-verification failures, restore-drill age, retention errors. A green metric is not proof the artifact restores; drills remain required. Control Room may render the packet's `Executive recovery:` block as a diagnostic projection, never lifecycle.

## 12. Retention (V1)

Drill exports: keep 8 weekly. Production nightly: 14 daily, 8 weekly, 12 monthly, plus protected pre-migration/pre-release exports. Deletion of a PRODUCTION off-host backup is a privileged maintenance action with receipts; models never prune production backups.

**Amendment (adversarial review M10):** the DR-D1 drill lane ships as DRAFT GitHub releases specifically so no permanent git tag/ref accumulates from routine (weekly + on-demand) drills, AND is paired with `scripts/dr_drill_prune_releases.py`, a deterministic fixed-count-retention CI step (`.github/workflows/dr-drill.yml`, runs after every successful drill) that keeps the newest 8 `draft=true` releases whose tag starts with `dr-export/` and deletes the rest, logging every deletion to the run's step summary. This is scoped in CODE, not by argument default alone: the script only ever lists+deletes releases matching BOTH `draft=true` AND the tag prefix, so a production/vault-lane release (always shipped `draft=False` by `executive_dr_cli.py ship`, never with the drill's tag prefix by construction of `_export_tag`) is structurally unreachable by it regardless of how it is invoked. The "models never prune backups" rule above is therefore unchanged for production data — this exception is narrowly the ephemeral drill-lane cleanup a fixed CI step performs deterministically, not ad hoc model-directed deletion of anything a restore could ever depend on.

## 13. What this wave deliberately does NOT do

- Does not start, enable, or arm any Executive service (H0/P0 lane's authority).
- Does not install anything on the control host (ships installer material + runbook for the ceremony).
- Does not install Litestream (DR-L0 separately gated; V1 value bar: beat "ship verified backups more often").
- Does not put restore/reset capability on any model-facing tool surface.
- Does not touch RuntimeStore schema or the existing backup primitive's semantics.
