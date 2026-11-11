# Adopted Agent OS context receiver

This receiver makes the existing installed source owner return the actual Agent
OS context compiler's exact UTF-8 bytes for one explicitly selected workstream.
It is an internal content capability. It does not create a memory store, public
MCP tool, credential, latest-DATA permission, or native Hermes enrollment.

## Owner composition

`InstalledBootPacketCollector.agentos_context_reader(macro_root=...)` issues an
opaque reader through the existing `installed_project_read_binding` owner. A
bare constructor, copied reader, changed owner coordinates, replaced callback,
synthetic collector, or missing Mastermind source pin cannot issue a usable read.

The read accepts only the existing closed `WS:` selection. It rejects an active
canonical-DATA or project-compilation scope: this first operation has **CODE =
DATA = the adopted Macro snapshot**. It does not silently turn an adopted read
into a latest-DATA read. The collector's existing Git observations, private
materialization, process-group settlement, and pre/post source-generation seals
remain the source authority. No acquisition cache, retry queue, or new watcher
is introduced.

The context materialization includes the ordinary brief inputs and the tracked
`config/context_index.yml` and `config/compiled_kill_registry.yml` inputs when
present. The original owner decides how to account for absent optional context.
Both `scripts/agentos.py` and `scripts/agentos_project_plan_contract.py` are required.
Artifact/ownership path-existence probes retain their original materialization
semantics; materializing a file does not authorize it to execute.

## Exact compiler path and import provenance

The existing CF2 capacity-runtime attestor qualifies the selected interpreter and
dependency location before and after compilation. The child runs the fixed
Mastermind entry under `-I -S -B`, then invokes the original Macro CLI with exactly
`compile-context --workstream WS:<KEY> --json --budget 4000`. No replacement parser,
context summary, ranking policy, or second retrieval engine is used.

The child replaces ordinary `PathFinder` resolution with frozen qualified
runtime/dependency paths. Macro's own `sys.path` insertion cannot add its
materialized record/artifact tree to ordinary imports. A missing optional module
may remain missing; a module found only through the widened path latches a
refusal, even if the compiler catches `ImportError`. Located disallowed code is
never executed. This is an import-provenance constraint for the reviewed compiler,
not a sandbox for arbitrary hostile replacement Python code.

The reviewed owner's explicit plan-helper loader is a separate fixed source
path. Since `-B` prevents bytecode writes but permits reads, the child refuses any
entry at that helper's exact `cache_from_source` candidate before executing the
CLI. It also requires an unset `sys.pycache_prefix` and optimization level zero.
It neither deletes nor hides that materialized artifact. The incumbent source
seals continue to cover the main script, helper, inputs, and Git observations.

The child buffers the entire successful output before emitting it. A failed
compiler, provenance refusal, invalid encoding, or oversized result emits no
partial context or raw diagnostics. The parent uses the existing Agent OS bundle
validator, requires the original workstream/adopted commit and fixed token budget,
and returns the **unchanged bytes**, including mandatory over-budget sections,
degraded inputs, exclusions, and omitted-item accounting.

## Receipt meaning

The closed `mastermind.agentos_adopted_context_receipt.v1` receipt contains:

| Commitment | Exact coverage |
| --- | --- |
| Bundle SHA-256 | Original compiler output bytes, including accounting tails. |
| Compiler sources | Git mode/blob, SHA-256 and length of the two permitted Macro executable files; scope is `fixed_macro_entry_and_helper`. |
| Source inventory | Digest/count of the verified materialization's files plus directory/path-existence entries and adopted commit. It is not a claim that every input was read or executed. |
| Source observation | Existing Mastermind, Macro and private-materialization generation seals, including the incumbent owner's Git metadata observations. |
| Runtime commitment | Exact interpreter version/binary digest, PyYAML version/RECORD digest and runtime-tree digest checked by the existing CF2 owner. It is not an invented universal OS-library closure. |
| Compiler closure SHA-256 | A digest joining the listed compiler facts, runtime commitment and inventory digest; it does not expand their coverage. |
| Import policy | `qualified_runtime_paths_v1`, implemented by this fixed release entry. |
| Deadline semantics | `cooperative_result_deadline_v1`; see below. |
| Generation/accounting | Owner-generated timestamp and degraded/omitted counts. Generation time does not prove source freshness. |

The receipt has `execution_authority: false`. Context prose, cited decisions,
source hashes and this receipt cannot grant an execution or tool capability.

## Deadline and failure behavior

One original cumulative deadline (at most 25 seconds) covers source acquisition,
materialization, qualification, child execution and final acceptance. Runtime
probe subprocesses receive the remaining budget. Checks before and after the
incumbent synchronous attestor refuse a late result and prevent a later stage.
The attestor's filesystem walks and hashes are not forcibly interrupted, so this
slice does **not** claim a hard wall-clock return bound. It does not create a nested
process owner to imply such a bound.

Original child failures and process-group cleanup uncertainty cause closed
unavailability, with no retry or partial context return. A post-execution runtime
or source change withholds the result even if compilation itself succeeded.

## Evidence and remaining integration

`tests/test_installed_agentos_context.py` uses the immutable actual Macro compiler
and helper fixture at `138a2c5cdc391b6319c797d9206bc66faa635cdc`, real Git repositories,
the private materializer, the isolated child and the actual bounded subprocess
runner. Its records and CF2 host-attestation seam are explicit test fixtures, not
production enrollment or custody proof. A typed plan-adoption decision exercises
the real sibling helper. Import-policy tests separately invoke the captured
`_parse_moment` fallback; the fixed CLI does not pass `--now` and does not claim to
exercise that branch during ordinary context compilation.

Decisive checks include exact-byte preservation, required-source absence,
original/private mutate-and-restore fences, copied/retargeted-reader rejection,
closed receipt and output validation, mandatory over-budget content, caught
artifact imports, qualified dependency shadows, a valid matching-header hostile
helper bytecode artifact, late attestation, changed runtime commitments, and
cleanup uncertainty without retry.

Public exposure still requires the existing authenticated COO/App/Control path,
an explicit mission/profile grant and a compatible principal-selected catalogue.
Native memory still requires actual plugin-loader enrollment, per-admission
preparation before context compaction, original-claim currentness and real model
window/revocation/restart proof. None is asserted by this internal receiver.
