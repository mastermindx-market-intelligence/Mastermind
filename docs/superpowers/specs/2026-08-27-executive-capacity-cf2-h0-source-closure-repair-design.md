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

The repaired H0 generation is deliberately composite. The exact existing commit
`e4e44867ace335ac9208a3990a10c163e199492d` remains the current inert topology, Mastermind release,
rollback, and topology-preparer identity because those bytes do not change. The future exact merged
repair commit becomes `source_closure_repair_commit` and `generation_repair_commit`; it does not
become a topology release or replace `e4e44867...` as `preparer_source_commit`. Success is still not
CF2-P0 acceptance. The repair's terminal capability is:

```text
H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED
```

followed by two independent verify-only passes with zero program-directed and zero semantic
mutation under the sole kernel read-atime exception defined in section 13, each returning:

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
| Current topology/release/preparer | `e4e44867ace335ac9208a3990a10c163e199492d` |
| Macro commit | `dcdd939c45b23abce5ba04f95e330ac914a3904b` |
| Material digest | `35931b4ef965c5d67a7e01444dd483804e48671784716ea8196c94e925466650` |

If any old-state gate differs under root, the carrier refuses before installed mutation. It does
not rewrite the intent around a newly discovered state.

## 3. Capability ledger

| Capability | State before repair | State after this carrier's proof |
|---|---|---|
| H0 ordinary complete Git object closure | `BROKEN` | `BUILT_NOT_PROVEN` after merge; `PROVEN_LIVE` only after native repair plus two verify-only passes |
| H0 runtime, telemetry boundary, inert topology, rollback drill | `PARTIAL` as old receipted prerequisites | Preserved byte-for-byte and reverified; `e4e44867...` remains their current release/preparer identity |
| Truthful H0 source-closure identity | `BROKEN` | Future merge is the distinct current `source_closure_repair_commit` and `generation_repair_commit` |
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
- `HOST_PREREQUISITES.md` owns the native operator ceremony.

The fixed installed source path, Macro commit, eleven material paths, H0 lock, staging/archive/
generation roots, runtime, PyYAML, telemetry boundary, three realm identities, topology, rollback
contract, rollback-drill archive, legacy services, and socket absence remain canonical. The repair
does not install a new Mastermind release, rerender topology, rewrite broker configs, attestations
or plists, mutate launchd, rerun the rollback drill, or introduce another source root, lifecycle
store, queue, retry plane, receipt authority, service family, provider normalizer, or P0 gate.

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
`size`. The object inventory is the deterministic semantic identity of the reachable closure;
`payload_sha256` and the enclosing ZIP SHA-256 are per-carrier integrity identities. Raw pack and
ZIP bytes are not required to be reproducible across two semantically equivalent builds because
Git may choose different valid delta layouts. Two accepted carriers for the same commit must have
the same object count, object-inventory digest, and material rows, while their payload/ZIP hashes
may differ and remain independently receipted.

## 7. Ordinary complete installed repository

Materialization creates a new direct repository from the v2 pack and never clones/copies the
operator repository. Before installed mutation it must prove:

- exact detached `HEAD` at the Macro commit and a clean worktree;
- every reachable object is locally readable with the manifest type/size and strict ordinary
  `git fsck --full --strict` succeeds;
- exactly one ordinary `.pack`/`.idx` pair exists;
- direct inspection before `fsck` finds no loose replacement ref under `.git/refs/replace`, packed
  replacement ref in `.git/packed-refs`, graft row in `.git/info/grafts`, `.promisor`, alternate,
  shallow file, remote, promisor config,
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

Every security-relevant path is opened without following links and rebound by descriptor. The fixed
system root is traversed component-by-component from an open `/` descriptor; the root and its
capacity-source, generation, staging, archive, and lock parents stay open through the operation and
their pathname relations are revalidated before and after use. Preserved generation/archive,
runtime, release, topology, and rollback evidence is likewise read through retained descriptors.
This includes `.git/config`, `.git/packed-refs`, `.git/info/alternates`, `.git/info/grafts`, shallow
and promisor markers, their parents, and lock siblings; a symlink, hard link, or pre-existing lock
at any optional metadata location refuses rather than being treated as absence. Regular files have
link count one. Symlinks, sockets, devices, FIFOs, hard links, ACLs, non-root/non-wheel ownership,
wrong expected GID, and group/other-writable objects refuse. Every relevant object's BSD `st_flags`
must equal the frozen allowed value zero before acceptance and on revalidation. Only system-maintained
`com.apple.provenance` may exist; every other xattr refuses, and provenance bytes are excluded from
content identity.

Installed source directories are `root:wheel 0555`; ordinary files are `0444`; material paths
whose Git mode is `100755` are `0555`. Git config/index/pack/idx/object/info/manifest files are
single-link `root:wheel 0444`. Staging and repair archive directories are `0700`; durable intent/
receipt files are `0400`; the new generation directory is `0555` and its six files are `0444`.
Every publisher and reconciler receives both `expected_uid` and `expected_gid`, verifies both with
`fstat`, and binds them in its accepted metadata state. Before intent publication, the carrier
opens the staging, installed-source, generation, and archive parents and proves their `st_dev`
values are identical. Every transition uses descriptor-relative, no-replace
`renameatx_np(..., RENAME_EXCL)` semantics. `EXDEV`, an existing destination, or an unavailable
no-replace primitive refuses before overwriting; copying, deleting, or replacing as fallback is
forbidden.

The closed tree digest is SHA-256 over canonical compact JSON for rows sorted by UTF-8 POSIX
relative path. Every row has `path,type,uid,gid,mode,nlink,flags`; file rows also have `size,sha256`.
The root row path is `.`, modes are four-digit octal, and ACL/unapproved-xattr state prevents digest
construction.

Digest framing is exact: source-config/component digests hash compact canonical JSON without LF;
transport hashes stored bytes; repair intent/receipt hash compact canonical JSON plus one LF;
`components.json`, `source-config.json`, and `host-preparation-receipt.json` have no LF;
topology/rollback retain validated renderer bytes; rollback-drill receipt retains exactly one LF.

## 9. Source and H0 evidence schemas

The repaired generation has one explicit composite identity object with exactly:

```text
schema_version preparer_source_commit topology_release_commit
source_closure_repair_commit generation_repair_commit topology_state
release_install_state rollback_drill_state
```

Its schema is `mastermind.executive_capacity_h0_generation_identity/v1`.
`preparer_source_commit` and `topology_release_commit` remain
`e4e44867ace335ac9208a3990a10c163e199492d`.
`source_closure_repair_commit` and `generation_repair_commit` both equal the future exact protected
merge that implements this source-only repair and constructs its new generation evidence. Fixed
state values are
`topology_state=preserved_byte_for_byte`, `release_install_state=not_installed`, and
`rollback_drill_state=preserved_not_rerun`. `components.json` adds this object as
`h0_generation_identity`; executable, entrypoint, inventory, telemetry, runtime, topology, and
rollback component schemas and bytes otherwise remain unchanged.
The top-level `components.json` field set is exactly:

```text
source_executable_identity source_entrypoint_identity source_working_directory_identity
inventory_config telemetry_config h0_generation_identity
```

The source config advances to `mastermind.executive_capacity_source_config/v2` because its working
directory identity and generation composition change. It has exactly:

```text
schema_version p0_source_kind source_contract_id source_release_commit
source_executable_identity_digest source_entrypoint_identity_digest
source_working_directory_identity_digest allowed_environment_names
inventory_config_digest telemetry_config_digest timeout_seconds stdout_max_bytes
stderr_retained_max_bytes no_shell network_denied write_denied preparer_source_commit
topology_release_commit source_closure_repair_commit generation_repair_commit
h0_generation_identity_digest
```

The four commit fields equal the composite identity above and the identity digest hashes its
canonical compact JSON. The generation still contains exactly the same six filenames.

The host receipt advances to `mastermind.executive_capacity_host_preparation/v2` and has exactly:

```text
schema_version outcome preparer_source_commit topology_release_commit
source_closure_repair_commit generation_repair_commit source_release_commit
producer_material_source_digest source_config_digest component_manifest_digest
source_closure_state source_repair_receipt_digest prior_generation broker_count
broker_topology_digest rollback_contract_digest rollback_drill_receipt_digest
service_state socket_state control_state credential_state worker_execution_state cf2_i_state
```

The four commit identities equal the source config. `outcome` remains
`H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED`; `source_release_commit` remains the Macro commit.
`source_closure_state=complete_non_promisor_offline_no_lazy_fetch`. `prior_generation` has
exactly `status`, `generation_digest`, and `generation_artifact_sha256`; `status` is
`archived_superseded_generation_same_current_e4_topology_identity`, the digest is
`2b05a61f54c876f00c3f03d51bd9df72de4a73e76bc06b2e7bc13a11ee203d60`, and its six-name hash map
is exactly the table in section 2. The old generation is superseded; `e4e44867...` is not.

The new generation basename is its new canonical source-config digest. The old basename may not
remain a visible current generation after commit. `broker-topology.json`,
`rollback-contract.json`, and `rollback-drill-receipt.json` in the new generation are byte-for-byte
copies whose hashes remain the section 2 values; they are not rerendered.

The digest graph is acyclic and one-way. The working-directory identity binds the semantic object
inventory. `components.json` binds that identity and the composite H0 identity. `source-config.json`
binds the individual component digests and repeats both commit axes. The repair receipt binds the
intent, installed/archive tree digests, object inventory, source-config digest, and component-
manifest digest. Only then does the host receipt bind the repair-receipt digest plus source/config
and preserved topology/rollback digests. Neither the repair receipt nor any earlier object contains
the host-receipt digest. The proof packet records the host-receipt and closed-generation hashes
externally.

## 10. One durable repair intent and receipt

The carrier uses the existing lock at
`/Library/Application Support/MastermindExecutive/locks/cf2-h0.lock`. After the candidate and all
old-state gates verify, but before installed mutation, it publishes one
`mastermind.executive_capacity_h0_source_repair_intent/v1` object with exactly:

```text
schema_version intent_id operation preparer_source_commit topology_release_commit
source_closure_repair_commit generation_repair_commit source_release_commit expected_uid
expected_gid filesystem_device
producer_material_source_digest old_generation observed_old_source_tree_sha256
candidate_transport_sha256 candidate_transport_manifest_sha256 candidate_object_count
candidate_object_inventory_sha256 candidate_source_tree_sha256 service_state socket_state
credential_state worker_execution_state cf2_i_state
```

`operation=side_by_side_non_promisor_rematerialization`. `old_generation` has exactly
`generation_digest`, `preparer_source_commit`, `topology_release_commit`, `outcome`, and
`generation_artifact_sha256`; their values are the current `e4` identity, old outcome, digest, and
six artifact hashes from section 2.
The identity fields equal section 9, `expected_uid=0`, `expected_gid=0`, and `filesystem_device` is
the common decimal `st_dev` proven for all transition parents. `intent_id` is SHA-256 over canonical
compact JSON of every other field. The archive is derived as
`capacity-archive/source-closure-repair-<intent_id>` and is not caller-selected.

After installed verification, the same archive receives one
`mastermind.executive_capacity_h0_source_repair/v1` receipt with exactly:

```text
schema_version outcome intent_id preparer_source_commit topology_release_commit
source_closure_repair_commit generation_repair_commit source_release_commit expected_uid
expected_gid filesystem_device producer_material_source_digest prior_generation_digest
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

The carrier performs this exact sequence. Only steps 1 and 2 precede lock acquisition, and neither
may inspect installed host state:

1. Parse and completely validate one of the two exact command forms below without reading host
   state or acquiring the lock.
2. Perform only the allowed preflight: verify effective UID zero and verify the sealed Mastermind
   checkout at the exact `source_closure_repair_commit`.
3. Acquire the existing H0 lock. From this point through exit, every reconciliation, installed-host
   observation, candidate operation, publication, transition, commit, and proof runs while holding
   that lock.
4. Reconcile any exact prior intent before observing or constructing a new operation. Ambiguous or
   nonmatching prior state refuses under the section 12 law.
5. Verify preserved H0 runtime/topology/telemetry/legacy/service/socket invariants and the
   repair-specific principal facts defined below without provider-home access.
6. Match the old generation and its six old artifact hashes.
7. Open all transition parents, prove one `st_dev`, prove every destination absent, copy the
   operator-owned v2 transport by no-follow descriptor, and bind its independent SHA-256.
8. Materialize and completely verify the side-by-side source candidate.
9. Publish and fsync the one durable repair intent.
10. Move the old source into the intent archive with no-replace rename and fsync both parents.
11. Install the candidate at the fixed source path with no-replace rename and fsync both parents.
12. Move the old generation into the same archive with no-replace rename and fsync both parents.
13. Reverify source closure and every preserved invariant.
14. Publish/fsync the repair receipt, build the new hidden six-file generation candidate, and
    verify all internal/external digest links, including byte equality for preserved topology and
    rollback artifacts.
15. Reverify source, repair archive/receipt, generation candidate, runtime, topology, rollback,
    telemetry, services, sockets, legacy files, and principals.
16. Rename the hidden generation to its digest basename with descriptor-relative no-replace rename
    as the last semantic filesystem mutation and sole commit point.
17. `fsync` the open capacity-generations parent directory as the required durability barrier,
    close descriptors, write the fixed success sentinel, and exit zero.

No correction, content rewrite, topology render, release install, or rollback occurs after the
final rename. The parent-directory `fsync`, descriptor closes, and fixed stdout write are durability
and reporting operations, not semantic filesystem mutations. The retained lock file is an
exclusion artifact, not a state record.

The repair-specific principal proof is deliberately narrower than P0. It makes attribute-scoped
directory-service queries for only fixed record names, UIDs, primary GIDs, and fixed group
membership/nonmembership facts, and verifies the fixed topology labels are disabled/unloaded and
their socket nodes absent. It does not request a home-directory attribute and never resolves,
stats, reads, traverses, or enumerates any provider-home path. H0 receipts claim only these fixed
identity/membership/topology facts.
The later P0 ceremony separately re-proves provider-home ownership, mode, and non-traversal.

The CLI accepts only these ordered argv forms:

```text
/bin/bash ops/executive_os/repair-capacity-source-closure.sh repair \
  --expected-source-closure-repair-commit <40-lower-hex> \
  --operator-user <local-name> \
  --macro-transport <absolute-transport-path> \
  --macro-transport-sha256 <64-lower-hex>

/bin/bash ops/executive_os/repair-capacity-source-closure.sh verify-only \
  --expected-source-closure-repair-commit <40-lower-hex>
```

`local-name` matches `[a-z_][a-z0-9._-]{0,63}`. `absolute-transport-path` is one absolute POSIX path
argument with no empty component, `.` or `..` component, CR, or LF; its single-link regular-file
metadata and supplied-byte digest are verified only after lock acquisition as a host-state gate,
with mismatch returning exit 65.
`generation_repair_commit` must equal the expected source-closure repair commit. Missing, extra,
reordered, mixed-mode, duplicate, help, empty, malformed, adversarial, relative-path, wrong-case
digest/commit, or illegal path/digest combinations return exactly exit 64,
`INVALID_INVOCATION\n` on stdout, and empty stderr without acquiring the lock or reading host state.

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

After the final generation rename succeeds, the repair is semantically committed. A failure or
ambiguous result from the immediately following capacity-generations parent `fsync` returns exit
70 with no pass sentinel and no automatic rollback: only the same carrier may reconcile. On replay,
the carrier accepts committed state only after reopening and fully reverifying the visible
generation, intent, repair receipt, installed source, archived source/generation, identity links,
and the parent-device law. It then completes the durability barrier if needed and may emit success.
The carrier never restores the archived promisor source automatically after a visible committed
generation. Later drift is a verify-only refusal and requires a new Sol ruling.

Crash tests freeze four final-publication boundaries: before rename; after rename but before parent
`fsync`; after parent `fsync` but before stdout; and after stdout. Each replay must produce exactly
one verified committed generation or the uniquely verified precommit state, never two visible
generations, overwrite, deletion, or an inferred pass.

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

Review, CI, Macro acquisition, v2 transport construction/hash, and construction of a digest-bound
exact-merge Git bundle occur before privilege. The reviewed bootstrap runs only as the unprivileged
operator. Before it observes the bundle or creates the privileged namespace, it resolves its own
UID and username with absolute `/usr/bin/id` calls, rejects UID 0, and requires the supplied
operator username to equal that exact non-root identity. Either boundary failure returns only
`64 INVALID_INVOCATION` with empty stderr. Root receives no shell, heredoc, interpreter `-c`, or
stdin program text: before carrier authentication it executes only reviewed absolute macOS
system-tool argv through `sudo`. Those
tools copy the inert bundle without preserving metadata into the exclusive fixed root-created
`0700` namespace `/private/var/root/mastermind-h0-root-carrier`, remove ACLs/xattrs/flags from the
new inodes, and verify the recorded digest. An initially observed symlink refuses before namespace
creation; source metadata is never changed; a source race must produce deterministic refusal or the
same already authenticated inert bytes.

Fully hardened Git is local-file-only and ignores system/global/local config, hooks, fsmonitor,
attributes, replacement refs, external diff/textconv, prompts, lazy fetch, optional locks, ambient
locale, `HOME`, and `PATH`. It extracts the exact five-file local-module closure
(`repair-capacity-source-closure.sh`, `capacity_host_artifacts.py`,
`capacity_source_contract.py`, `provider_worker_slots.py`, and `provider_identity_policy.py`),
binds every path and Git mode to the exact commit, verifies every retained file with Git blob
framing, and writes them into new root-owned single-link inodes. The authenticated Python verifier
independently repeats the exact commit/mode/blob checks from the root-created bare repository before
the carrier shell runs. Root never executes an operator-created inode and performs no network
access. Each authenticated repair or verify-only child runs as one tracked process group. A HUP,
INT, or TERM delivered only to the bootstrap terminates that active child and its descendants and
reaps the group before namespace cleanup; no descendant can mutate after the exit-70 receipt. The
fixed namespace is created no-replace, is removed on refusal, success, HUP, INT, and TERM, and is
never auto-removed when found preexisting. Cleanup failure is a typed non-success and all three
pass sentinels remain buffered until cleanup succeeds.

One native administrator dialog executes the repair once from that root-created carrier, then runs
verify-only twice using the exact CLI grammar. The installed `release_manifest.py` is never
executed or imported: the reviewed carrier authenticates the preserved e4 release and its manifest
strictly as descriptor-relative inert data. Each pass independently reopens
and verifies complete object closure, the six-file generation, repair archive/receipt, runtime,
byte-preserved topology/rollback evidence, telemetry boundary, fixed directory-service identity
and membership facts, disabled/unloaded labels, absent sockets, and legacy state. Verify-only does
not write the lock, create an intent, perform program-directed or semantic mutation, or access
provider homes.

Verify-only performs zero program-directed and zero semantic mutation. Kernel-induced access-time
advancement from required reads is the sole permitted observable metadata delta. Atime is
non-authoritative, may only remain equal or advance, and is never set, restored, decreased, or used
to conceal another change. Namespace, bytes/digests, device/inode identity, type, mode, UID/GID,
links, size, flags, ACLs, xattrs, mtime, ctime, topology/rollback evidence, launchd state, sockets,
and legacy state remain exact. This read-atime observer effect does not weaken content verification,
identical scoped semantic digests, the no-write law, or any lock, intent, publication, P0, provider,
service, socket, routing, or worker hold.

This exception applies only to the fixed installed H0 root. Primary host evidence proves that root
is on writable APFS, is not mounted `MNT_RDONLY`, and its mount does not expose `MNT_NOATIME`;
mandatory full independent content verification necessarily reads installed bytes. The exception
does not apply to any other filesystem, root, provider, or worker surface.

The governed packet records sanitized facts only: `e4e44867...` as current topology-preparer and
topology-release identity; the exact source-closure/generation repair merge; v2 ZIP/payload/manifest
hashes as per-carrier integrity; semantic object count/inventory digest; new generation basename
and six hashes; unchanged topology/rollback hashes; repair intent and receipt hashes; UID/GID and
common-device pass facts; archived old generation/source digests; the repair sentinel; two verify
sentinels; zero program-directed and semantic mutation for each verify pass; and any kernel
read-atime advancement as the sole non-authoritative observation. The packet does not record
provider-home paths or credential material.

## 14. Testing and exact stop condition

Tests must prove refusal for marker deletion without complete objects, promisor-enabled `fsck`, a
fabricated `lazy_fetch_impossible`, v1/stale receipts, missing/extra objects, alternates, shallow
state, filters, remotes, loose replacement refs, packed replacement refs, `.git/info/grafts`, and
symlinked/hard-linked/locked alternates, shallow, promisor, config, packed-refs, and graft metadata.
They also cover attached/dirty worktrees, extra worktree files, unsafe Git metadata, wrong UID or
GID, device mismatch/`EXDEV`, existing rename destination, missing no-replace support, every exact
CLI refusal, archive ambiguity, every rename/fsync/receipt crash point including the four final
boundaries, post-candidate drift, equivalent semantic inventories with unequal valid pack bytes,
provider-home access attempts, topology rerender/release install, and P0 coupling.

Exact-head acceptance requires TDD evidence, focused/full local tests, Apple system-Python and Bash
3.2 proof, independent adversarial review, hosted CI/CodeQL, merge through protected `master`, one
native repair, and two verify-only passes.

The carrier then stops and hands off both identity axes to a separate P0 re-pin:
`e4e44867...` remains the exact current topology-preparer/topology-release identity, while the
observed merge is the exact current source-closure/generation-repair identity. P0 updates its
prerequisite pins only after those merge/install identities and both verify receipts exist, and
replaces its constant closure assertion with the pure verifier. It separately re-proves provider-
home metadata/non-traversal and undergoes its own review/merge/native proof. OAuth, services,
providers, routing, workers, fan-out, failover, and CF2-I remain held.
