# Same-schema acceptance superseding an unstarted selected release

This opt-in branch preserves a sealed, unstarted V2 maintenance descriptor while
qualifying one current schema-v5 release through the existing full acceptance
owner. It does not credit the selected release with PASS. The accepted ancestor
remains predecessor_sha; selected release and descriptor digest have independent
superseded_unstarted_sha / superseded_descriptor_sha256 bindings. V1 and V2
selectors retain their previous installed-predecessor requirement.

## Source and scope

Patch base: f381af6758533906865361373addbb0514f86d7d, maintenance Git blob
2de5f9344c2df0c85e783a8b6d5d89ec97646e61. This descriptor schema is
mastermind.executive_acceptance_maintenance/supersede_unstarted_v1 and is
separate from the V3 schema-migration contract. No database migration, acceptance
rebaseline, old recovery, provider retry, source registry or lifecycle is added.

## Preparation

The reviewed owner must be available through the existing release/install owners.
Use the normal stopped and disarmed preservation phase. Services, release
selection, readiness, Gate B and full acceptance prerequisites retain their
existing owners. Preparation checks installed control proof_base_sha equals the
selected release, validates the actual accepted ancestor through the existing
prior PASS chain and terminal_carry_fields, and compares the full live prestate,
artifact inventory and prior canary against the selected sealed baseline.

Run the reviewed preparation owner once with the actual protected successor SHA:

```sh
python3 /path/to/qualified-release/ops/executive_os/acceptance_maintenance.py \
  --predecessor-sha 7d82b9adb839d54e4ab25378ca333e498dd83fcc \
  --successor-sha CURRENT_PROTECTED_SCHEMA_V5_SHA \
  --root-job-id JOB-003 \
  --carry-terminal-dispatch \
  --supersede-unstarted-sha 326c8469a21d7f50fc9ecb1848196bf1c6e66685 \
  --superseded-descriptor-sha256 e45b5a3c49a96dbc811a639f129167401cce603b30aa5425064bd9b56f603991
```

Do not supply recovery selectors. The predecessor flag is the genuinely accepted
7d82 ancestor, not selected326c. The successor value must be a fully qualified
protected release containing this reviewed patch and supporting runtime schema5;
a proposal, checkout, historical source pin or schema6 release is not enough.
Retain the printed descriptor digest for that single successor operation.

The selected bundle is read only. The allowed original preparation entries are
descriptor.json, preparing.json, baseline.json, inventory.json,
prior-secret-canary.json and prestate.sqlite3, optionally accompanied only by the
legacy prestate.sqlite3-wal / prestate.sqlite3-shm pair. Each document remains sealed;
preparing.json must identify V2. Any other extra entry, run marker, carry/PASS receipt
or partial bundle is rejected. The selected acceptance output directory must be
absent beneath an existing canonical acceptance parent. An empty directory,
summary, partial receipt, dangling symlink or access error does not prove absence.
The legacy pair is admitted only when both files are canonical regular root:root
0400 single-link files without ACLs, WAL size is exactly zero and SHM size is
exactly 32768 bytes. Identity checks through no-follow FDs and before/after the
backup snapshot reject replacement or metadata drift. Sidecar contents are never
read, copied, deleted or altered. A lone file, nonempty WAL or unsafe metadata is
refused. Any other original layout requires evidence and owner review, not
deleting or moving old artifacts to satisfy the check.

Backup reads validate canonical root-owned single-link 0400 bytes and SQLite
snapshot using immutable read mode, so checking a WAL-mode sealed backup does
not create sidecars. Immutable mode ignores any admitted legacy pair only after
the owner proves the WAL is empty; SHM bytes are neither read nor trusted. The selected backup's exact digest and full snapshot must
match its descriptor and baseline. The new backup may have a different file
hash but must represent exactly the same complete prestate. Every selected V2
semantic carry field is equal to the new descriptor, including accepted
ancestor, root admission, terminal planner/attempt/marker, assignment seal,
prior PASS materials, frozen base, template proof and quota snapshot.

## Acceptance and future carry

Install the exact qualified successor using existing owners, then execute the
existing full acceptance owner once using its normal digest-bound maintenance
selector. Before writing the successor run-started marker it revalidates the
selected immutable descriptor, no-start/no-output state, sealed artifacts,
full baseline and the accepted ancestor's terminal carry evidence. Follow the
existing same-phase service-restoration obligations on success or refusal.

Only the successor's actual full PASS summary and carry-forward receipt qualify
it for future maintenance. Future V2 carry traverses its true accepted ancestry
and retains the selected unstarted binding. Selected326c remains NOT_STARTED and
its old descriptor/evidence remain untouched. Any failure or uncertain effect
stays on the existing operation; this branch grants no acceptance replay.

## Verification limits

The patch is verified with hermetic fixture tests. Filesystem root ownership and
service state are mocked at explicit test boundaries; real descriptor shapes,
sealed readers, backup checks, full snapshots, terminal-carry validation and
preserved-proof delta guards are exercised. These tests establish source
behavior, not live host eligibility, installation, readiness or acceptance.
