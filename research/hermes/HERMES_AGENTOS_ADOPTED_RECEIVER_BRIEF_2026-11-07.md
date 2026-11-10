# Adopted Agent OS context receiver — bounded implementation
Date: 2026-11-07
Program/root/parent metadata: hermes-teammate-evolution-20261106-c3
Authority: Chairman asked to take leadership to get the Hermes teammate completely implemented.
Protected procedure pin: 650b81344a7cf5790cdf617dff6e1e2175742037 (bootstrap major 1).
Implementation base: e37dc82f070fd391e29f0dbd0bf46b022166beea, protected master after native PR2134 merge4d1561bcba1bfad583c75e419ced9a6ff0f3fa40. Merged Agent OS provider PR2163/5ca25e561ffaeacb4ef94bb08f507617f80d0607 is already present; do not recreate it.
Source-only bounded task. This packet is not a Runtime Job, capability grant, host enrollment, or deployment authority.

## Outcome and scope
Implement an internal callable adopted-snapshot context reader on the incumbent InstalledBootPacketCollector. It must execute Macro's actual compile-context --workstream implementation against the verified private materialization of the installed/adopted Macro revision under the incumbent qualified CF2 compiler runtime. Return complete exact UTF-8 bytes and bounded independently checked provenance only after pre/post source/runtime seals.

No public endpoint, MCP catalogue change, capability grant, consumer enrollment, native memory activation, installation, service mutation, credentials, latest canonical DATA permission, new memory store, cache, queue, watcher, runtime inventory, or owner. Existing COO v1 digest remains 5cf2a0de4a47686c545d1ee3d9c388ab4dc94c880cb0670140de2eca2e54f550.

Use the supplied source base in a new isolated task worktree/branch sol/hermes-agentos-adopted-receiver-20261107-c3. Check actual writer/effect fences. Never reset another workspace. No existing worker owns this task. Existing vendor/request-observation/EVAL runs are different tasks and may not be replayed.

## Allowed changes
Existing:
- integrations/executive_mcp/installed.py: fixed reader factory/read method; one mutually exclusive context operation; fixed materialization selection; bounded child invocation, output validation, post-check return.
- control_plane/installed_project_read_binding.py: one fixed _METHODS kind using incumbent nominal issuance/pre/post identity checks.
Proposed new:
- control_plane/agentos_context_bundle.py: content-only facade and closed result/receipt validator; constructor cannot issue binding; core cannot import integration.
- scripts/agentos_context_bundle_entry.py: fixed isolated child entry executing incumbent Macro CLI, preserving stdout.
- tests/test_installed_agentos_context_bundle.py
- tests/test_agentos_context_bundle_entry.py
- docs/hermes/AGENTOS_ADOPTED_CONTEXT_RECEIVER.md
If another production path must change, return the concrete dependency and proposed scope instead of silently widening it. Existing source and fixtures may be read.

## Actual owner path and proposed API
Existing project_plan_reader -> AgentOsProjectPlanReader.read -> read_installed_project_binding -> collector.read_project_plan -> _collect_packet is the model.
Proposed:
reader = collector.agentos_context_reader(macro_root=collector_macro_root)
raw_bundle, receipt = reader.read(work_ref="WS:EXACT-WORKSTREAM")
InstalledBootPacketCollector.read_agentos_context(*, work_ref: str, timeout: float = 25.0) -> tuple[bytes, dict]
Fixed token budget4000. Public facade takes only work_ref. Timeout is internal bounded execution control, never authority.
_METHODS["agentos_context"]="read_agentos_context".

Issue only from exact InstalledBootPacketCollector, matching absolute installed Macro coordinate, release code root, non-null expected source SHA, _allow_synthetic_fixture false, private nominal binding. Preserve original owner identity/coordinates/method/reader identity before and after call. Bare/copied/forged/equal-coordinate second owners do not qualify.

Add exactly one operation to _collect_packet's mutual exclusion. Refuse active _CANONICAL_PROJECT_DATA and canonical compilation scopes for this operation. Do not create CanonicalProjectDataView. No caller code/data revision, root, Python, script, command, environment, dependency directory.

## CODE/DATA custody
For this leaf compiler CODE commit == adopted DATA commit == bundle repo_sha.
Reuse _snapshot_pair, _VerifiedRepositorySnapshot, _build_macro_materialization_plan, _materialized_macro_root, _verify_materialized_macro_root, _generation_pair, cumulative deadline, bounded child runner.
Execute in verified private materialization, not live checkout after merely hashing entry script. Verify materialization and original source after execution. A transient restored mutation must remain detectable.
Run fixed CLI only: compile-context --workstream <exact WS ref> --json --budget 4000.
Required executable closure: scripts/agentos.py and scripts/agentos_project_plan_contract.py plus qualified Python stdlib/PyYAML. Preserve fixed existing helpers scripts/__init__.py and scripts/audit_stranded_work.py as appropriate; no arbitrary discovery. Lazy helper must resolve inside qualified materialization.
Do not invoke free-text engine.context_index.packet, worktree scanning/audit_stranded_work, or ship/agentos_ship_capture paths.
Reuse records/workstreams/decisions/discoveries/handoffs/programs/active-build inputs. Add only context-operation fixed DATA selections config/compiled_kill_registry.yml and config/context_index.yml. Preserve owner path-existence semantics and honest optional-missing degradation. Missing executable dependencies, unsafe topology, inconsistent bytes or wrong target refuse the read.

## Incumbent CF2 runtime
Reuse control_plane.ceo_boot_packet.attest_capacity_boot_runtime and existing capacity_source_contract/capacity_host_artifacts. Require exact Python binary/ownership/topology, PyYAML RECORD, complete runtime tree, isolated import probe. Fixed child argv qualified_python -I -S -B <fixed release entry> ...
Only CF2-attested dependency location exposed. No ambient sys.executable/pip/user site/YAML fallback.
Use closed _installed_child_env and fixed Mastermind source join; Terminal join absent. Do not inherit HOME, bearer, PYTHONPATH, proxy or arbitrary Git configuration.
Bracket compile with incumbent runtime qualification. Source checks, probes, compile, materialization, post-checks spend ONE cumulative deadline; no renewed clocks. No new custody service.

## Exact bytes and receipt
Preserve successful stdout bytes exactly; no parse-reserialize, summarization, reranking or tail deletion. Raw cap128KiB. Strict duplicate-key/nonfinite/malformed JSON rejection; validate owner schema, exact WS, resolved target, mandatory accounting arrays, exact revision. Reuse incumbent ops/fabric_launch/agentos.py validation semantics at integration boundary, not a duplicate compiler. Nonzero/timeout/invalid UTF8/oversize/unproven child cleanup refuse whole result without partial bundle or raw diagnostics.

Return (raw_bundle: bytes, receipt: dict), closed bounded schema including:
schema, owner="agent_os", source_mode="ADOPTED_SNAPSHOT", workstream, token_budget=4000, bundle_sha256, source_script_sha256, compiler_sources, compiler_closure_sha256, mastermind_source_sha, compiler_code_commit, data_commit, repo_sha, runtime_commitment, generated_at, degraded_count, omitted_count, execution_authority=false.
compiler_sources: repository-relative actual executable paths, Git blob IDs and SHA256; document canonical digest representation. runtime_commitment: actual accepted CF2 binary/PyYAML/tree commitments, no credentials/host paths. CODE/DATA/repo commit must agree. generated_at means bundle generation, NOT latest canonical DATA freshness. Preserve provider-compatible fields owner/workstream/bundle_sha256/source_script_sha256/repo_sha/generated_at/execution_authority.

## Actual immutable compiler fixture
Reuse tests/fixtures/agentos-project-plan-owner-contract.json, not a fake emitter.
Macro revision138a2c5cdc391b6319c797d9206bc66faa635cdc, treefd9c91aef9915f9136243f21e831c9837b8bd583.
agentos.py blob7b24ef53e2559cf433a8d3ae8b427b9179ed8e8f, SHA256575d9b18d3e69f250aa3156d181457aaa5e3303522f65505fb64e4772f22df49.
helper blob84ff653fe948a138efb1ad0e0e3b7e44c9058e89, SHA256fe93bd433963d740dc617a3df91a13baee0b919b0e4cd1ebab158cff929608b6.
Verify hashes. Use actual bytes in temporary Git repository with valid authored WS/decision/discovery or handoff/DNR/config records. Fixture proves source behavior, not installed Macro/CF2 enrollment.

## Focused acceptance
1 Actual collector -> issued reader -> nominal binding -> actual Git/source qualification -> private materialization -> actual fixture compiler/helper -> exact bundle -> runtime/source post-check -> receipt.
2 Verify meaningful record semantics, whole stdout identity and receipt revisions/hashes.
3 Bare/forged/copied/retargeted reader, changed collector coordinates/method/runtime/source, helper/config/directory drift, restored transient drift, symlinks, wrong revision/workstream refuse.
4 Fixed -I -S -B argv + closed env; poisoned PYTHONPATH/user startup/shadow YAML/ambient helper cannot execute. Wrong runtime commitments/no CF2 qualification refuse without fallback. Explicit runtime fixture doubles must be labeled, never called production attestation.
5 Whole over-budget mandatory output retained. Oversize/duplicate keys/nonfinite/invalid UTF8/wrong schema/missing accounting/timeout/uncertain cleanup refuse; deadline shared.
6 Active latest-DATA or canonical compilation scopes refuse. V1 COO catalogue/profile digests and representative installed read/binding/materialization tests unchanged.
Run new tests and directly affected existing reader/binding/runtime/materialization tests. Broaden only for concrete failures/required CI.
DONE_WHEN: source-complete internal adopted reader with real incumbent-owner/actual-compiler tests and complete exact bytes/receipt, no new public tool/grant/enrollment. Return exact commit/PR, paths, API/schema, fixture identity, actual-code vs runtime doubles, commands/results, remaining runtime/transport/enrollment proof. Do not claim teammate completion.

## Follow-on remote contract (SPEC ONLY)
Future authenticated call executive_agentos_context({"work_ref":"WS:..."}) on same original Executive MCP session, explicitly enrolled context catalogue; response strict base64 exactbytes +receipt, entire envelope within incumbent256KiB. Native adapter verifies original session, current claim pre/post, hashes/revisions/budget/source mode; no retarget/retry of uncertain RPC and no dummy owner_root.
Separate source work must add fixed per-principal v1/v2 catalogue selection derived from existing installed mission/profile grants; preserve v1 digest and same Server/endpoint/process. An actual new grant/profile enrolls context; mixed/unknown catalogues refuse. Adopted-only does not grant read_latest_project_data. Native memory requires explicit remote binding plus original loader/current-claim/window-fit proof. Do NOT implement these follow-ons in this packet.
