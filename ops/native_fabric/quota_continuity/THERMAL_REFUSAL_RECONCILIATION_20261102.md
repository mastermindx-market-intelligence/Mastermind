# Thermal-refusal historical checker and reconciler

## Named case and the observed gap

The retained native Fabric run
`terminal-news-sidebar-20261102-c4-current-build-001`, rooted and parented at
`terminal-news-sidebar-20261018-c4`, was a `fix_build` request routed to
`POOL=minimax MODEL=MiniMax-M3 HOST=ubuntu1 MODE=minimax KEY=- REASON=minimax_first
ESCALATE_TO=glm-flash`, with `cwd=~` and background execution off. The remote
lane refused the request at admission with
`REMOTE_SUB_ADMISSION_REFUSED {... "reasons":["host_temperature_at_or_above_limit"] ...}`
(241 bytes, SHA-256 `9226eff028a331231dfb4b1b0724ae44285f89240e338de98c6107b2ae6ece4d`).
The controller returned `rc=75`, the incumbent ledger recorded
`signal=admission reason=remote_admission_refused`, and the continuation closed
with `controller_rc=75 reason=continuation_evidence_unqualified` and no
successor run.

No provider or worker execution occurred: the retained result is a refusal line,
the log records `USAGE_RECEIPT_MISSING` and
`REMOTE_CLEANED transport=1 receipt_saved=0 usage_saved=0`, and no usage,
process, provider or session receipt was published. The missing implementation
was the reason the retained refusal could not be reconciled: the incumbent
controller had no read-only proof for this case and no explicit reconciler, so
the run stayed indefinitely unreconciled. This change adds exactly those two
capabilities and nothing else.

## What the checker proves

`candidate/native_thermal_refusal_check.py` is a fixed-case, read-only
diagnostic. It never writes a receipt, changes status, retries, accepts a
review, admits new work, or touches the thermal limit, route, admission or
accounting policy. It reuses the incumbent safe primitives from
`native_plain_packet_check.py` — `EvidenceReadSet`, `DirectoryChain`, `digest`,
`strict_json`, `identity` and the `owner_path` no-follow custody pattern — and
does not monkeypatch the incumbent exact-case module's globals.

The proof binds, in one held descriptor set that is revalidated before and
after every phase:

- the ten frozen owner artifacts under `state/remote_sub/<RUN>.<suffix>`, each
  mode `0600`, one link, exact SHA-256, over a closed inventory that admits only
  this run's original files plus this checker's own optional receipt;
- the owner lane inventory, which admits only the retained refusal result;
- the semantic relationships between the records: request, launch, controller
  return, continuation request and continuation finish, the support manifest
  digest, the launch's controller/broker/quota source binding, the published
  support closure and the packet length and digest;
- the retained log, bound to this run id and host, with the ordered contract
  facts (`RUN_RESERVED`, `LEASE_WAIT`/`LEASE_OK`, packet/support SCP,
  `SUPPORT_VERSION_READY`, exactly one `LAUNCH_ATTEMPT attempt=1`, the first
  poll rc, `REMOTE_DONE rc=75`, the stdout collection, the missing usage
  receipt, the cleanup and the terminal `DONE rc=75 signal=admission
  reason=remote_admission_refused`), with markers for a later usage receipt, a
  provider outcome, an admission retry, an uncertainty state or a success
  refused outright;
- the thirteen controller commission receipts and the routing receipt, each
  complete, identity- and census-proven, capture-complete, with zero residual
  processes and no timeout, truncation or runtime failure, and with
  `commission-admission-read` returning 1 because its grep tests
  `active_lane_limit_reached` rather than the temperature refusal;
- the incumbent broker database, read once with `mode=ro` and `PRAGMA
  query_only=ON`, never constructed, snapshotted, garbage collected or
  released. The census also never creates the broker's own write-ahead
  sidecars: an empty or absent write-ahead log is read as an immutable
  complete database, and a populated log is read only while the broker's own
  shared-memory index is already present. A populated log without that index
  is refused rather than recovered;
- the incumbent ledger terminal identity through
  `pool_ledger.read_execution_identity(RUN, expected_rc=75,
  expected_signal="admission")`, which must be unique and verified for this root
  and parent. Acceptance is never read and never granted.

## What the checker explicitly does not claim

- It does not claim the historical selected generation. The proof records
  `original_selected_generation_recorded=false` and treats the frozen closure
  as a *compatible* immutable generation whose bytes are verified, not as the
  generation that was selected at launch time.
- It does not claim remote cryptographic attestation and does not claim the
  absence of all telemetry transport
  (`telemetry_transport_absence_claimed=false`). The evidence model is the
  incumbent same-OS-principal native owner model.
- It does not claim that the currently running checker is the bytes that ran.
  The frozen closure carries the pre-change incumbent `fabric_task.py` bytes;
  the reconciliation code is new source.

## The missing `LEASE_ID` and its honest reconstruction

The retained log records `LEASE_OK pool=minimax` without a lease identifier, so
the broker binding cannot be read from the log. The reconstruction is bounded
and must be able to fail:

- The bound `remote_sub.sh` contains exactly one broker `acquire` call site
  (the native and ordinary branches are mutually exclusive), and `LEASE_OK` is
  logged only after that call returns a lease identifier.
- The bound `lease_broker.py` inserts one fresh `uuid.uuid4().hex[:12]` lease
  row at the grant point; wait attempts (`cap_full`, `priority_wait`,
  `account_unavailable`) return before any insert, so a wait never grants and
  then retries.
- No statement deletes a row from the `leases` table; expiry and release are
  `UPDATE leases SET state=...`, so the identity columns are immutable and the
  historical row survives.

The census interval is bounded independently by two artifacts: the lower bound
is the launch artifact's `created_at` and the upper bound is the `commission-setup`
stage's `started_at` from the controller process receipts. That stage is the
incumbent `run()` wrapper around the controller's remote preparation, which
begins after the only broker acquisition call site, so the interval covers the
whole possible acquisition window. Both bounds are widened by one second so a
lost timestamp precision can never hide a second acquisition of the same root
and route. The census must return exactly one row for this root, pool, account,
task class and host, and that row must match the frozen values exactly: lease
`9e8400f4e4d6`, granted at `1793585266.9144828`, last heartbeat
`1793585270.660717`, ttl `7436`, renewable `1`, scope `minimax:default`, model
`MiniMax-M3`, host `ubuntu1`, pid `2806`, state `released` and no quota outcome
digest. Zero rows, several rows, a mutating database, an unreadable database
or an incomplete query are refusals.

The census also proves that the observed row set was stable: the database
file's own identity and the broker's write-ahead sidecars are compared before
and after the read, so a commit that lands during the census is a refusal
rather than a silently incomplete observation.

Two claims stay deliberately narrow. The pid is recorded as corroboration of
the frozen row only, because no run artifact binds the pid; the original
acquisition receipt is not claimed. The released state is an observation made
at check time; the receipt does not claim the lease was released before the
original controller return.

## Reconciler and status semantics

`candidate/native_thermal_refusal_reconcile.py` requires the expected proof
digest, re-derives the proof under the held read set, and publishes exactly one
canonical `0600` receipt with `O_EXCL`, `fsync` on the file and on the
directory, and a fresh same-carrier readback bound to the open writer. An
identical existing receipt is read back and reported as already recorded without
being reopened for writing. A partial or invalid receipt is preserved and never
repaired, deleted or overwritten in place. Any uncertainty after the exclusive
creation stays `EFFECT_UNKNOWN`; a failed response delivery reports the
unknown state rather than `NOT_APPLIED`.

The run status projection is read-only and fresh-revalidates the receipt before
projecting. It preserves the original terminal facts — rc 75, signal
`admission`, reason `remote_admission_refused`, the 241-byte retained result —
and adds only the reconciliation observation. `execution_absence_proven` is
true only for the qualified worker and provider scope of the original request.
Acceptance stays unverified, `same_run_replay_allowed` and `retry_allowed`
stay false, and `new_work_admission` stays `UNCHANGED`. No automatic launch is
added and continuation eligibility is not widened. When a receipt exists but
cannot be read, the projection stays fail-closed as
`STATUS_UNREADABLE` and still reports the retained terminal facts; only the
reconciliation observation is withheld.

The read-only check tolerates its own reconciliation receipt in the closed
owner inventory, so a repeated check after a reconciliation still qualifies.
The receipt's canonical bytes bind the reconstructed lease and the census
interval, so the record shows the bounds that make the reconstruction
meaningful.

## Source closure

`rollout/build_review_stage.py` gains the two new candidate files, so the
declared native closure moves from 102 to 104 files. The regenerated
`native-manifest.json` and `native-source-inventory.json` carry the two new
entries and the changed `fabric_task.py` digest. No obsolete 85-file release is
reconstructed and no other closure member changes.

Every pin that the incumbent design derives from the closure bytes follows the
closure: the successor installer's `SUCCESSOR_MANIFEST` and
`SUCCESSOR_MEMBER_COUNT`, the finite test pins on the manifest digest and
member count, and the current-members difference recorded in the historical
paired-upgrade fixture. The historical manifest, the historical per-file bytes
and the dated `research/H1_LINUX_CI_DEFAULT_ACL_FIX_20261025.md` record of the
102-member payload stay unchanged; that record remains historical evidence for
the bytes it names. No route, thermal limit, admission rule, continuation
eligibility rule or accounting policy changes with the closure.

The check requires the frozen relevant source bytes from the compatible
immutable generation `28faaf101463bcabef578ab1acabdcd270e301c7ed9cedf294e82fd459ccfcce`,
whose `RELEASE.json` has SHA-256
`0954bd8d5516b78b2a2c0a1354034c985e1637a89f2cdc6e448a391fc874c1f8` and whose
manifest carries 102 files. The twelve frozen source digests are verified both
against the manifest and against the bytes on disk. If that compatible closure
is absent on the host, the check refuses; it never substitutes a weaker
assertion.

## Verification boundary

`tests/test_native_thermal_refusal.py` builds a private fixture whose digests
replace the fixed historical allowlists only inside the test module. It
exercises forged and post-start records, changed source and artifact bytes,
root, packet and process mismatches, a broker census with zero, two, wrong,
unreleased and mutated rows, a lease outside the bounded interval, an
unverified ledger identity, symlinks, hard links, unsafe modes, changed paths
and cross-record replacement races, a partial receipt, an interrupted write, an
`fsync` failure, a failed response and a failed flush, exact idempotency, the
no-effect check and status paths, and the refusal to touch an unrelated run.
The fixture is not evidence about the original run; only the parent host holds
the original files for the installed read-only qualification.

## Gaps reserved for the parent

- Installation and live reconciliation are out of scope here. This change is
  source only; it performs no installation, no live-state mutation and no
  reconciliation of the retained run.
- The independent paid read-only proof audit remains separate. This change
  neither anticipates nor substitutes for it.
- If the release process retires the compatible 102-file generation, the
  installed check will refuse rather than weaken; the parent must either keep
  that closure addressable or explicitly re-base the frozen evidence.
- The broker database is opened read-only. If the host cannot read it — an
  unavailable database, a populated write-ahead log without the broker's own
  shared-memory index, or an unreadable or mutating database — the census
  refuses; it never falls back to a snapshot, a constructed broker, a garbage
  collection or a sidecar this checker would have to create.
- The proof and therefore the receipt depend on two live incumbent readings:
  the broker lease row and the ledger terminal identity. Neither is mutable
  today — the broker never deletes or rewrites a lease identity column and
  the ledger is append-only — but if either were replaced the receipt would
  stop being readable and the run would fall back to the fail-closed
  projection. The parent owns that acceptance decision.
- The thirteen controller commission labels are the retained stage set of this
  one artifact, not a general execution order; the checker requires exactly
  those thirteen and binds the whole receipt file by digest.
