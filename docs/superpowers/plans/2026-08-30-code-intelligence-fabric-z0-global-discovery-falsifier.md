# Code Intelligence Fabric Z0 Global Discovery Falsifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove or refuse a disposable self-hosted Zoekt composition that materially improves company-wide source discovery while making repository/ref coverage, indexed SHA, staleness, corruption, truncation and canonical-verification requirements explicit in every result.

**Architecture:** Build a production-inert Mastermind discovery contract and local test facade in a disjoint `experiments/code_discovery` namespace. The host-side runner builds or receives exact-digest Zoekt binaries from pinned `sourcegraph/zoekt@5f833dde1bc4b1a8f99007617b4b721e44506c4f`, indexes curated immutable repository snapshots into disposable shards, and exercises only a tiny facade contract. Raw Zoekt administration and credentials are never model-facing.

**Tech Stack:** Python 3.11+, standard-library HTTP/JSON/subprocess/path/stat/hashlib, pytest, Git, exact pinned Go/Zoekt binaries supplied by the host-side experiment runner.

**Spec:** `research/MASTERMIND_CODE_INTELLIGENCE_FABRIC_F0_ARCHITECTURE_2026-08-30.md`

## Global Constraints

- Base from then-current protected Mastermind and re-pin the current Skillpack before START.
- Exact wave status is `DISPOSABLE FALSIFIER / PRODUCTION_INERT`; a successful local index is not a service or capability grant.
- Change only `experiments/code_discovery/**`, `tests/code_discovery/**`, `tests/fixtures/code_discovery/**` and `research/code_intelligence_fabric/Z0_*` unless Sol explicitly reconciles a new path.
- Do not modify `control_plane/**`, `config/**`, Operator Harness, production MCP configuration, service files, host state, repository credentials, Slack, Linear or Agent OS.
- No raw Zoekt admin/index/server command is exposed through the discovery tool schemas.
- No model-facing field accepts filesystem paths, repository URLs, credentials, executable paths, shard directories or index administration.
- Repositories and refs are selected from a host-owned reviewed manifest.
- Every search result names indexed ref/SHA, generated/observed times, health, coverage, freshness and truncation.
- An empty result is authoritative only for a healthy, fully covered, in-budget indexed ref with a completed non-truncated query.
- Index storage is disposable and rebuilt from exact Git/GitHub source.
- No network beyond loopback to the disposable local Zoekt process during Z0; repository acquisition occurs before the process is started and uses exact frozen snapshots.
- Every task ends with focused tests; final task emits no production endpoint, credential, profile or daemon.

---

### Task 1: Freeze the global discovery facade contract

**Files:**
- Create: `experiments/code_discovery/__init__.py`
- Create: `experiments/code_discovery/discovery_contract.py`
- Create: `tests/code_discovery/test_discovery_contract.py`

**Interfaces:**
- Produces: `DISCOVERY_TOOL_SCHEMAS`
- Produces: `validate_discovery_request(tool: str, arguments: Mapping[str, object]) -> DiscoveryRequest`
- Produces: `discovery_tool_schema_digest() -> str`
- Produces immutable result types `RepositoryIndexStatus`, `CodeMatch`, `SearchResult`

Exact model-facing tool census:

```text
search_code
list_repositories
index_status
```

`search_code` fields are exactly:

```text
query              required bounded string, 1..512 bytes
repositories       optional list of reviewed logical repository IDs, max 12
path_prefixes      optional repository-relative prefixes, max 12
languages          optional closed normalized language labels, max 12
refs               optional reviewed logical ref labels, max 12
case_sensitive     boolean
regex              boolean
limit              integer 1..100
context_lines      integer 0..8
```

No field may contain a URL, absolute path, credentials, index/shard directory, command, executable, host or port.

- [ ] **Step 1: Write failing schema tests**

Assert closed schemas, exact census, no administrative terms, bounded list cardinality and strict repository/ref values resolved only from a host-owned manifest.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest tests/code_discovery/test_discovery_contract.py -q
```

Expected: missing module failure.

- [ ] **Step 3: Implement canonical schemas and validation**

Reject unknown properties, NUL/control characters, path traversal, regex longer than 256 bytes, unsupported regex constructs defined by Z0 policy, limit above 100 and context above 8. Canonical JSON uses sorted compact ASCII encoding with `allow_nan=False`.

- [ ] **Step 4: Mutation check**

Add `index_path` and `repository_url` to a temporary schema and prove tests fail; revert and rerun green.

- [ ] **Step 5: Commit**

```bash
git add experiments/code_discovery/__init__.py experiments/code_discovery/discovery_contract.py tests/code_discovery/test_discovery_contract.py
git commit -m "test(codeintel): freeze global discovery contract"
```

### Task 2: Define the reviewed repository/ref/path manifest

**Files:**
- Create: `experiments/code_discovery/index_manifest.py`
- Create: `tests/code_discovery/test_index_manifest.py`
- Create: `tests/fixtures/code_discovery/manifest.json`

**Interfaces:**
- Produces: `RepositorySpec`
- Produces: `IndexManifest`
- Produces: `load_index_manifest(path: Path) -> IndexManifest`
- Produces: `material_source_manifest_digest(manifest: IndexManifest) -> str`

`RepositorySpec` fields are exactly:

```text
repository_id
repository_name
source_snapshot_root
ref_label
commit_sha
included_prefixes
excluded_globs
source_tree_digest
```

The production-facing logical manifest will not contain `source_snapshot_root`; Z0 keeps that host-only field in the runner projection.

- [ ] **Step 1: Write manifest validation tests**

Cover duplicate logical IDs, duplicate repository name/ref combinations, same repository name in different roots, invalid SHA, symlink source root, mutable/dirty source snapshot, included/excluded overlap, absolute glob, traversal and unbounded path counts.

- [ ] **Step 2: Encode the initial policy**

Seed logical entries for:

```text
mastermind/master
mastermind-terminal/master
macro/main
```

For Macro, include source-bearing paths such as `engine/**`, `lib/**`, `scripts/**`, `tests/**`, `agentos/**`, `.github/workflows/**`, `docs/**`, `research/**`, `config/**` and actual application/source roots observed at START. Exclude `site/**`, most `data/**`, content-addressed archives, rendered outputs, binaries, caches and vendored dependency directories. A path absent at the exact snapshot is omitted rather than fabricated.

- [ ] **Step 3: Implement deterministic materialization**

Require exact regular-file Git snapshots with no untracked files and record a sorted source-tree digest. Copy/link behavior is forbidden; the Z0 runner reads immutable disposable checkouts directly and writes shards elsewhere.

- [ ] **Step 4: Prove duplicate-name safety**

Construct two fixtures with the same repository basename and different logical IDs. The manifest must keep them distinct and generate disjoint shard namespaces; name-only identity fails.

- [ ] **Step 5: Commit**

```bash
git add experiments/code_discovery/index_manifest.py tests/code_discovery/test_index_manifest.py tests/fixtures/code_discovery/manifest.json
git commit -m "feat(codeintel): add reviewed discovery index manifest"
```

### Task 3: Launch exact pinned Zoekt processes under a disposable host runner

**Files:**
- Create: `experiments/code_discovery/processes.py`
- Create: `tests/code_discovery/test_processes.py`

**Interfaces:**
- Produces: `ExecutableSpec(path: Path, sha256: str, source_commit: str)`
- Produces: `ZoektProcessSet`
- Produces: `ZoektProcessSet.build_indexes(manifest: IndexManifest) -> tuple[RepositoryIndexStatus, ...]`
- Produces: `ZoektProcessSet.start_search() -> LoopbackEndpoint`
- Produces: `ZoektProcessSet.close() -> None`

- [ ] **Step 1: Write subprocess security/lifecycle tests**

Require exact digest verification before and after launch, `shell=False`, a closed environment, loopback-only listener, disposable external shard/log directories, bounded stdout/stderr, startup timeout, child-exit detection and idempotent cleanup. Refuse PATH-only executable resolution, symlink binaries, mutable world/group-writable binaries, non-loopback bind and inherited credentials.

- [ ] **Step 2: Inspect pinned upstream command contracts**

At exact `sourcegraph/zoekt@5f833dde1bc4b1a8f99007617b4b721e44506c4f`, freeze the required `zoekt-git-index` and `zoekt-webserver` argv into test fixtures. Record the source commit and built binary digests. Do not use a release alias or floating container tag.

- [ ] **Step 3: Implement one repository/ref per logical shard namespace**

Build each manifest row independently so one failure cannot silently erase another repository. After indexing, enumerate shard metadata and verify repository logical ID, ref, SHA and source-tree digest against the manifest before serving.

- [ ] **Step 4: Add cleanup and crash tests**

Kill the search process mid-query and require typed `ZOEKT_PROCESS_EXITED`. Leave a stale shard directory from a prior manifest and require refusal until explicitly discarded by the host runner; do not silently merge generations.

- [ ] **Step 5: Commit**

```bash
git add experiments/code_discovery/processes.py tests/code_discovery/test_processes.py
git commit -m "feat(codeintel): add disposable pinned Zoekt runner"
```

### Task 4: Implement the internal Zoekt client and stable discovery facade

**Files:**
- Create: `experiments/code_discovery/zoekt_client.py`
- Create: `experiments/code_discovery/discovery_facade.py`
- Create: `tests/code_discovery/test_zoekt_client.py`
- Create: `tests/code_discovery/test_discovery_facade.py`

**Interfaces:**
- Produces: `ZoektClient.search(...) -> RawZoektResult`
- Produces: `DiscoveryFacade(manifest, statuses, client, freshness_budget)`
- Produces: `DiscoveryFacade.call(request: DiscoveryRequest) -> Mapping[str, object]`

- [ ] **Step 1: Freeze the exact pinned Zoekt request/response fixture**

Read the pinned upstream HTTP/JSON search handler, capture one minimal valid request and response, and store a redacted deterministic fixture under `tests/fixtures/code_discovery/`. Tests must fail on an unknown response field that changes semantic interpretation, malformed JSON, non-200 status, oversized body, timeout or endpoint redirect.

- [ ] **Step 2: Implement bounded client behavior**

Loopback endpoint is host-injected and not model-facing. Maximum response is 8 MiB; one request is sent once; timeout/effect uncertainty is not retried. Normalize matching rows to repository-relative paths and bounded line context.

- [ ] **Step 3: Implement status-first facade behavior**

Before search, resolve every requested repository/ref against the reviewed manifest and current `RepositoryIndexStatus`. After search, attach exact status to every match and return a per-request coverage summary. Sort deterministically by `(repository_id, ref_label, path, line_start, line_end)` after preserving bounded engine score as non-authoritative metadata.

- [ ] **Step 4: Enforce negative-result authority**

A zero-match response may state `not_found_on_healthy_covered_ref` only when all requested rows are present, exact-SHA matched, health green, freshness within budget, query completed and no truncation occurred. Otherwise return `negative_result_authority: unavailable` plus exact reason set.

- [ ] **Step 5: Commit**

```bash
git add experiments/code_discovery/zoekt_client.py experiments/code_discovery/discovery_facade.py tests/code_discovery/test_zoekt_client.py tests/code_discovery/test_discovery_facade.py tests/fixtures/code_discovery
git commit -m "feat(codeintel): add governed Zoekt discovery facade"
```

### Task 5: Add corruption, staleness, omission and plausible-empty falsifiers

**Files:**
- Create: `experiments/code_discovery/health.py`
- Create: `tests/code_discovery/test_health_falsifiers.py`

**Interfaces:**
- Produces: `evaluate_index_health(...) -> RepositoryIndexStatus`
- Produces closed health values: `healthy`, `stale`, `coverage_unknown`, `index_failed`, `corrupt`, `process_unavailable`, `manifest_mismatch`

- [ ] **Step 1: Write malformed/corrupt shard tests**

Mutate or truncate a disposable shard, then exercise the pinned server/client. Even when the server returns HTTP 200 and zero results, the facade must refuse authoritative absence by consulting process/shard health and observed crash/error evidence.

- [ ] **Step 2: Reproduce duplicate repository-name risk**

Index two logical repositories with the same basename and different sentinels. Both must remain queryable by logical ID. If pinned Zoekt erases/collides despite separate namespaces, record `DUPLICATE_REPOSITORY_IDENTITY_UNSAFE` and require the facade/runner to isolate index directories or refuse that topology.

- [ ] **Step 3: Test freshness and omission**

Advance a source snapshot after indexing without refreshing; require `stale` with both indexed and current SHA. Omit a repository/ref from the served generation; require `coverage_unknown`, never empty success.

- [ ] **Step 4: Test huge/truncated queries**

Create more than 100 matches and require exact truncation plus unavailable negative authority. Reject regex/corpus work that exceeds the configured deadline rather than returning partial-looking success.

- [ ] **Step 5: Commit**

```bash
git add experiments/code_discovery/health.py tests/code_discovery/test_health_falsifiers.py
git commit -m "test(codeintel): add Zoekt health and absence falsifiers"
```

### Task 6: Measure initial path policy and search quality

**Files:**
- Create: `experiments/code_discovery/z0_benchmark.py`
- Create: `tests/code_discovery/test_z0_benchmark.py`
- Create: `research/code_intelligence_fabric/z0-path-policy.json`

**Interfaces:**
- Produces: per-repository source-file count, indexed bytes, shard bytes, build time, refresh time, query latency and answer-key recall.
- Consumes benchmark cases E1, X3, R3 and A1.

- [ ] **Step 1: Materialize exact answer-key subsets**

For each case, freeze exact repo/ref, critical paths, canonical owner/source law and expected query families before running Zoekt. Use Git/GitHub evidence, not PR titles alone.

- [ ] **Step 2: Run three Macro path-policy variants**

```text
P0  broad repository minus binaries/caches only
P1  initial source-bearing include policy from the architecture
P2  P1 plus each individually justified narrow data/config subtree
```

Measure relevant-path recall, false-positive burden, shard size, build/refresh latency and query latency. Select P1 or P2 only from case evidence; broad P0 cannot win solely by recall when false-positive/resource burden is materially worse.

- [ ] **Step 3: Record excluded-but-needed evidence**

When a critical answer-key file lies in an excluded subtree, record the exact case/path and smallest safe inclusion amendment. Do not add all `data/**` or `site/**` as a convenience fallback.

- [ ] **Step 4: Commit**

```bash
git add experiments/code_discovery/z0_benchmark.py tests/code_discovery/test_z0_benchmark.py research/code_intelligence_fabric/z0-path-policy.json
git commit -m "research(codeintel): measure Z0 path and search policy"
```

### Task 7: Publish the Z0 result and stop production-inert

**Files:**
- Create: `experiments/code_discovery/z0_runner.py`
- Create: `tests/code_discovery/test_z0_runner.py`
- Create: `research/code_intelligence_fabric/Z0_GLOBAL_DISCOVERY_FALSIFIER_RESULT.md`
- Create: `research/code_intelligence_fabric/z0-result.schema.json`

**Interfaces:**
- Produces one `mastermind.codeintel_z0_result.v1` JSON artifact and human-readable report.
- Decision enum: `ZOEKT_FACADE_ACCEPTED_FOR_CI3`, `ZOEKT_REQUIRES_ARCHITECTURE_REVISION`, `NO_SAFE_GLOBAL_INDEX`.

- [ ] **Step 1: Write deterministic report tests**

The report binds exact Mastermind/Macro/source snapshots, Zoekt source commit, binary digests, manifest/path-policy digests, service config digest, health-falsifier outcomes, benchmark measurements and resource observations.

- [ ] **Step 2: Implement the host-only runner CLI**

Host-only arguments are exact source snapshot roots, external scratch/index root, binary paths/digests and result path. They configure the experiment and never enter model-facing schemas. Refuse symlinks, dirty snapshots, digest mismatch, non-loopback server, floating source/ref or existing unrecognized shard generations.

- [ ] **Step 3: Run complete Z0 verification**

```bash
python3 -m pytest tests/code_discovery -q
python3 -m compileall -q experiments/code_discovery tests/code_discovery
python3 -m experiments.code_discovery.z0_runner ...
git diff --check
```

- [ ] **Step 4: Perform required mutations**

At minimum mutate one status path to bless stale zero results, one manifest identity to collapse duplicate names, one response to omit indexed SHA and one client to retry after timeout. Each mutation must fail a named test.

- [ ] **Step 5: Stop and return**

Return exact head, changed-file census, commands/results, result digest, resource envelope, selected path policy and typed failures. Do not add a production HTTPS/MCP service, repository credential, webhook, daemon, host deployment, registry profile or CI3 code.

- [ ] **Step 6: Commit**

```bash
git add experiments/code_discovery tests/code_discovery research/code_intelligence_fabric
git commit -m "research(codeintel): record Z0 global discovery decision"
```

## Z0 acceptance ruler

Z0 passes only when the exact pinned source/binaries and source snapshots are reproducible, global search improves E1/X3/A1 retrieval, negative-result authority fails closed under every R3 health defect, duplicate repository names cannot erase or blend indexes, freshness and indexed SHA are explicit, result size is bounded, credentials remain outside model context and measured resource cost is acceptable enough to propose CI3. `NO_SAFE_GLOBAL_INDEX` is a valid successful falsifier result and returns to Sol for architecture revision.