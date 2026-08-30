# Code Intelligence Fabric C0 Semantic Falsifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove or refuse one production-inert semantic backend composition that returns useful symbol/reference/implementation/diagnostic facts from the exact sealed worker worktree while exposing zero path selection, editing, shell, memory, project-switching or candidate-tree write capability.

**Architecture:** Build a backend-neutral in-process Mastermind facade and hostile two-worktree fixture under an isolated `experiments/code_intelligence` namespace. Compare a pinned hardened Serena v1.7.0 backend with a direct LSP backend through the same six-tool contract; bind both to a captured host-owned workspace seal and emit a content-addressed falsifier report. Do not touch production registry, Operator Harness, MCP configuration or host installation.

**Tech Stack:** Python 3.11+, standard-library JSON-RPC/subprocess/path/stat/hashlib, pytest, Git, pinned external Serena/LSP executables supplied only by the host-side experiment runner.

**Spec:** `research/MASTERMIND_CODE_INTELLIGENCE_FABRIC_F0_ARCHITECTURE_2026-08-30.md`

## Global Constraints

- Base from then-current protected Mastermind and re-pin the current Skillpack before START.
- Exact wave status is `DISPOSABLE FALSIFIER / PRODUCTION_INERT`; a successful spike is not a capability grant.
- Change only `experiments/code_intelligence/**`, `tests/code_intelligence/**`, `tests/fixtures/code_intelligence/**`, `research/code_intelligence_fabric/C0_SEMANTIC_FALSIFIER_RESULT.md` and `research/code_intelligence_fabric/c0-result.schema.json` unless Sol explicitly reconciles a new path.
- Do not modify `control_plane/**`, `config/**`, Operator Harness, App Server profiles, production MCP configuration, service files, host state, Slack, Linear or Agent OS.
- No model-facing argument may select a root, path, project, Attempt, Worker, session, endpoint, executable, environment or language-server command.
- External executable paths/digests are host-runner inputs and must never enter the facade tool schemas.
- Zero writes inside either candidate worktree; all caches/config/metadata live under an experiment-created external scratch root.
- No network access.
- Serena candidate is exactly v1.7.0 / source commit `949a27ef1e5fda1a6e7b561e777bcece345c6ffd`.
- Candidate S is refused rather than patched when repository-controlled configuration cannot be prevented from changing tools, prompts, commands or root behavior.
- Every task ends with focused tests; the final task runs the complete C0 matrix and emits no production profile.

---

### Task 1: Freeze the semantic facade contract

**Files:**
- Create: `experiments/code_intelligence/__init__.py`
- Create: `experiments/code_intelligence/semantic_contract.py`
- Create: `tests/code_intelligence/test_semantic_contract.py`

**Interfaces:**
- Produces: `SEMANTIC_TOOL_SCHEMAS: Mapping[str, Mapping[str, object]]`
- Produces: `SemanticRequest(tool: str, arguments: Mapping[str, object])`
- Produces: `SemanticResponse(tool: str, workspace_binding_digest: str, backend_digest: str, payload: Mapping[str, object])`
- Produces: `validate_semantic_request(tool: str, arguments: Mapping[str, object]) -> SemanticRequest`
- Produces: `semantic_tool_schema_digest() -> str`

- [ ] **Step 1: Write failing closed-schema tests**

Assert the exact tool census is:

```python
{
    "workspace_status",
    "symbol_overview",
    "find_symbol",
    "find_references",
    "find_implementations",
    "diagnostics",
}
```

Assert every input schema has `additionalProperties: false`. Assert no schema field contains any of these tokens after lowercase normalization:

```text
root path project attempt worker session endpoint command executable cwd env memory edit shell
```

Allowed location fields are bounded repository-relative `relative_file` and bounded line/column positions only; they never change the workspace root.

- [ ] **Step 2: Run tests and observe RED**

Run:

```bash
python3 -m pytest tests/code_intelligence/test_semantic_contract.py -q
```

Expected: collection fails because `experiments.code_intelligence.semantic_contract` does not exist.

- [ ] **Step 3: Implement canonical JSON, schemas and validators**

Use sorted-key, compact, ASCII, `allow_nan=False` JSON. Reject unknown tool names, unknown arguments, absolute paths, `..` path traversal, NUL, arguments longer than 4 KiB and requested result limits above 100. `workspace_status` accepts no arguments.

- [ ] **Step 4: Run focused GREEN and mutation checks**

Temporarily add `project_path` to one schema and prove the hostile-field test fails; revert and rerun to green.

- [ ] **Step 5: Commit**

```bash
git add experiments/code_intelligence/__init__.py experiments/code_intelligence/semantic_contract.py tests/code_intelligence/test_semantic_contract.py
git commit -m "test(codeintel): freeze semantic facade contract"
```

### Task 2: Capture exact workspace identity and enforce zero candidate writes

**Files:**
- Create: `experiments/code_intelligence/workspace_seal.py`
- Create: `tests/code_intelligence/test_workspace_seal.py`

**Interfaces:**
- Produces: immutable `WorkspaceSeal`
- Produces: `capture_workspace_seal(root: Path) -> WorkspaceSeal`
- Produces: `verify_workspace_seal(expected: WorkspaceSeal) -> None`
- Produces: `candidate_tree_fingerprint(root: Path) -> str`
- Produces: `create_external_scratch(*, parent: Path, seal: WorkspaceSeal) -> Path`

`WorkspaceSeal` fields are exactly:

```text
resolved_root
device
inode
uid
gid
git_common_dir
git_dir
head_sha
status_porcelain_v2_sha256
candidate_tree_sha256
```

- [ ] **Step 1: Write hostile workspace tests**

Cover symlink root, symlink ancestor, moved root, replaced inode, changed HEAD, dirty-file change, untracked-file change, Git worktree root mismatch and scratch creation inside the candidate tree.

Create two simultaneous fixture worktrees with the same package/symbol names but sentinel values `WORKTREE_ALPHA_ONLY` and `WORKTREE_BETA_ONLY`.

- [ ] **Step 2: Run tests and observe RED**

```bash
python3 -m pytest tests/code_intelligence/test_workspace_seal.py -q
```

- [ ] **Step 3: Implement the seal with fixed Git argv**

Use `Path.resolve(strict=True)`, `os.lstat`, owner/device/inode checks and fixed-argv `git -C <sealed-root> ...` subprocess calls with `shell=False`. Hash a sorted bounded manifest of repository-relative regular-file identity and bytes, excluding only `.git` indirection metadata; refuse special files and filesystem traversal outside the root.

- [ ] **Step 4: Prove zero-write detection**

Capture before/after seals around a fake backend that writes `.semantic-cache` into the worktree; require a typed `CANDIDATE_TREE_WRITE_DETECTED` refusal. The same fake backend writing under the external scratch root must pass.

- [ ] **Step 5: Commit**

```bash
git add experiments/code_intelligence/workspace_seal.py tests/code_intelligence/test_workspace_seal.py
git commit -m "feat(codeintel): add exact workspace seal falsifier"
```

### Task 3: Define the backend protocol and deterministic fixtures

**Files:**
- Create: `experiments/code_intelligence/backend.py`
- Create: `tests/fixtures/code_intelligence/python_sample/src/sample/producer.py`
- Create: `tests/fixtures/code_intelligence/python_sample/src/sample/consumer.py`
- Create: `tests/fixtures/code_intelligence/python_sample/tests/test_consumer.py`
- Create: `tests/code_intelligence/test_backend_contract.py`

**Interfaces:**

```python
class SemanticBackend(Protocol):
    @property
    def identity(self) -> BackendIdentity: ...
    def start(self, *, seal: WorkspaceSeal, scratch: Path) -> None: ...
    def workspace_status(self) -> Mapping[str, object]: ...
    def symbol_overview(self, *, relative_file: str | None, query: str | None, limit: int) -> Mapping[str, object]: ...
    def find_symbol(self, *, name: str, relative_file: str | None, limit: int) -> Mapping[str, object]: ...
    def find_references(self, *, name: str, relative_file: str | None, limit: int) -> Mapping[str, object]: ...
    def find_implementations(self, *, name: str, relative_file: str | None, limit: int) -> Mapping[str, object]: ...
    def diagnostics(self, *, relative_file: str | None, limit: int) -> Mapping[str, object]: ...
    def close(self) -> None: ...
```

`BackendIdentity` contains exact backend kind, source version/commit, executable SHA-256, language-server identity/digest set and normalized configuration digest.

- [ ] **Step 1: Create the fixture answer key**

The producer exposes a protocol/interface, concrete implementation, wrapper and deliberately similar dead sibling. The consumer imports only the live wrapper. The test imports the consumer. Add one deterministic undefined-name/type diagnostic.

- [ ] **Step 2: Write conformance tests**

A `FakeBackend` must satisfy all methods, preserve bounded repository-relative locations and return a stable identity. Refuse payloads with absolute paths, raw environment, executable paths, secrets or more than 100 rows.

- [ ] **Step 3: Run RED, implement protocol helpers, rerun GREEN**

```bash
python3 -m pytest tests/code_intelligence/test_backend_contract.py -q
```

- [ ] **Step 4: Commit**

```bash
git add experiments/code_intelligence/backend.py tests/fixtures/code_intelligence/python_sample tests/code_intelligence/test_backend_contract.py
git commit -m "test(codeintel): add semantic backend contract fixtures"
```

### Task 4: Implement the direct LSP candidate

**Files:**
- Create: `experiments/code_intelligence/jsonrpc_stdio.py`
- Create: `experiments/code_intelligence/lsp_backend.py`
- Create: `tests/code_intelligence/test_jsonrpc_stdio.py`
- Create: `tests/code_intelligence/test_lsp_backend.py`

**Interfaces:**
- Produces: `JsonRpcStdioClient`
- Produces: `DirectLspBackend(SemanticBackend)`
- Consumes: one host-injected immutable `ExecutableSpec(path: Path, sha256: str, argv_suffix: tuple[str, ...])`

- [ ] **Step 1: Write framed JSON-RPC tests**

Cover split headers/bodies, multiple messages in one read, malformed length, oversized frame, unsolicited notifications, timeout, child exit, cancellation and stderr bounding. The client must use `shell=False`, a closed environment and exact executable digest verification before and after launch.

- [ ] **Step 2: Implement the minimal stdio JSON-RPC client**

Support request IDs, notifications and a bounded notification queue. Maximum inbound frame is 4 MiB; maximum stderr retained is 32 KiB. No network or shell fallback.

- [ ] **Step 3: Write LSP integration tests against an injected test server**

The fake server must record `initialize.rootUri`, assert it equals the sealed root, and implement `textDocument/documentSymbol`, `workspace/symbol`, `textDocument/references`, `textDocument/implementation` and diagnostics notifications. Attempts to send `workspace/didChangeWorkspaceFolders`, execute command or change root must fail.

- [ ] **Step 4: Implement LSP mappings**

Open fixture documents read-only, translate exact LSP positions to bounded facade rows, deduplicate and sort by `(relative_file, start_line, start_character, symbol)`. Do not expose arbitrary LSP methods.

- [ ] **Step 5: Run with one real pinned Python language server**

The worker selects one available open-source Python LSP by exact release/commit, records its binary/source digest in the falsifier report, and runs the fixture answer key. Absence of a safely pin-able server is a truthful `LSP_BINARY_UNAVAILABLE`, not permission to download latest or use PATH ambiently.

- [ ] **Step 6: Commit**

```bash
git add experiments/code_intelligence/jsonrpc_stdio.py experiments/code_intelligence/lsp_backend.py tests/code_intelligence/test_jsonrpc_stdio.py tests/code_intelligence/test_lsp_backend.py
git commit -m "feat(codeintel): add direct LSP semantic candidate"
```

### Task 5: Implement the pinned Serena candidate as an internal backend only

**Files:**
- Create: `experiments/code_intelligence/serena_backend.py`
- Create: `tests/code_intelligence/test_serena_backend.py`

**Interfaces:**
- Produces: `SerenaBackend(SemanticBackend)`
- Consumes: exact pinned Serena source/bundle `949a27ef1e5fda1a6e7b561e777bcece345c6ffd`
- Reuses: `JsonRpcStdioClient`, `WorkspaceSeal`, external scratch

- [ ] **Step 1: Write tool-census and configuration-injection tests**

Require the internal client to call only the upstream tools needed to implement the six facade tools. Create hostile repository `.serena` files that attempt to add prompts, modes, editing tools, a custom language-server command and another project root. Any change in tool census, executable command, prompt material, root or result is `SERENA_REPOSITORY_CONFIG_INFLUENCE` and Candidate S fails.

- [ ] **Step 2: Write candidate-write and project-switch tests**

Reject dashboard startup, memory writes, onboarding state, project activation/switch calls and `.serena` metadata in the worktree. Search the full before/after tree fingerprint.

- [ ] **Step 3: Implement the smallest adapter**

Launch the pinned local Serena bundle over stdio with dashboard disabled, read-only intent, explicit tool exclusion/fixed tool set when supported, a closed environment and external scratch configuration. Record both advertised and callable upstream tool censuses. Map only bounded results into the facade response.

- [ ] **Step 4: Apply the fail-closed decision**

When the exact pinned version cannot prevent repository configuration from influencing behavior or cannot keep metadata outside the candidate tree, emit a complete refusal report and mark Candidate S `REJECTED_BY_C0`. Do not patch/fork Serena inside this wave.

- [ ] **Step 5: Commit**

```bash
git add experiments/code_intelligence/serena_backend.py tests/code_intelligence/test_serena_backend.py
git commit -m "test(codeintel): falsify pinned Serena backend"
```

### Task 6: Build the stable facade dispatcher and pre-turn binding receipt

**Files:**
- Create: `experiments/code_intelligence/semantic_facade.py`
- Create: `tests/code_intelligence/test_semantic_facade.py`

**Interfaces:**
- Produces: `SemanticFacade(seal: WorkspaceSeal, backend: SemanticBackend, scratch: Path)`
- Produces: `SemanticFacade.call(request: SemanticRequest) -> SemanticResponse`
- Produces: `SemanticFacade.binding_receipt() -> Mapping[str, object]`

- [ ] **Step 1: Write exact binding tests**

The receipt must bind workspace seal digest, facade source digest, semantic schema digest, backend identity digest, language-server digest set, startup time and zero-write before/after fingerprints. Tool calls are refused until the receipt is validated against the expected seal.

- [ ] **Step 2: Implement one-call validation and post-call revalidation**

Validate request, verify seal, call one backend method, normalize/bound response, verify seal again, then return. A crash or timeout returns one typed failure and is never automatically resent.

- [ ] **Step 3: Prove two-worktree isolation**

Run two facade instances concurrently. Alpha requests must never return `WORKTREE_BETA_ONLY`; Beta requests must never return `WORKTREE_ALPHA_ONLY`. Try absolute path, `../`, symlink and backend project-switch mutations.

- [ ] **Step 4: Commit**

```bash
git add experiments/code_intelligence/semantic_facade.py tests/code_intelligence/test_semantic_facade.py
git commit -m "feat(codeintel): add sealed semantic facade falsifier"
```

### Task 7: Run real C0 benchmark subset and publish the decision report

**Files:**
- Create: `experiments/code_intelligence/c0_runner.py`
- Create: `tests/code_intelligence/test_c0_runner.py`
- Create: `research/code_intelligence_fabric/C0_SEMANTIC_FALSIFIER_RESULT.md`
- Create: `research/code_intelligence_fabric/c0-result.schema.json`

**Interfaces:**
- Produces one `mastermind.codeintel_c0_result.v1` JSON artifact and human-readable report.
- Consumes benchmark cases O1, W1 and A3 plus the deterministic fixture.

- [ ] **Step 1: Write report-schema and deterministic rerun tests**

The report contains exact source pins, executable digests, tool censuses, per-case recall/latency, resource observations, all hostile test outcomes, candidate-tree before/after digests and one decision: `SERENA`, `DIRECT_LSP`, or `NO_SAFE_BACKEND`.

- [ ] **Step 2: Implement the runner**

The CLI accepts host-only `--workspace`, `--scratch-parent`, `--serena-bundle`, `--serena-sha256`, `--lsp-binary` and `--lsp-sha256`. Those values configure the experiment process only and never appear in model-facing tool schemas. Refuse symlinks, digest mismatch, network-required setup and missing exact source pins.

- [ ] **Step 3: Run the complete C0 matrix**

```bash
python3 -m pytest tests/code_intelligence -q
python3 -m compileall -q experiments/code_intelligence tests/code_intelligence
python3 -m experiments.code_intelligence.c0_runner --workspace <disposable-worktree> --scratch-parent <external-scratch> ...
git diff --check
```

- [ ] **Step 4: Perform mutation/falsifier verification**

At minimum mutate one schema to add a root field, one backend to write the candidate tree, one binding check to accept Beta under Alpha and one executable digest. Each mutation must fail a named test.

- [ ] **Step 5: Stop and return**

Return exact head, changed-file census, commands/results, C0 result digest, selected/refused backend, discovered upstream constraints and CI. Do not add a production MCP server, registry transport, capability profile, service, host install or CI1 code.

- [ ] **Step 6: Commit**

```bash
git add experiments/code_intelligence tests/code_intelligence research/code_intelligence_fabric
git commit -m "research(codeintel): record C0 semantic backend decision"
```

## C0 acceptance ruler

C0 passes only when one backend is useful on O1/W1/A3, exact tool and executable identity are recorded, zero candidate writes are proven, hostile repository configuration cannot widen behavior, two worktrees remain isolated, crash/restart behavior is explicit, and every result is reproducible from an exact source manifest. `NO_SAFE_BACKEND` is a successful falsifier result when honestly proven; it returns to Sol for architecture revision rather than weakening capability law.