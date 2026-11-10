# Sol Capability Fabric Package Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:test-driven-development` and either `superpowers:subagent-driven-development` or `superpowers:executing-plans`. Re-pin the current protected Mastermind Skillpack before every modifying phase. This plan uses checkbox (`- [ ]`) steps and grants no implementation START by itself.

**Goal:** Add a backward-compatible `ExecutionCapabilityRegistry` v4 contract that verifies one exact immutable `mastermind-operator` source-package generation and compiles its four effective Skill closure digests into the existing Operator Harness capability identity, while the checked-in default policy remains byte/semantically v3 and no provider route or runtime state changes.

**Architecture:** A focused pure package module owns canonical file/closure digesting and no-follow source verification; the existing registry remains the only capability-policy owner and gains an opt-in v4 parser/compiler. V3 loading and every current digest remain exact. A repository fixture exercises the protected seven-file package and four Skill grants; CAP-S1 later migrates the default policy and supplies the real Codex consumer.

**Tech Stack:** Python 3.11+, frozen dataclasses, `pathlib`, `os.open`/`dir_fd`/`O_NOFOLLOW`, SHA-256, canonical JSON, existing `ExecutionCapabilityRegistry`, existing OHF `CapabilityIdentity`, pytest, GitHub Actions.

**Specs:**
- `docs/superpowers/specs/2026-09-01-sol-capability-fabric-package-generation-design.md`
- `docs/superpowers/specs/2026-09-01-sol-capability-fabric-package-content-digest-correction.md`
- protected AOC-F0 source under merge `187490f3d5676adf7a249d69afacedd00b3efcec`

## Global constraints

- Executive OS remains the sole Job / Attempt / Worker / Event / retry / effect-reconciliation authority.
- `ExecutionCapabilityRegistry` remains the sole execution-capability grant and policy-digest owner.
- Do not create a plugin database, package registry service, package lifecycle table, marketplace client, auto-sync path, provider-specific broker, session store, route, scheduler, watcher or host allocator.
- BSC-P1 owns the protected package bytes. BSC-U1 remains the Business app/import/workspace-enrollment owner.
- Sol Capability Fabric owns future Sol-facing capability status; SCF-PKG1 creates no MCP app/tool.
- Professional Practice Fabric owns professional method/admission/evaluation. A loaded Skill is not competence proof.
- Default `config/executive_agent_capabilities.json` remains schema v3 and byte-identical in this wave.
- `config/executive_worker_routes.json`, `control_plane/executive_autonomy.py`, installed service files and host receipts are protected no-edit surfaces.
- V3 behavior and digests must remain exact; v4 is opt-in through an explicit fixture or later default migration.
- Runtime full-plugin grants remain unavailable. V4 package entries are immutable **source-package generations**, not provider plugin installation authority.
- No provider process, App Server, model turn, browser, MCP sidecar, package manager or external network action occurs in SCF-PKG1.
- No credential bytes, provider-home paths, OAuth identifiers, Business workspace IDs, hostnames or session handles may enter policy, digest projections, errors or tests.
- A source verification failure is `CapabilityPolicyError` at the public registry boundary and never a fail-open warning.
- Green source CI proves only `BUILT_NOT_PROVEN / PRODUCTION_INERT`.

---

## File structure

### New production files

- `control_plane/executive_capability_packages.py`
  - pure immutable package/Skill contract types;
  - canonical package-content and effective-closure digesting;
  - closed path/row validation;
  - no-follow, bounded local source verification;
  - internal `CapabilityPackageError` converted by the registry to `CapabilityPolicyError`.

### Modified production files

- `control_plane/executive_agent_capabilities.py`
  - v3/v4 schema dispatch;
  - exact package-generation parsing and verification through the new module;
  - v4 Skill capability-ID resolution;
  - resolved Skill grants on `ExecutionCapabilityProfile`;
  - existing OHF `CapabilityIdentity.skill_content_digest` compilation;
  - v3 compatibility and public exports.

### New test fixtures

- `tests/fixtures/executive_agent_capabilities_v4_mastermind_operator.json`
  - complete v4 fixture based on current v3 policy;
  - exact protected package generation;
  - four exact Skill grants;
  - one read-only fixture profile requiring the complete four-Skill set;
  - `production_armed=false`;
  - no runtime plugin grant and no route.

### New tests

- `tests/test_executive_capability_packages.py`
  - pure canonical digest and hostile-filesystem verification matrix.

- `tests/test_executive_agent_capabilities_v4.py`
  - v4 parser/compiler/digest/revocation/profile tests against the actual protected package source.

### Modified tests

- `tests/test_executive_agent_capabilities.py`
  - pin v3 compatibility constants and unchanged current default policy/profile digests;
  - preserve every existing assertion.

### Protected no-edit files

- `config/executive_agent_capabilities.json`
- `config/executive_worker_routes.json`
- `control_plane/executive_autonomy.py`
- `control_plane/operator_harness_contract.py`
- `control_plane/codex_operator_adapter.py`
- `scripts/executive_os_phase1c_worker.py`
- all plugin package source files
- all Browser/Capacity/MH1/Business/PPF runtime files

---

## Exact public interfaces

### `control_plane/executive_capability_packages.py`

```python
CAPABILITY_PACKAGE_CONTENT_SCHEMA = "mastermind.capability_package_content/v1"
EFFECTIVE_SKILL_CLOSURE_SCHEMA = "mastermind.effective_skill_closure/v1"
PACKAGE_KIND_SKILLS_ONLY_SOURCE = "skills-only-source"
PACKAGE_SOURCE_STATE_PROTECTED = "SOURCE_PROTECTED"
MAX_PACKAGE_FILES = 64
MAX_PACKAGE_FILE_BYTES = 1024 * 1024
MAX_PACKAGE_TOTAL_BYTES = 8 * 1024 * 1024
MAX_SKILLS_PER_PACKAGE = 32
MAX_CLOSURE_FILES = 32

class CapabilityPackageError(ValueError): ...

@dataclasses.dataclass(frozen=True)
class CapabilityPackageFile:
    relative_path: str
    sha256: str
    byte_length: int
    executable: bool

@dataclasses.dataclass(frozen=True)
class EffectiveSkillGrant:
    capability_id: str
    runtime_name: str
    entrypoint_path: str
    closure_paths: tuple[str, ...]
    skill_content_digest: str
    package_capability_id: str
    package_generation: str
    package_grant_digest: str
    grant_digest: str

@dataclasses.dataclass(frozen=True)
class CapabilityPackageGeneration:
    capability_id: str
    kind: str
    repository: str
    source_commit: str
    source_tree_sha: str
    package_root: str
    manifest_path: str
    generation: str
    source_state: str
    revoked: bool
    package_content_digest: str
    files: tuple[CapabilityPackageFile, ...]
    skills: tuple[EffectiveSkillGrant, ...]
    required_app_references: tuple[str, ...]
    grant_digest: str

@dataclasses.dataclass(frozen=True)
class VerifiedCapabilityPackage:
    capability_id: str
    generation: str
    package_root: str
    package_content_digest: str
    file_count: int
    total_bytes: int
    skill_content_digests: tuple[tuple[str, str], ...]


def capability_package_content_digest(
    files: tuple[CapabilityPackageFile, ...],
) -> str: ...


def effective_skill_content_digest(
    *,
    runtime_name: str,
    entrypoint_path: str,
    closure_files: tuple[CapabilityPackageFile, ...],
) -> str: ...


def build_capability_package_generation(
    *,
    capability_id: str,
    raw: Mapping[str, object],
) -> CapabilityPackageGeneration: ...


def verify_capability_package_source(
    source_root: Path,
    generation: CapabilityPackageGeneration,
) -> VerifiedCapabilityPackage: ...
```

The module exports data/verification only. It does not load policy files, resolve profiles, start processes, query GitHub, invoke Git, call providers or mutate the filesystem.

### `control_plane/executive_agent_capabilities.py`

```python
CAPABILITY_POLICY_SCHEMA_V3 = "mastermind.executive_agent_capabilities/v3"
CAPABILITY_POLICY_SCHEMA_V4 = "mastermind.executive_agent_capabilities/v4"
CAPABILITY_POLICY_SCHEMA = CAPABILITY_POLICY_SCHEMA_V3
DEFAULT_CAPABILITY_SOURCE_ROOT = Path(__file__).resolve().parent.parent

@dataclasses.dataclass(frozen=True)
class ExecutionCapabilityProfile:
    ...
    skills: tuple[str, ...]                  # provider-runtime names, compatibility view
    skill_grants: tuple[EffectiveSkillGrant, ...]
    ...

@dataclasses.dataclass(frozen=True)
class ExecutionCapabilityRegistry:
    schema_version: str
    ...
    plugins: Mapping[str, CapabilityPackageGeneration]
    ...

    @classmethod
    def load(
        cls,
        path: str | Path | None = None,
        *,
        source_root: str | Path | None = None,
    ) -> "ExecutionCapabilityRegistry": ...
```

V3 returns `plugins={}` and `profile.skill_grants=()`. V4 verifies every package against `source_root`, resolves Skill capability IDs, and keeps `profile.skills` as exact runtime names.

---

# Task 1: Add pure canonical package and effective-closure digest contracts

**Files:**
- Create: `control_plane/executive_capability_packages.py`
- Create: `tests/test_executive_capability_packages.py`

**Produces:** the exact immutable types and canonical digest functions used by every later task.

- [ ] **Step 1: Write RED tests for canonical package rows**

Create tests with two temporary package rows and assert:

```python
files = (
    CapabilityPackageFile(
        relative_path="references/boundary.md",
        sha256="a" * 64,
        byte_length=7,
        executable=False,
    ),
    CapabilityPackageFile(
        relative_path="skills/receive/SKILL.md",
        sha256="b" * 64,
        byte_length=11,
        executable=False,
    ),
)
assert capability_package_content_digest(files) == EXPECTED_FIXED_DIGEST
```

The test computes `EXPECTED_FIXED_DIGEST` once from the frozen literal projection and pins it as a literal. It also asserts:

```text
absolute source root is excluded
row input order is normalized by relative path
changed path changes digest
changed byte length changes digest
changed SHA-256 changes digest
changed executable flag changes digest
schema token changes digest
```

- [ ] **Step 2: Write RED tests for effective Skill closure**

Pin the exact projection:

```python
{
    "schema_version": "mastermind.effective_skill_closure/v1",
    "skill_name": "receive-commission",
    "entrypoint_path": "skills/receive-commission/SKILL.md",
    "files": [...sorted exact rows...],
}
```

Assert entrypoint and shared-reference movement changes the digest while an unrelated package row not supplied to the closure does not.

- [ ] **Step 3: Write RED validation tests**

Require `CapabilityPackageError` for:

```text
blank or invalid identifiers
absolute paths
`.` / `..` components
backslashes
NUL/control characters
empty path
non-lowercase SHA-256
zero/negative/oversized byte length
non-bool executable
unsorted or duplicate normalized file rows
case-fold collisions
more than 64 package files
more than 8 MiB total bytes
closure missing entrypoint
closure containing unknown path
closure duplicate or unsorted paths
more than 32 closure files
unsupported package kind/state
non-40-hex source commit/tree
non-empty required_app_references
```

- [ ] **Step 4: Run RED**

```bash
python3 -m pytest -q -p no:cacheprovider \
  tests/test_executive_capability_packages.py
```

Expected: import failure.

- [ ] **Step 5: Implement canonical dataclasses and digest functions**

Implementation rules:

```text
canonical JSON: sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
package rows: sorted by UTF-8/POSIX relative path
closure rows: exact subset in closure-path order after canonical sort
no host path, uid, gid, inode, mtime or Git SHA in content/closure digest
```

`build_capability_package_generation()` validates exact raw keys and computes every digest rather than trusting an unchecked declared result. A declared package or Skill digest must equal the computed value or construction fails.

- [ ] **Step 6: Run GREEN**

```bash
python3 -m pytest -q -p no:cacheprovider \
  tests/test_executive_capability_packages.py
```

- [ ] **Step 7: Commit**

```bash
git add \
  control_plane/executive_capability_packages.py \
  tests/test_executive_capability_packages.py
git commit -m "feat(scf): define immutable capability package contracts"
```

---

# Task 2: Implement bounded no-follow local source verification

**Files:**
- Modify: `control_plane/executive_capability_packages.py`
- Modify: `tests/test_executive_capability_packages.py`

**Consumes:** Task 1 types and digest functions.

**Produces:** `verify_capability_package_source()` with a complete hostile-filesystem matrix.

- [ ] **Step 1: Write RED happy-path source verification test**

Create a temporary source root with:

```text
plugins/example/.codex-plugin/plugin.json
plugins/example/references/boundary.md
plugins/example/skills/receive/SKILL.md
```

Build a matching generation and assert the receipt contains only bounded non-secret identity facts:

```python
assert receipt.package_content_digest == generation.package_content_digest
assert receipt.file_count == 3
assert receipt.total_bytes == sum(row.byte_length for row in generation.files)
assert receipt.skill_content_digests == (
    ("example.receive.v1", generation.skills[0].skill_content_digest),
)
```

- [ ] **Step 2: Write RED hostile-filesystem tests**

Use real filesystem mutations and require refusal for:

```text
source root symlink
package root symlink
symlink in package path component
symlinked file
hardlinked file with st_nlink > 1
FIFO
UNIX socket when platform supports it
extra regular file
missing regular file
changed bytes with same size
changed size
executable-bit drift
case-fold collision declared in policy
source file replaced between first and second stat
package total grows beyond bound
unreadable source file
source root does not exist
package path escapes source root
```

For race testing, inject one test-only `before_final_stat` callback or a private helper seam rather than adding sleeps. The public API remains the signature frozen above.

- [ ] **Step 3: Run RED**

```bash
python3 -m pytest -q -p no:cacheprovider \
  tests/test_executive_capability_packages.py
```

Expected: verification tests fail because the function is absent or incomplete.

- [ ] **Step 4: Implement descriptor-relative verification**

Use reviewed host primitives:

```python
O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
```

If either primitive is unavailable, exact source verification refuses rather than silently following paths.

Algorithm:

```text
lstat every lexical source/package component; reject symlink
open source root and walk package-root directories with openat + O_NOFOLLOW + O_DIRECTORY
enumerate package tree without following symlinks
normalize each relative path and require exact declared set equality
open each file with O_NOFOLLOW relative to retained package directory
require regular file, nlink=1, bounded size and exact executable bit
stream SHA-256 in <=64 KiB chunks
retain first stat; final fstat must preserve dev/inode/mode/nlink/uid/gid/size/mtime_ns/ctime_ns
recompute package and closure digests
close every descriptor on success/refusal
```

The verifier may observe uid/gid/inode for race protection but must not include them in returned public digest identity.

- [ ] **Step 5: Run GREEN and resource-leak test**

```bash
python3 -m pytest -q -p no:cacheprovider \
  tests/test_executive_capability_packages.py
```

Add a bounded `/proc/self/fd` count assertion on Linux or an injected close-tracker to prove success/refusal closes descriptors.

- [ ] **Step 6: Commit**

```bash
git add \
  control_plane/executive_capability_packages.py \
  tests/test_executive_capability_packages.py
git commit -m "feat(scf): verify immutable package sources fail closed"
```

---

# Task 3: Add exact v4 fixture for the protected Mastermind Operator package

**Files:**
- Create: `tests/fixtures/executive_agent_capabilities_v4_mastermind_operator.json`
- Create: `tests/test_executive_agent_capabilities_v4.py`

**Consumes:** Task 1 package schema.

**Produces:** one exact policy fixture and immutable source-snapshot test independent of registry parsing.

- [ ] **Step 1: Create the exact v4 fixture**

Copy the current v3 default policy content into the fixture and change only:

```text
schema_version -> mastermind.executive_agent_capabilities/v4
policy_version -> 2026-09-01.mastermind-operator-p1-fixture
plugins -> exact mastermind-operator.p1 generation
profiles -> retain every current profile unchanged plus one fixture profile
```

The new fixture profile is:

```json
{
  "enabled": true,
  "execution_surface": "codex-app-server",
  "auth_realm": "dedicated-worker-account",
  "sandbox_policy": "read-only",
  "approval_policy": "never",
  "network_policy": "disabled",
  "write_capable": false,
  "native_helper_policy": "DISABLED",
  "native_helper": null,
  "skills": [
    "mastermind-operator.escalate-decision.v1",
    "mastermind-operator.finish-operation.v1",
    "mastermind-operator.receive-commission.v1",
    "mastermind-operator.return-progress.v1"
  ],
  "mcp_servers": [],
  "resources": [],
  "plugins": [],
  "forbidden": []
}
```

The package grant uses corrected package-content digest:

```text
a9781411d2642569f8b56e33bd0e0d9808a69176ccaced86642cd23948a71306
```

and the four closure digests frozen in the spec.

- [ ] **Step 2: Write a source snapshot test independent of production parser**

The test reads the real repository files under `plugins/mastermind-operator`, computes byte length/SHA-256/executable flag, and asserts exact seven-row equality with the fixture.

Then independently recompute:

```text
package-content digest
each effective Skill closure digest
```

using local test helper code rather than the new production functions. This avoids a shared implementation bug making both producer and verifier agree falsely.

- [ ] **Step 3: Add package-source mutation tests**

Copy the real package to a temp root and mutate:

```text
entrypoint byte
shared dialogue reference byte
unrelated app-binding template byte
native manifest byte
missing file
extra file
executable bit
```

Record the expected digest consequences:

```text
entrypoint drift -> package + corresponding closure change
shared reference drift -> package + all four closures change
unrelated app-binding drift -> package change; all four closures stable
manifest drift -> package change; all four closures stable
```

- [ ] **Step 4: Run RED**

```bash
python3 -m pytest -q -p no:cacheprovider \
  tests/test_executive_agent_capabilities_v4.py
```

At this task boundary, tests may validate fixture source identity without importing the v4 registry parser. They must pass before Task 4.

- [ ] **Step 5: Commit**

```bash
git add \
  tests/fixtures/executive_agent_capabilities_v4_mastermind_operator.json \
  tests/test_executive_agent_capabilities_v4.py
git commit -m "test(scf): freeze Mastermind Operator package generation"
```

---

# Task 4: Add exact v3/v4 registry dispatch without changing v3 semantics

**Files:**
- Modify: `control_plane/executive_agent_capabilities.py`
- Modify: `tests/test_executive_agent_capabilities.py`
- Modify: `tests/test_executive_agent_capabilities_v4.py`

**Consumes:** package parser/verifier and exact fixture.

**Produces:** a public registry loader that supports v3 and opt-in v4 while preserving default v3 identity.

- [ ] **Step 1: Pin current v3 compatibility before production edits**

Extend `tests/test_executive_agent_capabilities.py` with exact current assertions:

```python
assert CAPABILITY_POLICY_SCHEMA == CAPABILITY_POLICY_SCHEMA_V3
assert CAPABILITY_POLICY_SCHEMA_V3 == "mastermind.executive_agent_capabilities/v3"
assert CAPABILITY_POLICY_SCHEMA_V4 == "mastermind.executive_agent_capabilities/v4"
assert registry.schema_version == CAPABILITY_POLICY_SCHEMA_V3
assert registry.plugins == {}
assert registry.policy_digest == "b8fbfd9065764206b03f835f7fbc09910326f806584a8185229474aff59008b7"
assert registry.resolve(
    "operator.appserver.readonly.docs-mcp.native-helper.v1"
).profile_digest == "536853fb01d69ae8deca9a028b55c90aea0d1529f1fc80d83bb20d5d54f2cc44"
```

Also assert every current default profile has `skill_grants == ()`.

- [ ] **Step 2: Write RED v4 loader tests**

```python
registry = ExecutionCapabilityRegistry.load(
    V4_FIXTURE,
    source_root=REPO_ROOT,
)
assert registry.schema_version == CAPABILITY_POLICY_SCHEMA_V4
assert tuple(registry.plugins) == ("mastermind-operator.p1",)
```

Expected initial failure: v4 schema unsupported or plugins rejected.

- [ ] **Step 3: Add version constants and registry fields**

Add v3/v4 constants and preserve `CAPABILITY_POLICY_SCHEMA` as v3. Add `schema_version` and `plugins` to the registry dataclass. Add `skill_grants` to the profile dataclass.

V3 normalized profile/policy projections must remain exactly the old shape. Do not insert empty `skill_grants` or plugin metadata into v3 digest projections.

- [ ] **Step 4: Parse and verify v4 packages**

For v4 only:

```text
plugins must be a dict with 1-16 package generations
build each exact generation
reject duplicate runtime names globally
verify each source package against source_root
construct capability-id -> EffectiveSkillGrant map
```

Catch `CapabilityPackageError` and raise `CapabilityPolicyError` with the same bounded message and exception chaining.

For v3 only:

```text
plugins must equal {}
source_root is ignored
current behavior stays exact
```

- [ ] **Step 5: Run v3 and v4 focused tests**

```bash
python3 -m pytest -q -p no:cacheprovider \
  tests/test_executive_capability_packages.py \
  tests/test_executive_agent_capabilities.py \
  tests/test_executive_agent_capabilities_v4.py
```

- [ ] **Step 6: Commit**

```bash
git add \
  control_plane/executive_agent_capabilities.py \
  tests/test_executive_agent_capabilities.py \
  tests/test_executive_agent_capabilities_v4.py
git commit -m "feat(scf): load immutable package generations in registry v4"
```

---

# Task 5: Resolve exact v4 Skill capability IDs into profiles

**Files:**
- Modify: `control_plane/executive_agent_capabilities.py`
- Modify: `tests/test_executive_agent_capabilities_v4.py`

**Consumes:** Task 4 package/Skill registry.

**Produces:** resolved exact Skill grants and compatibility runtime names.

- [ ] **Step 1: Write RED profile-resolution assertions**

For the fixture profile:

```python
profile = registry.resolve("operator.appserver.readonly.mastermind-operator.v1")
assert profile.skills == (
    "escalate-decision",
    "finish-operation",
    "receive-commission",
    "return-progress",
)
assert tuple(grant.capability_id for grant in profile.skill_grants) == (
    "mastermind-operator.escalate-decision.v1",
    "mastermind-operator.finish-operation.v1",
    "mastermind-operator.receive-commission.v1",
    "mastermind-operator.return-progress.v1",
)
assert profile.plugins == ()
assert profile.write_capable is False
assert profile.native_helper_policy is NativeHelperPolicy.DISABLED
```

- [ ] **Step 2: Add hostile v4 profile cases**

Require `CapabilityPolicyError` for:

```text
unknown Skill capability ID
revoked package generation
same Skill ID repeated
multiple Skill IDs resolving to same runtime name
profile full plugins non-empty
codex-exec profile with Skills
write-capable profile with Skills before exact write-profile source law
browser profile inheriting custom Skills
Skill ID in forbidden by capability ID instead of runtime name
```

V4 `forbidden` continues to use provider-runtime capability names because launch comparison sees runtime names.

- [ ] **Step 3: Implement v4 resolution**

For v4:

```text
parse profile.skills as Skill capability IDs
resolve exact grants
preserve sorted capability-ID order in skill_grants
derive sorted unique runtime names in profile.skills
profile normalized digest includes each capability_id + grant_digest
```

For v3, retain current name-only input and `skill_grants=()`.

Until CAP-S1, keep the existing prohibition on write-capable extension profiles. V4 fixture Skill profile is read-only App Server only.

- [ ] **Step 4: Run focused tests**

```bash
python3 -m pytest -q -p no:cacheprovider \
  tests/test_executive_agent_capabilities.py \
  tests/test_executive_agent_capabilities_v4.py
```

- [ ] **Step 5: Commit**

```bash
git add \
  control_plane/executive_agent_capabilities.py \
  tests/test_executive_agent_capabilities_v4.py
git commit -m "feat(scf): resolve exact Skill grants into v4 profiles"
```

---

# Task 6: Compile exact Skill closures into the existing OHF manifest

**Files:**
- Modify: `control_plane/executive_agent_capabilities.py`
- Modify: `tests/test_executive_agent_capabilities_v4.py`
- Test unchanged compatibility: `tests/test_ohf_p1a_operator_harness_contract.py`

**Consumes:** resolved `EffectiveSkillGrant` rows.

**Produces:** existing `CapabilityIdentity` rows carrying the exact closure digest.

- [ ] **Step 1: Write RED manifest assertions**

```python
manifest = profile.capability_manifest(harness_binary_digest="a" * 64)
assert [(item.kind, item.name, item.skill_content_digest) for item in manifest.required] == [
    ("skill", "escalate-decision", "ca621a..."),
    ("skill", "finish-operation", "3e689a..."),
    ("skill", "receive-commission", "d79535..."),
    ("skill", "return-progress", "510be1..."),
]
assert all(item.harness_binary_digest == "a" * 64 for item in manifest.required)
assert manifest.allowed_ambient == ()
assert manifest.forbidden == ()
assert manifest.unclassified_policy == "fail_closed_on_write"
```

Use full literal digests in the test, not ellipses.

- [ ] **Step 2: Implement version-aware Skill compilation**

```text
v3 profile with name-only Skills -> preserve current name-only CapabilityIdentity behavior
v4 profile with skill_grants -> compile exact runtime name + skill_content_digest
```

Do not add package path, source commit, package generation or provider install state to the OHF `CapabilityIdentity`; those remain registry/profile provenance. The existing Attempt profile/policy digests bind the source generation.

- [ ] **Step 3: Prove current OHF contract remains unchanged**

```bash
python3 -m pytest -q -p no:cacheprovider \
  tests/test_executive_agent_capabilities.py \
  tests/test_executive_agent_capabilities_v4.py \
  tests/test_ohf_p1a_operator_harness_contract.py
```

- [ ] **Step 4: Commit**

```bash
git add \
  control_plane/executive_agent_capabilities.py \
  tests/test_executive_agent_capabilities_v4.py
git commit -m "feat(scf): compile exact Skill closure identities"
```

---

# Task 7: Freeze digest, revocation and source-correction semantics

**Files:**
- Modify: `tests/test_executive_agent_capabilities_v4.py`
- Modify production only if a test exposes a missing invariant.

**Consumes:** complete v4 parser/compiler.

**Produces:** the discriminating mutation matrix required before release.

- [ ] **Step 1: Add exact digest-cascade tests**

Copy the v4 fixture and source package to a temp root. For each mutation, load a correspondingly updated policy where required and assert:

```text
entrypoint byte change:
  corresponding closure changes
  package grant changes
  fixture profile changes
  policy changes

shared dialogue reference change:
  all four closures change
  package/profile/policy change

unrelated app-binding template change:
  all four closure digests stable
  package grant/profile provenance/policy change

manifest change:
  all four closure digests stable
  package grant/profile provenance/policy change
```

The loader must never accept changed source against the old declared digests.

- [ ] **Step 2: Add revocation tests**

```text
revoked package parses as historical source only if the registry needs it for diagnostics
no enabled profile may resolve a Skill from a revoked generation
resolve() refuses the fixture profile
policy digest changes on revocation
no source row is rewritten
```

Choose one closed behavior: recommended V4 loader accepts the revoked source grant for diagnostics after exact source verification, but refuses any profile referencing it. Do not silently delete it from `registry.plugins`.

- [ ] **Step 3: Add duplicate/conflict tests**

```text
same capability ID cannot occur twice in JSON map by construction; duplicate-aware JSON parsing is not added in this wave because current loader uses stdlib json and broader duplicate-key hardening belongs to a separately scoped source-security review
changed normalized payload under same fixture identity produces a different grant/policy digest
runtime-name collision across package grants refuses
case-fold path collision refuses
```

Record the duplicate-JSON-key limitation honestly in the PR if it remains inherited; do not claim protection that the loader does not provide.

- [ ] **Step 4: Run focused tests**

```bash
python3 -m pytest -q -p no:cacheprovider \
  tests/test_executive_capability_packages.py \
  tests/test_executive_agent_capabilities.py \
  tests/test_executive_agent_capabilities_v4.py
```

- [ ] **Step 5: Commit any test-only hardening**

```bash
git add tests/test_executive_agent_capabilities_v4.py
git commit -m "test(scf): falsify package generation drift and revocation"
```

Add production paths only if changed to satisfy a concrete RED test.

---

# Task 8: Prove protected no-edit surfaces and full repository compatibility

**Files:**
- Modify: `tests/test_executive_agent_capabilities_v4.py`
- No production file additions beyond prior tasks.

- [ ] **Step 1: Add static no-migration assertions**

Assert the current checked-in default policy still contains:

```python
raw = json.loads(Path("config/executive_agent_capabilities.json").read_text())
assert raw["schema_version"] == CAPABILITY_POLICY_SCHEMA_V3
assert raw["plugins"] == {}
assert "operator.appserver.readonly.mastermind-operator.v1" not in raw["profiles"]
```

Assert route/autonomy protected files contain none of the new package capability IDs or V4 fixture policy version.

- [ ] **Step 2: Run adjacent compatibility suites**

```bash
python3 -m pytest -q -p no:cacheprovider \
  tests/test_executive_capability_packages.py \
  tests/test_executive_agent_capabilities.py \
  tests/test_executive_agent_capabilities_v4.py \
  tests/test_executive_model_router.py \
  tests/test_executive_operator_supervisor.py \
  tests/test_codex_operator_adapter.py \
  tests/test_ohf_p1a_operator_harness_contract.py \
  tests/test_worker_browser_b1.py
```

No test may be excluded because it is slow or unrelated if the current repository gate discovers it.

- [ ] **Step 3: Run compile, diff and secret gates**

```bash
python3 -m py_compile \
  control_plane/executive_capability_packages.py \
  control_plane/executive_agent_capabilities.py \
  tests/test_executive_capability_packages.py \
  tests/test_executive_agent_capabilities_v4.py

git diff --check origin/master...HEAD

git diff --unified=0 origin/master...HEAD -- \
  | grep -E '^\+.*(BEGIN (RSA|OPENSSH|EC|DSA|PGP) PRIVATE KEY|api[_-]?key|bearer |password|refresh[_-]?token)' \
  && exit 1 || true
```

Test sentinels and error-word assertions must be reviewed rather than blindly classified as secrets.

- [ ] **Step 4: Run the complete repository gate**

```bash
python3 scripts/ci_pytest.py
```

Record discovered/running/excluded counts and terminal result.

- [ ] **Step 5: Commit final proof-only corrections if required**

Any correction follows RED-first discipline on the same carrier. Do not weaken source verification or v3 digest assertions to make CI green.

---

# Task 9: Hosted proof, adversarial review and source release

**Files:**
- No new implementation scope.
- PR metadata/evidence only unless a real defect is found.

- [ ] **Step 1: Re-pin protected source and collision census**

Before push/review:

```text
current protected Mastermind + Skillpack
open PRs touching:
  control_plane/executive_agent_capabilities.py
  control_plane/executive_capability_packages.py
  tests/test_executive_agent_capabilities.py
  package source paths
  capability config/routes/autonomy constants
```

If a current owner moved any semantic surface, history-preservingly reconcile or return to Sol. Do not create a replacement implementation carrier.

- [ ] **Step 2: Verify exact changed-file set**

Expected source implementation set:

```text
control_plane/executive_capability_packages.py
control_plane/executive_agent_capabilities.py
tests/fixtures/executive_agent_capabilities_v4_mastermind_operator.json
tests/test_executive_capability_packages.py
tests/test_executive_agent_capabilities.py
tests/test_executive_agent_capabilities_v4.py
```

No config, route, autonomy, provider, Browser, Business, PPF, Agent OS or deployment path may appear.

- [ ] **Step 3: Open draft PR with capability honesty**

PR state:

```text
SCF-PKG1 = BUILT_NOT_PROVEN / PRODUCTION_INERT / DEFAULT POLICY V3
```

The PR body must explicitly state:

```text
package source parser/verifier exists
v4 fixture proves exact source generation
current default policy remains v3
no Skill is installed or loaded
no Codex profile/route exists
no host receipt is rotated
CAP-S1 remains separate
```

- [ ] **Step 4: Require exact-head hosted CI**

Hosted repository `test` must be terminal SUCCESS on the final exact head. Earlier branch runs are supporting evidence only.

- [ ] **Step 5: Request independent review**

Review focus:

```text
no duplicate registry/control plane
v3 digest identity exact
source no-follow/race bounds
package vs closure separation
revocation behavior
no Business/PPF authority leakage
no hidden default migration
completion honesty
```

Critical/Important findings are repaired before release. If no independent reviewer returns, state the absence; do not fabricate approval.

- [ ] **Step 6: Final Sol review and expected-head merge**

Before merge, verify:

```text
protected base exact or reconciled
changed files exact
hosted CI green
review threads resolved
head immutable
no production/config changes
```

Merge with expected head SHA only.

- [ ] **Step 7: Stop**

Do not start CAP-S1 on the SCF-PKG1 implementation carrier. A new operation and branch are mandatory because default-policy migration, comparator correction and provider loading are independently reviewable effects.

---

## SCF-PKG1 completion packet

The worker returns:

```text
operation key
protected base
exact final head/tree
PR number
exact changed files
v3 policy/profile digest compatibility proof
v4 fixture package generation + corrected package-content digest
four Skill closure digests
source-verification hostile matrix results
focused/full CI counts and run IDs
independent review result or explicit absence
capability state = BUILT_NOT_PROVEN / PRODUCTION_INERT
confirmation default config/routes/autonomy/provider/browser files unchanged
known limitations
exact CAP-S1 next action
```

## Routing receipt

```text
ROUTE: Codex engineering worker / CTO Sol-compatible execution surface
WHY: single-repository, exact-contract, Python/TDD/security implementation with fully frozen architecture and bounded no-edit surfaces
WHY NOT FABLE: no remaining product/organizational ambiguity or sustained cross-repository program control is needed; scarce principal capacity would not improve this deterministic slice
```

## Stop condition

Stop at a protected SCF-PKG1 source implementation. Do not migrate the default policy, configure Codex, invoke a model, create a route, requalify a host, install a package, touch Business workspace state or begin heterogeneous provider work.
