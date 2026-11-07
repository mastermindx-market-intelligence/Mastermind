# Canonical stdout for new Macro worktrees

The current native controller publishes successful `--new-macro-worktree`
stdout at the Fabric-owned `lanes/<run-id>.remote.stdout` path, including when
the caller requests a distinct `--out` mirror. Publication and result reading
share the same byte and inode binding.

This is the canonical implementation of the intent explored by historical
PR #1651. That proposal's patch package is not the installed source. The current
implementation composes the protected native closure and preserves the existing
session-receipt collection, physical transport owner, worker settlement,
provider lease, and acceptance boundaries.

## Publication contract

1. The exclusive per-run log creator first writes
   `MACRO_RESULT_REQUIRED schema=1` and flushes both the file and its parent
   directory. The unchanged
   `RUN_RESERVED` event follows. Missing, empty, partial, or marker-only logs
   cannot select legacy result reading, including a crash before destination
   checks. Before a provider lease or remote effect, the controller invokes
   `macro-result-prepare`. It qualifies
   the canonical and optional custom destination parents through the existing
   `DirectoryChain` and declared native owner adapter. Occupied leaves,
   including dangling symlinks, are refused. Missing custom parent directories
   are created only beneath held, qualified directory descriptors.
2. The helper durably appends one `MACRO_RESULT_POLICY` JSON record to the
   existing owned controller log. Failure to prove that append refuses launch.
   The record binds the run, host, log inode, qualified output parents and
   canonical/custom destination names. Output paths refer to stable physical
   data owners, so a later immutable code generation can still read the result.
3. Only an observed successful worker return uses the new publication path.
   Rsync collects into a private `.macro-capture.<run-id>.*` file in the original
   lanes owner. The helper holds its descriptor, enforces a maximum of 8 MiB,
   reads the exact bytes, makes the file private, and synchronizes it.
4. An exclusive hardlink publishes the canonical name. The still-open capture
   descriptor and both visible names must identify the same inode and bytes.
   A distinct custom output is copied into an exclusively created private
   `.macro-copy.<run-id>.*` inode. Its descriptor remains open through hardlink
   publication and verification. Existing destinations are never replaced.
5. Only after all required destinations pass revalidation does the helper
   durably append `MACRO_RESULT_PUBLISHED`. Its versioned JSON binds the policy
   digest, file identities, exact byte count, SHA-256 values, and retained
   staging names. Controller success still requires the existing terminal
   ledger acknowledgment and `DONE rc=0 signal=ok`.

A default output expressed through a declared native alias and the same output
expressed through its physical owner are one destination. Equality depends on
qualified parent identity and leaf name.

## Reading and status

Both `fabric_task.inspect_run()` and `read_result()` use the same verified
snapshot routine. A new-policy result is available only when:

- Its supported, unique policy and publication records agree.
- Successful worker-return evidence precedes publication, and successful
  terminal evidence follows it.
- No conflicting delivery failure or execution-uncertainty event is retained.
- The canonical result, its retained staging alias, and any required custom
  mirror still match the recorded descriptors, file metadata and exact bytes.
- The owned log and directory chains remain unchanged across the observation.

A regular canonical leaf alone is insufficient. This includes reads during
collection, after a canonical link but before a final binding, after partial
log publication, and after a custom-output publication failure.

The status parser recognizes the new event namespace before parsing complete
JSON records. Malformed, partial, duplicate, or unsupported evidence produces
an unreadable status instead of reaching the legacy status scan. Validated
JSON payloads remain data: a filename containing `DONE`, `RESULT_UNAVAILABLE`,
`CONTROLLER_PROCESS_UNPROVEN`, or a worktree marker cannot manufacture terminal
status, preserve a lease, or add a reclaim-plan launch event. The original log
bytes remain the custody and binding evidence.

Intact legacy logs retain their bounded result-read behavior. Missing, empty,
partial or changed logs no longer allow an orphan file to be read as a result.
Successful publication does not grant ledger acceptance or parent authority.

## Failure and custody

Canonical and custom staging aliases remain retained. Each successful inode
has two known links: its staging name and published name. Removing a staging
alias invalidates the binding; it is not disposable shell scratch. A canonical
staging alias consumes another directory entry, not another stdout copy.

On failure, the helper preserves files and withholds the positive binding. It
does not unlink a pathname that could now belong to another writer. A canonical
file can therefore remain as diagnostic evidence when a later custom
publication fails. Fabric will not expose it as a verified result.

Observed nonzero worker output keeps its existing diagnostic transport behavior,
but an opted-in new Macro run has no successful result without the positive
binding and successful terminal event. Execution uncertainty still preserves
the incumbent lease and recovery boundary. A local delivery failure does not
turn a known terminal worker into an unobserved execution, and none of these
events authorizes a retry.

The existing exclusion of new Macro worktrees from bound physical-root worker
shapes is unchanged. This repair changes local publication through native
owner aliases; it does not admit a host, modify a host registry, or replay a held
operation.

## Trust and portability

The existing trusted-owner, append-only controller log is the evidence owner.
This protocol does not isolate files or logs from a hostile process with the
same UID.

Portable pathname hardlinking cannot atomically require that the source name
still denotes an already-open descriptor. Post-link verification detects the
substitution, and bound Fabric readers withhold the result. The protocol does
not promise that an unqualified name can never briefly be visible to a raw
filesystem reader. Complete malicious rewriting of valid historical evidence
is outside the owned append-only model.

## Qualification

The focused tests are `tests/test_macro_result_publication.py` and
`tests/test_macro_result_controller.py` beneath this directory. The first builds
the actual 85-file native closure, publishes sealed fixture generations and
calls the real task APIs. The second runs the actual Bash controller against
finite inert SSH, rsync, broker and provider boundaries.

The cases cover descriptor/name substitution, retained foreign files,
publication crash cuts, duplicate or malformed evidence, size bounds, native
aliases, generation changes, status tokens in data, custom collisions,
diagnostic failures and session-receipt preservation. The repository's existing
native qualification wrapper discovers these tests. Fixture tests create no
provider requests and are not live worker execution proof.
