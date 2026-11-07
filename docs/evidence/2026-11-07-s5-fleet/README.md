# S5 Fleet source integration and observed capability coverage — 2026-11-07

Status: source integration and synthetic/read-only qualification. This is not installed-service acceptance.
Original carrier: [#1425](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1425), operation `fleet-health-os-20261013-sol-001`.
Original head: `aadb658f4dcd0b09b70db52c8673384dfb24a816`.
Protected integration and law pin: `5f8c13da926011fb5fdc8cea21287b532ac968db`, Skillpack 1.0.1/bootstrap major 1.
S5 root: `01a1b498-2e4c-746b-bdea-77b474c900c4`.

## What changed

The original branch is composed with the pinned current master, retaining the current Resources & systems, Capacity, attended Fabric, project navigation and authenticated Workspace owners. Ten integration conflicts were resolved additively. The fixed Fleet route, four-window enum, authorization before read and revocation after await remain. Hardware data is removed when authentication is revoked.

The installed observer's missing Linux disk and lane values were traced to a projection parser, not a host outage. Existing Capacity emits details such as `4<12 (lane_ceiling=32, max_active=12)` and `51.2>=75 (base=60,stage=15)`. The former parser tried to convert the entire annotated right operand with Number(), producing unknown. It also coerced a blank operand to measured zero.

The source observer now accepts only the known annotated formats and finite decimal operands. Lane counts are safe integers and the displayed laneCeiling is the existing owner's effective launch threshold. Unknown, held and malformed values remain null; failed disk gates retain their measured free space. Eligibility and placement authority are unchanged. A stale online record is still stale and excluded, not usable capacity.

An initial failed Fleet read now says no observation is available. It does not claim to be showing a last observation when none exists.

## Existing sensor inventory, then one forward adapter addition

The retained incumbent host snapshots already contain Linux procfs CPU activity, available RAM, swap and filesystem space, plus hwmon CPU/NVMe temperatures. Ubuntu1 also supplies a CPU fan reading. Mac snapshots contain load, logical CPU count, disk and free/inactive memory estimate; precise CPU busy, total RAM and thermal readings are missing there.

Linux `granular.mem_total_bytes` was absent. The existing candidate probe now emits measured `/proc/meminfo` MemTotal and the existing candidate adapter maps it into the already-understood Fleet field. Absent, malformed, boolean, non-string, negative and zero total RAM remain unknown. Available RAM is never promoted to total RAM.

Only `candidate/host_pull_probe.template` and `candidate/host_pull_backend.py` change. The `source/` files and `rollout/native-preimages.json` are byte-identical to the protected pin: they record installation preimages, not forward source. The incumbent review-stage builder regenerated the manifest and inventory. Exactly two staged entries changed: `ext/host_pull_backend.py` and `ext/host_pull_probe.template`. No CURRENT selection, native release, collector installation or activation occurred.

Review-stage manifest SHA256: `d0eeeb81106bf27e67a63bdde971636944dea749d53f427ea9a51ed624394314`.
Source-inventory SHA256: `38f7bd528306c2a5a8ae5291967543040dff3f2328cda031432e77920726420e`.

## Live read-only evidence and its limits

- [Installed observer at entry](installed-observer-entry.json): 13 registered hosts, seven fresh and six stale; all eight public accounts ready while overall state is DEGRADED. The tool did not return an overall capture timestamp, so none is invented.
- Installed observer module SHA256 observed before edits: `b1ca93566b50246a271dc1720b9e0328d9887d4c3b32b50a7b9ed7107a1fae5a`, matching the protected source preimage.
- Configured placement launcher SHA256 verified before its permitted read: `bc0b3559392a07f3d4f7109455765c14dbc4dc946f6cb5a788e547ae179dbf0f`.
- [Corrected source observer](source-observer.json), 2026-11-07T06:23:57.643Z: same-user source canary through the existing configured read launcher. This is not an installed update or cross-UID proof.
- [Retained sensor coverage](retained-sensor-coverage.json): selected fields from already-pulled snapshots. Its generation identifies the retained source path; it does not independently attest current generation selection or service installation.

At the source canary timestamp:

| Host | Fresh | Free GiB | Active lanes / effective limit | Qualification retained |
| --- | --- | ---: | --- | --- |
| m1 | yes | 136.9 | 0 / 1 | seat/candidate exclusions preserved |
| m2 | yes | 231.7 | unknown / unknown | occupancy remains unknown |
| ubuntu0 | yes | 135.3 | 2 / 12 | current owner did not admit go-codex in this sample |
| ubuntu1 | yes | 48.0 | 0 / 18 | disk below the 75 GiB reserve; excluded |
| ubuntu2 | yes | 138.7 | 2 / 12 | owner qualified go-codex in this sample only |
| ubuntu3 | yes | 139.5 | unknown / unknown | occupancy reconciliation hold |
| ubuntu4 | yes | 864.0 | 0 / 2 | automatic qualification and candidate exclusions remain |
| mb, mini1–4, pc | no | retained/unknown | retained/unknown | all excluded; no usable capacity inferred |

These are observations at their recorded times, not lasting reservations. Later free-space changes in the retained snapshots are unattributed. This session applied no cleanup and reclaimed **0 attributable bytes**. Account readiness, maintenance readiness, provider entitlement and physical admission remain separate.

## Executed qualification

| Surface | Observed result |
| --- | --- |
| Fleet producer, history/downsampling/window budgets, Workspace Fleet route and read app | 146 tests passed |
| Executive Workspace mount suite | 77 tests passed |
| Studio observer integration | Original 28 passed plus three new failures reproduced; repaired suite 31 passed |
| Original Fleet decoder/native host adapter/browser auth suites | 14 + 3 + 200 passed; original Fleet component seven passed |
| Current App integration under sequential execution | App.test.tsx 105 passed; a broader daily-route run retained one pre-existing 10-second timing failure |
| Final affected Fleet component and actual navigation/sign-out selection | nine passed, three unrelated daily-route tests deliberately not selected |
| TypeScript | `npx tsc --noEmit` passed |
| MemTotal fake procfs + actual adapter mapping | original candidate measured-total case failed; candidate repair three tests passed; five existing disk telemetry tests passed |
| Existing native review-stage build | passed; exactly two manifest entries changed; original preimages unchanged |
| Compiled Chromium synthetic browser | passed at 1440×1100 and 390×844; no page errors; no horizontal page overflow; sign-out removes the hardware region |
| Native Rust Fleet selection | 2 passed on committed source `fde4c5108527a3ce3706dfcb7f53abdc404adb9a`, with explicit `MM_SOURCE_REVISION` and nonproduction build identity; the earlier invocation lacked those required inputs |

[Browser receipt](browser-receipt.json), [reproducer](prove_browser.py), [desktop fixture](fleet-desktop-synthetic.png), [mobile fixture](fleet-mobile-synthetic.png).
The separate fixture entry never enters the default production entry. No real authentication, installed host, cleanup or restart is represented by the screenshots.

Author self-check is SELF_REVIEWED. No separate formal GitHub approval is claimed. Required hosted CI, protected merge and installed acceptance remain distinct.

## Preserved holds and original carriers

The denied `_workspace_fleet_reader_from_config` handoff-binding edit remains untouched, byte-identical to the original #1425 function (SHA256 `9cfcbdc49761ea86e916c9b495cf02472563884c14300c6ada734b139d9b324e`). It still uses the original reader. No private observer root was bound into the cross-UID Executive service, no ACL/TCC/security change was made, and #1363 collector activation was not retried. The previously refused handoff-test command was not replayed.

Storage remains under [#1632](https://github.com/mastermindx-market-intelligence/Mastermind/issues/1632), the original [#1877](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1877) → [#1900](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1900) stack and merged #1951 guards. #1877's prior source-write refusal is preserved. Merged [#2156](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2156) is the accepted preview/toolkit source; #2154 is not re-admitted. No live worktree, active lease, user data, credential or retained result was deleted.

Recovery stays on [#1887](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1887): first-party heartbeat and existing ledger only. The specific pathname-spawn HOLD_SECURITY, historical native-generation mismatch and host-route refusal remain. No Studio Direct remote carrier or original service was restarted.

[#2007](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2007) retains its historical Ubuntu receipts and source publication/projection constraints; [#2008](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2008) is already merged and is not redone. Historical provider/account denials, runner floors and Ubuntu2 uncertain original work are unchanged.

## Bounded paid contributions

- `s5-observer-parser-fixtures-20261107-c2-01`: response digest `4e03f1ed12c2ea71fae8334ac6a4e8f882482c0be8d71beeda8003c4cee9de81`; consumed and accepted after parent regression proof.
- `s5-linux-memtotal-fixture-20261107-c2-01`: response digest `a8762876e1d3a24c48ddf3abb7937b36a1df6ffb026653335a01f2c5b1162acd`; consumed in full and accepted after candidate-only parent qualification. The parent retained source preimages and tightened zero-total handling.
- The first recovery-ledger and storage-inventory proposals returned but are not accepted for integration. Parent adjudication identified effect-uncertainty, first-party health, concurrency and durability gaps. Refined bounded proposals use `s5-recovery-serialized-effects-20261107-c2-01` and `s5-storage-pre-effect-holds-20261107-c2-01`; their original results remain preserved. Delivery is not installed acceptance.

S3 alone consumes qualified placement facts. S0/S6 retain the app integration owners. No second collector, registry, scheduler, watchdog, lease ledger or publication controller was introduced.


## Current Ubuntu owner observations and elapsed timer evidence

[ubuntu-readonly-observations.json](ubuntu-readonly-observations.json) records two
read-only observations of the original #2007/#2008/#1632 maintenance surfaces.
The same-UID existing bus, installed file owner/mode/inode/digests, effective unit
paths and empty drop-in lists were observed. No service was manually started,
no maintenance executable was invoked, and no raw maintenance log was read.
[observe_ubuntu_units.py](observe_ubuntu_units.py) is the bounded observation code;
it is evidence of this read, not another installed collector or controller.

| Host | Latest observation UTC, 2026-11-07 | Available GiB | Existing floor GiB | Timer | Latest oneshot exit |
| --- | --- | ---: | ---: | --- | ---: |
| Ubuntu1 | 07:05:34 | 63.051 | 75 | enabled / active / waiting | 0 |
| Ubuntu2 | 07:05:29 | 137.979 | 75 | enabled / active / waiting | 0 |
| Ubuntu3 | 07:05:30 | 139.591 | 75 | enabled / active / waiting | 1 |
| Ubuntu4 | 07:05:32 | 864.053 | 75 | enabled / active / waiting | 0 |
| Ubuntu0 | no current observation returned | unverified | historical 75 | current state unverified | unverified |

All four observed installed scripts still have SHA256
`3f676c0075478029e5857f0a95cd4ba9ae0dba9221eab312b034f88bca2502e3`.
The observed service and timer hashes match the original November 3 receipts.
Each timer's trigger advanced during 252.587–264.679 seconds of actual elapsed
observation. Those are naturally scheduled executions, not a manually induced
cleanup or death/recovery exercise. Exit 0 does not establish pressure recovery:
Ubuntu1 remains below its configured reserve. No byte change is attributed to
this session; measured reclaimed bytes are zero.

Ubuntu0's two metadata-read processes completed with rc0 but no returned stdout.
The second used unbuffered output as the one bounded diagnostic. This is an
observation gap with unproven cause, not evidence of a general host outage or a
permission denial. No further unchanged probe was repeated. Its prior installed
receipt remains historical evidence only.

The original #2007 branch still resolves to
`e339c3b7da77c0fb1087656fc89150f955db9613`, while its PR projection reports
`0e20d9b2eaba16219495e4a9489d4e2ae88900fc`. That publication mismatch remains held.
These new read-only observations do not retry, rehome or clear the original
publication effect, provider/account denials, Ubuntu2 unknown-work holds or
Ubuntu4 qualification-only restrictions.

The local Fleet source merge is `fde4c5108527a3ce3706dfcb7f53abdc404adb9a`, with
parents `aadb658f4dcd0b09b70db52c8673384dfb24a816` and
`5f8c13da926011fb5fdc8cea21287b532ac968db`. The scoped diff check is clean. An
initial whole-merge whitespace check stopped before committing on existing
upstream whitespace; it was replaced by the correct comparison to the merged
upstream base. The successful commit separately reported Git's existing
automatic-repack permission failure at another worktree index. That auxiliary
operation was not repaired or replayed and no other writer's files were touched.
