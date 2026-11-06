# Retain and close a set of Capacity/Wake observations

R2 Stage4 requires a genuine seven-day installed campaign, with ordinary and busy
demand, Secretary occupancy/consumption, review backlog and total cost per
accepted outcome. `executive_wake_reconcile.py --observe-only` already provides
read-only point observations from the existing Runtime, Wake and Agent OS owners.
The optional receipt and offline report close the evidence-retention gap. They do
not qualify that campaign, start a service, schedule a sample or admit a worker.

## Start and observe through the existing operational owner

After the qualified source is installed, the existing authorized operational
owner supplies the real Runtime root and a private evidence directory it owns.
The directory must already exist, be direct (no symlink ancestors), owned by the
invoking UID, mode0700 and without a macOS ACL. Choose a new explicit receipt
filename for each real observation:

```sh
python scripts/executive_wake_reconcile.py \
  --root "$observed_runtime_root" --observe-only \
  --observation-receipt "$observation_directory/point-001.json"
```

The first actual invocation starts the retained collection. Later invocations
collect additional real points through the same owner. Scheduling and custody
stay with the existing operational owner; this command creates no timer, daemon,
campaign registry, Runtime event, provider job or transport invocation. The
default mutating Wake reconciliation path cannot be combined with the receipt
flag. No source code here starts an installed campaign automatically.

Each receipt reserves its path exclusively before the read, records fresh host
UTC acquisition start/end and monotonic acquisition duration, and retains exact
observer stdout, stderr, return code and their digests. Source-file digests are
observations of bytes; they do not attest the executing installed release or the
Runtime's production identity. Local fixtures receive the same explicit
`UNATTESTED_SOURCE_OBSERVATION` classification. There is no CLI input for a
timestamp, installed status, campaign qualification or synthetic elapsed time.

The original observation's return code and streams are preserved. A missing
Runtime or degraded/contradictory point remains failed or partial in its receipt.
The only intended write is the evidence file. The read-only Runtime retains its
existing SQLite sidecar/shared-memory bookkeeping caveat; no authoritative row,
schema or WAL mutation is added.

A complete receipt is a direct single-link file owned by the invoking UID,
mode0400 and without a macOS ACL. An interrupted capture may leave its original
incomplete reservation. Preserve and reconcile that file; another invocation
never overwrites it or silently reuses its name. Reports reject changed custody,
aliases, same-byte inode replacement during acquisition, malformed JSON/digests,
source drift during capture and invalid or regressing timestamps.

## Close/report the explicit retained input set

Use the exact filenames expected by the operational record, including any
missing observation filenames. Avoid a shell glob that silently omits a missing
point:

```sh
python scripts/executive_wake_reconcile.py --summarize-observations \
  "$observation_directory/point-001.json" \
  "$observation_directory/point-002.json" \
  "$observation_directory/point-003.json" --json
```

This is an offline deterministic report over the supplied bytes. It opens no
Runtime, reads no current clock and mutates no receipt or campaign state. The
same input set in a different argument order produces the same report. It lists
raw receipt hashes, individual outcomes, recorded wall-clock span and gaps,
missing/invalid/duplicate inputs and mixed Runtime/source/boot-packet origins.
Per-point conditional interval summaries are retained; repeating snapshots are
not pooled into misleading campaign percentiles or a demand census. Bounds are
512 inputs,16MiB per receipt and128MiB per supplied set. Inputs left unread by a
bound are reported explicitly.

`rc0` means the supplied set was read and reported without input/observer failure.
It does not mean campaign acceptance. Failed/missing input or observer failure
returns2; the exact original observer result remains in each retained record.
Closing the supplied set does not seal an operational campaign or prevent later
observations from its existing owner.

## What still needs real proof

`campaign_qualified` and `installed_coverage_claimed` remain false. Two timestamps
a week apart establish neither seven days of observation nor continuous service.
UTC labels are not attested physical elapsed time; sample gaps and omitted inputs
must be evaluated against the accepted operational campaign.

Qualification still needs the installed source/Runtime identity and genuine
elapsed/cadence evidence, ordinary/busy demand coverage, actual reasoning and
desktop-occupancy measurements, queue delay, complete review backlog, Secretary
and original-parent consumption, actual total cost per accepted outcome, and the
required stale/relieved-principal rejection proof. Those facts must join their
existing canonical producers. Missing measurements remain `UNAVAILABLE` with
null values, never zero. This source addition supplies no invented producer or
independent account/quota inference.

Source basis: the unchanged R2 contract
`docs/superpowers/specs/2026-10-12-meta-ceo-office-r2-implementation.md` sections
"Capacity and scheduling" and "Stage4"; existing point owner
`control_plane/capacity_campaign_observation.py`; existing CLI
`scripts/executive_wake_reconcile.py`. Initial implementation base:
`2707ce750b4cfda7420b63ded94c5d35dba6a53c`. Local tests use real temporary Runtime
and evidence files with explicit synthetic clock/source ports; they claim no
host installation or elapsed campaign coverage.
