# Executive Capacity CF2-H0 Source-Closure Repair Design

**Status:** Architecture frozen by the controller ruling on 2026-08-27

**Protected Mastermind, Skillpack, and implementation base:**
`be68ec881460aa60d7d77cdb69f7c1cae81f6310`

**Protected Skillpack compatibility:** `mastermind.sol_skillpack.v1`, version `1.0.0`,
`minimum_bootstrap_major = 1`

**Downstream immutable implementation evidence:** CF2-P0 Task 3 head
`e315ba003511dd1b52ef7a41da2a7d6bb187621b`

**Selected repair:** alternative B, one fresh side-by-side non-promisor rematerialization followed
by an archive-only source/generation transition and a new truthfully receipted H0 generation

## 1. Outcome and stop state

The repair restores the promise H0 was meant to make: the fixed installed Macro source at commit
`dcdd939c45b23abce5ba04f95e330ac914a3904b` is an ordinary, complete, direct Git repository whose
accepted commit graph is fully present offline, whose only material worktree files are the frozen
eleven CF1 paths, and whose metadata cannot trigger or conceal lazy acquisition.

The new H0 generation truthfully identifies the exact merged repair/preparer commit as current. It
retains `e4e44867ace335ac9208a3990a10c163e199492d` only as superseded provenance. Success is still
not CF2-P0 acceptance. The repair's terminal capability is:

```text
H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED
```

followed by two independent zero-mutation verify-only passes, each returning:

```text
H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED
```

The carrier stops there and hands the new H0 identities to a separate CF2-P0 re-pin carrier. It
does not run P0, modify the P0 proof runner, authenticate a provider, read a credential or provider
home, perform OAuth, call a provider, start or change a service, create or connect to a socket,
execute a worker, route work, implement CF2-I, or release any later gate.

## 2. Reconciled current state

The protected H0 materializer is not a complete ordinary Git materializer. It builds its object
list using `rev-list --filter=blob:none`, adds only the eleven material blobs, writes a `.promisor`
sidecar, and configures `extensions.partialClone`. Its source contract then calls that state
`promisor_state=offline_no_remote`. Remote absence prevents a successful fetch but does not prove
that every object reachable from the accepted commit exists.

Immutable P0 Task 3 correctly demands a non-promisor source in its architecture, but its current
source observation assigns `lazy_fetch_impossible=True` without inspecting the installed source's
alternates, shallow state, promisor sidecars/configuration, partial-clone filters, or complete
reachable-object closure. H0 must repair its own source and evidence. Moving or weakening that law
inside P0 would turn a false prerequisite into an acceptance shortcut.

The installed `.git` directory was not readable to the unprivileged discovery. The following
sanitized identities are therefore old-state match gates for the root ceremony, not proof of the
installed Git object's current promisor or closure state:

| Old installed artifact | Required SHA-256 / identity match |
|---|---|
| Generation basename and `source-config.json` digest | `2b05a61f54c876f00c3f03d51bd9df72de4a73e76bc06b2e7bc13a11ee203d60` |
| `components.json` | `02886a6c79f22534ac24234d8adb3224329976342393988541c2a50d7e297f29` |
| `host-preparation-receipt.json` | `51c58d18869663d90c593e416c7fc7833b3725378870f576abd3647f62f40830` |
| `broker-topology.json` | `981e880ba7d21a0003fe2dd8322c5793f2643b815d094374dd6fad3fed31e453` |
| `rollback-contract.json` | `18d83b0e164ac2e917d84c01fe1d53fc5c1ce0c33ac9580f11d684e16e495093` |
| `rollback-drill-receipt.json` | `7efba70495cbbf8bcad0c4e47e894a23f4b1618756d8c3e23cae85ad6b7250ba` |
| Receipt outcome | `H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED` |
| Prior preparer | `e4e44867ace335ac9208a3990a10c163e199492d` |
| Macro commit | `dcdd939c45b23abce5ba04f95e330ac914a3904b` |
| Material digest | `35931b4ef965c5d67a7e01444dd483804e48671784716ea8196c94e925466650` |

If any old-state gate differs under root, the carrier refuses before installed mutation. It does
not rewrite the intent around a newly discovered state.

## 3. Capability ledger

| Capability | State before repair | State after this carrier's proof |
|---|---|---|
| H0 ordinary complete Git object closure | `BROKEN` | `BUILT_NOT_PROVEN` after merge; `PROVEN_LIVE` only after native repair plus two verify-only passes |
| H0 runtime, telemetry boundary, inert topology, rollback drill | `PARTIAL` as old receipted prerequisites | Preserved and reverified; not rebuilt |
| Truthful H0 current preparer/source identity | `BROKEN` | New repair merge is current; `e4e44867...` is superseded provenance only |
| CF2-P0 Task 1-3 implementation | `BUILT_NOT_PROVEN` at immutable head `e315ba0...` | Unchanged and still blocked on a separate re-pin/review carrier |
| CF2-P0 production acceptance | `NOT_BUILT` / no accepted current result | Unchanged |
| OAuth, provider execution, services, routing, workers, CF2-I | `REJECTED_BY_DESIGN` in H0 | Unchanged |

## 4. Alternatives and ruling

### Alternative B — selected: side-by-side complete rematerialization

Build a complete offline transport as the authenticated operator. Under the existing H0 host lock,
root materializes it into a fresh sibling candidate, fully verifies the candidate before touching
the installed source, publishes one durable repair intent, archives the old source and old
generation without deletion, installs the candidate, and publishes a verified new six-file H0
generation last.

### Alternative A — rejected: strip markers in place

Deleting `.promisor`, `extensions.partialClone`, or filter configuration cannot materialize missing
objects. Even if every object happened to be present, in-place changes would erase evidence of how
the repository was built, leave the old generation falsely current, and create a broad crash window.

### Alternative C — rejected: weaken P0

Accepting `offline_no_remote`, trusting `git fsck` under promisor semantics, or continuing to set a
constant `lazy_fetch_impossible=True` would convert remote absence into a false closure claim. P0
must remain strict and independent.

## 5. Canonical boundaries and no-rebuild law

The repair extends the existing owners:

- `capacity_source_contract.py` owns source/component/host-receipt semantics;
- `capacity_host_artifacts.py` owns data-only transport, materialization, metadata digests, closure
  verification, and resumable intent/receipt publication;
- the new `repair-capacity-source-closure.sh` owns the one privileged archive/install transition;
- `prepare-capacity-host.sh` adopts the complete v2 transport and receipt law for future clean H0
  installations; and
- `HOST_PREREQUISITES.md` owns the native operator ceremony.

The fixed installed source path, Macro commit, eleven material paths, H0 lock, staging/archive/
generation roots, runtime, PyYAML, telemetry boundary, three realm identities, topology, rollback
contract, rollback-drill archive, legacy services, and socket absence remain canonical. The repair
does not introduce another source root, lifecycle store, queue, retry plane, receipt authority,
service family, provider normalizer, or P0 gate.

The successful end state has one visible installed source at the existing path and one visible
current generation. Superseded source/generation trees exist only as immutable children of the
single repair archive. Nothing is deleted.

## 6. Complete offline transport v2

The authenticated operator builds `mastermind.capacity_source_transport/v2` from a local Macro
repository that already contains the exact commit. Network access is outside the root ceremony.
The builder does not accept a branch, remote, ref wildcard, or caller-defined material inventory.

The ZIP contains exactly `manifest.json` then `payload.pack`. Both are stored, not compressed or
encrypted. Their timestamp is `1980-01-01T00:00:00`, Unix regular-file mode is `0400`, member names
are exact ASCII, and there are no comments, extra/duplicate members, prefixes, suffixes, or trailing
archive bytes. `manifest.json` is sorted compact canonical UTF-8 JSON with no final LF.

The manifest has exactly:

```text
schema_version repository commit object_format closure_kind payload_sha256
object_count object_inventory_sha256 material
```

Fixed values are:

```text
schema_version = mastermind.capacity_source_transport/v2
repository = mastermindx-market-intelligence/macro
commit = dcdd939c45b23abce5ba04f95e330ac914a3904b
object_format = sha1
closure_kind = complete_reachable_commit_graph
```

The builder enumerates every object reachable from the commit with replacements, alternates,
promisor fetching, system/global config, hooks, fsmonitor, text conversion, optional locks, and
network prompts disabled. Any missing object refuses. One object-inventory row is exact ASCII:

```text
<40-lower-hex-oid> <commit|tree|blob|tag> <decimal-uncompressed-size>\n
```

Rows are unique and sorted bytewise by OID. `object_count` is the row count and
`object_inventory_sha256` hashes their concatenation. `payload_sha256` hashes raw pack bytes.
`material` remains the exact ordered eleven-row v1 structure: `path`, `mode`, `git_blob`, `sha256`,
`size`. Pack/ZIP hashes bind the delivered carrier; object-inventory and material hashes bind its
semantic closure even if a later equivalent pack encoding differs.

## 7. Ordinary complete installed repository

Materialization creates a new direct repository from the v2 pack and never clones/copies the
operator repository. Before installed mutation it must prove:

- exact detached `HEAD` at the Macro commit and a clean worktree;
- every reachable object is locally readable with the manifest type/size and strict ordinary
  `git fsck --full --strict` succeeds;
- exactly one ordinary `.pack`/`.idx` pair exists;
- no `.promisor`, replacement ref, graft, alternate, shallow file, remote, promisor config,
  partial-clone extension/filter, `filter.*` config, URL rewrite, include, or credential helper;
- sparse checkout projects only the eleven worktree files but does not filter the complete object
  store; and
- every material file matches its fixed blob, SHA-256, size, and Git mode.

The stale identity `promisor_state=offline_no_remote` is removed. The new
`mastermind.executive_capacity_working_directory_identity/v2` object has exactly:

```text
schema_version repository commit working_directory git_directory_kind checkout_scope
object_format object_closure object_count object_inventory_sha256 head_detached
worktree_clean worktree_file_count remote_count alternates_present shallow_present
promisor_present partial_clone_filter_present sparse_checkout lazy_fetch_state
```

Fixed semantics include `git_directory_kind=direct`,
`checkout_scope=accepted_cf1_material_only_complete_object_store`,
`object_closure=complete_reachable_commit_graph`, `worktree_file_count=11`, every forbidden-state
boolean false, `sparse_checkout=true`, and
`lazy_fetch_state=impossible_complete_offline_object_store`. Object count and inventory digest are
observed from the verified v2 manifest, never accepted as caller assertions.

## 8. Filesystem and digest law

Every security-relevant path is opened without following links and rebound by descriptor. Regular
files have link count one. Symlinks, sockets, devices, FIFOs, hard links, ACLs, non-root/non-wheel
ownership, and group/other-writable objects refuse. Only system-maintained
`com.apple.provenance` may exist; every other xattr refuses, and provenance bytes are excluded from
content identity.

Installed source directories are `root:wheel 0555`; ordinary files are `0444`; material paths
whose Git mode is `100755` are `0555`. Git config/index/pack/idx/object/info/manifest files are
single-link `root:wheel 0444`. Staging and repair archive directories are `0700`; durable intent/
receipt files are `0400`; the new generation directory is `0555` and its six files are `0444`.

The closed tree digest is SHA-256 over canonical compact JSON for rows sorted by UTF-8 POSIX
relative path. Every row has `path,type,uid,gid,mode,nlink`; file rows also have `size,sha256`.
The root row path is `.`, modes are four-digit octal, and ACL/unapproved-xattr state prevents digest
construction.

Digest framing is exact: source-config/component digests hash compact canonical JSON without LF;
transport hashes stored bytes; repair intent/receipt hash compact canonical JSON plus one LF;
`components.json`, `source-config.json`, and `host-preparation-receipt.json` have no LF;
topology/rollback retain validated renderer bytes; rollback-drill receipt retains exactly one LF.

## 9. Source and H0 evidence schemas

The source config advances to `mastermind.executive_capacity_source_config/v2` because its
working-directory identity changes semantically. Executable, entrypoint, inventory, telemetry,
runtime, topology, and rollback component schemas remain unchanged. The generation still contains
exactly the same six filenames.

The host receipt advances to `mastermind.executive_capacity_host_preparation/v2` and has exactly:

```text
schema_version outcome preparer_source_commit repair_source_commit source_release_commit
producer_material_source_digest source_config_digest component_manifest_digest
source_closure_state source_repair_receipt_digest prior_provenance broker_count
broker_topology_digest rollback_contract_digest rollback_drill_receipt_digest
service_state socket_state control_state credential_state worker_execution_state cf2_i_state
```

`preparer_source_commit` and `repair_source_commit` both equal the exact merged repair commit.
`source_closure_state=complete_non_promisor_offline_no_lazy_fetch`. `prior_provenance` has exactly:

```text
status = superseded_archived_not_current
preparer_source_commit = e4e44867ace335ac9208a3990a10c163e199492d
generation_digest = 2b05a61f54c876f00c3f03d51bd9df72de4a73e76bc06b2e7bc13a11ee203d60
generation_artifact_sha256 = {
  "broker-topology.json": "981e880ba7d21a0003fe2dd8322c5793f2643b815d094374dd6fad3fed31e453",
  "components.json": "02886a6c79f22534ac24234d8adb3224329976342393988541c2a50d7e297f29",
  "host-preparation-receipt.json": "51c58d18869663d90c593e416c7fc7833b3725378870f576abd3647f62f40830",
  "rollback-contract.json": "18d83b0e164ac2e917d84c01fe1d53fc5c1ce0c33ac9580f11d684e16e495093",
  "rollback-drill-receipt.json": "7efba70495cbbf8bcad0c4e47e894a23f4b1618756d8c3e23cae85ad6b7250ba",
  "source-config.json": "2b05a61f54c876f00c3f03d51bd9df72de4a73e76bc06b2e7bc13a11ee203d60"
}
```

The new generation basename is its new canonical source-config digest. The old basename may not
remain a visible current generation after commit.

## 10. One durable repair intent and receipt

The carrier uses the existing lock at
`/Library/Application Support/MastermindExecutive/locks/cf2-h0.lock`. After the candidate and all
old-state gates verify, but before installed mutation, it publishes one
`mastermind.executive_capacity_h0_source_repair_intent/v1` object with exactly:

```text
schema_version intent_id operation repair_source_commit macro_release_commit
producer_material_source_digest old_generation observed_old_source_tree_sha256
candidate_transport_sha256 candidate_transport_manifest_sha256 candidate_object_count
candidate_object_inventory_sha256 candidate_source_tree_sha256 service_state socket_state
credential_state worker_execution_state cf2_i_state
```

`operation=side_by_side_non_promisor_rematerialization`. `old_generation` contains the exact
basename, prior preparer, outcome, and six artifact hashes from section 2. `intent_id` is SHA-256
over canonical compact JSON of every other field. The archive is derived as
`capacity-archive/source-closure-repair-<intent_id>` and is not caller-selected.

After installed verification, the same archive receives one
`mastermind.executive_capacity_h0_source_repair/v1` receipt with exactly:

```text
schema_version outcome intent_id repair_source_commit source_release_commit
producer_material_source_digest prior_preparer_source_commit prior_generation_digest
archived_source_tree_sha256 archived_generation_tree_sha256 installed_source_tree_sha256
installed_object_count installed_object_inventory_sha256 new_source_config_digest
new_component_manifest_digest service_state socket_state
credential_state worker_execution_state cf2_i_state
```

Its outcome is `H0_SOURCE_CLOSURE_REPAIRED_NOT_P0_ACCEPTED`. The v2 host receipt binds the stored
repair-receipt digest. The repair receipt deliberately does not bind the new host-receipt digest,
which would create a circular identity; the host-receipt hash is external governed proof. This
receipt is not a seventh generation file.

## 11. Ordered transition and commit point

The root carrier performs this exact sequence under the H0 lock:

1. Verify the sealed Mastermind checkout at the exact merged repair commit.
2. Verify preserved H0 runtime/topology/telemetry/principal/legacy/service/socket invariants.
3. Match the old generation and its six old artifact hashes.
4. Copy the operator-owned v2 transport by no-follow descriptor and bind its independent SHA-256.
5. Materialize and completely verify the side-by-side source candidate.
6. Publish and fsync the one durable repair intent.
7. Move the old source into the intent archive atomically and fsync both parents.
8. Install the candidate at the fixed source path atomically and fsync both parents.
9. Move the old generation into the same archive atomically and fsync both parents.
10. Reverify source closure and every preserved invariant.
11. Publish/fsync the repair receipt, build the new hidden six-file generation candidate, and
    verify all internal/external digest links.
12. Reverify source, repair archive/receipt, generation candidate, runtime, topology, rollback,
    telemetry, services, sockets, legacy files, and principals.
13. Rename the hidden generation to its digest basename as the last semantic filesystem mutation
    and sole commit point.

No correction or verification occurs after the final rename. The script writes only the fixed
success sentinel and exits. The retained lock file is an exclusion artifact, not a state record.

## 12. Crash reconciliation, failure, and rollback

The intent is the only recovery authority. Exact path positions and closed tree digests define
state; timestamps and shell variables do not. A fresh invocation with the same exact merge and
transport reconciles that intent before creating anything. A different intent, multiple candidates,
or multiple archive positions refuses for Sol adjudication.

Before the generation commit point, a definite failure restores the exact prior visible source and
generation by atomic rename when their digests prove they are the intent-bound archives. Failed
candidate/current trees are archived under the same repair archive; nothing is deleted. After a
crash, the same carrier may resume forward from a uniquely valid next position or restore the
uniquely valid prior position. It never guesses, overwrites, changes an intent, or auto-fails over.

After the new visible generation verifies against the intent and repair receipt, the repair is
committed. The carrier never restores the superseded promisor source automatically. Later drift is
a verify-only refusal and requires a new Sol ruling.

Fixed exits/stdout are:

```text
0  H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED\n  (repair)
0  H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED\n       (verify-only)
64 INVALID_INVOCATION\n
65 H0_SOURCE_CLOSURE_REPAIR_REFUSED\n
70 H0_SOURCE_CLOSURE_REPAIR_INCOMPLETE_RECONCILE_SAME_CARRIER\n
75 H0_LOCK_HELD\n
77 ROOT_REQUIRED\n
```

Stderr is empty. Exit 70 is not a completed outcome; the same carrier must reconcile before any
new attempt. No output contains a path, Git output, principal, account, credential, or exception.

## 13. Native administrator ceremony and proof

Review, CI, Macro acquisition, v2 transport construction/hash, and the exact merged Mastermind
checkout occur before privilege. Root receives only the single-link operator transport plus its
recorded digest. During the root ceremony there is no network, credential/provider-home access,
service mutation, socket creation/connection, provider call, routing, or worker execution.

One native administrator dialog executes the repair once from the sealed merged checkout. That
checkout then runs verify-only twice. Each pass independently reopens and verifies complete object
closure, the six-file generation, repair archive/receipt, runtime, topology, rollback evidence,
telemetry boundary, fixed principal-directory metadata, disabled/unloaded labels, absent sockets,
and legacy state. Verify-only does not write the lock, create an intent, or mutate any path.

The governed packet records sanitized facts only: repair merge, v2 transport/manifest hashes,
object count/inventory digest, new generation basename and six hashes, repair receipt hash,
archived old identities, the repair sentinel, two verify sentinels, and zero scoped mutation for
each verify pass.

## 14. Testing and exact stop condition

Tests must prove refusal for marker deletion without complete objects, promisor-enabled `fsck`, a
fabricated `lazy_fetch_impossible`, v1/stale receipts, missing/extra objects, alternates, shallow
state, filters, remotes, attached/dirty worktrees, extra worktree files, unsafe Git metadata,
archive ambiguity, every rename/fsync/receipt crash point, post-candidate drift, and P0 coupling.

Exact-head acceptance requires TDD evidence, focused/full local tests, Apple system-Python and Bash
3.2 proof, independent adversarial review, hosted CI/CodeQL, merge through protected `master`, one
native repair, and two verify-only passes.

The carrier then stops and hands off the observed new merge/generation/preparer/closure identities
to a separate P0 re-pin. P0 must replace its old pins and constant closure assertion with the pure
verifier, then undergo its own review/merge/native proof. OAuth, services, providers, routing,
workers, fan-out, failover, and CF2-I remain held.
