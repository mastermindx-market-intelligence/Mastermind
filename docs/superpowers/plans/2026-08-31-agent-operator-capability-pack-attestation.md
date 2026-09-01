# Agent / Operator Capability Pack Attestation Implementation Plan

> **For implementing workers:** use the current protected Mastermind Skillpack plus `superpowers:test-driven-development` and either `superpowers:subagent-driven-development` or `superpowers:executing-plans`. Every wave below gets its own fresh operation key/carrier after its prerequisites are accepted. This plan is **not** start authority for a gated wave.

**Program owner:** Sol, AI CEO  
**Chairman:** Chris  
**Architecture:** `docs/superpowers/specs/2026-08-31-agent-operator-capability-convergence-design.md`  
**Planning operation:** `mastermind-agent-operator-capability-convergence-f0-20260831-sol-001`  
**Protected source basis for this plan:** `12c2cb8993f78e81c6cb9e9a75a9829f9b194dab`  
**Status:** **IMPLEMENTATION PLAN / DEPENDENCY GATED / PRODUCTION INERT**

## Goal

Make one company-owned operator skill provably portable across governed worker surfaces by binding its exact content into the existing `CapabilityManifest`, observing the exact loaded content before the first work turn, then adding deterministic provider-native materialization under the accepted HF1 common harness.

The first useful slice is deliberately small:

> A real read-only Codex rich-operator Attempt can require `receive-commission` from the protected `mastermind-operator` source package and will refuse launch if the observed skill has the same name but different bytes, a missing file, a symlinked/escaped tree, or insufficient content identity.

Later waves reuse that exact source identity through Claude, Grok and ZCode/GLM and combine it with the already-owned Browser Resource Fabric and MH1 host placement. No wave creates a new lifecycle, plugin registry, provider broker, browser scheduler, host scheduler or memory store.

---

# 0. Global gates and stop conditions

## 0.1 Hard prerequisites

Do **not** begin CAP-S1 implementation until all of the following are true:

1. current protected Skillpack is re-pinned and compatible;
2. current protected `master` and all active PRs touching `executive_agent_capabilities.py`, `operator_harness_contract.py`, `codex_operator_adapter.py`, `config/executive_agent_capabilities.json`, or BSC plugin-generation attestation are reconciled;
3. BSC-F2 has been accepted/protected far enough to expose exact plugin/source-generation truth through the **existing** `ExecutionCapabilityRegistry`, including repository commit, plugin root, exact skill file inventory/digests, generation and revocation;
4. the accepted F2 implementation still preserves `CapabilityIdentity.skill_content_digest` / `ObservedCapabilityIdentity.skill_content_digest` as the canonical skill identity seam;
5. CAP-S1 remains read-only and production-unarmed for its first canary.

If F2 lands with materially different source-grant names/types than this plan anticipated, **stop before implementation and return to Sol with the exact accepted interface**. Do not build a substitute registry to keep this plan cosmetically executable.

## 0.2 Later-wave prerequisites

- CAP-M1 provider-neutral materialization waits for accepted **HF1** after the current Capacity/Router chain.
- CAP-C1 real Claude parity waits for HF1 + current Claude provider readiness/adapter law.
- CAP-G1 waits for Grok G0 host/readiness proof + HF1.
- CAP-Z1 waits for a governed ZCode execution surface + HF1.
- browser parity waits for real Worker Browser B1 installed-path proof.
- multi-host parity waits for MH1.

## 0.3 Stop conditions shared by every wave

Stop and return to Sol if implementation would require any of:

- a second capability/plugin registry;
- a provider-specific Job/Attempt/Worker lifecycle;
- a new session database;
- dynamic model-controlled plugin/skill installation;
- credential copies into Git/worktrees/staging receipts;
- Chairman browser/profile reuse;
- bypassing `EFFECT_UNKNOWN` reconciliation to switch provider/host;
- making Agent OS own runtime plugin/session state;
- broadening browser/public-network authority merely to simplify a test;
- changing accepted BSC-F2, HF1, Browser B1 or MH1 ownership rather than extending it.

---

# 1. CAP-S1 — exact custom-skill content identity on Codex

**Observable mission:** one real read-only Codex rich-operator profile requires the protected `mastermind-operator/receive-commission` skill and launches only when the exact observed skill tree digest equals the exact source-generation digest sealed into the existing capability manifest.

**Why this matters:** current Codex attestation reads `skills/list` and sees skill names/paths, while the OHF identity contract already has `skill_content_digest`. The missing vertical is exact content identity, not another schema.

**Non-goals:** no plugin grant, no provider-neutral staging, no write-capable worker, no new browser authority, no provider routing change, no production arming.

## Task 1 — freeze one canonical skill-tree digest algorithm

**Files:**
- Create: `control_plane/operator_capability_digest.py`
- Create: `tests/test_operator_capability_digest.py`

**Interfaces:**

```python
SKILL_TREE_SCHEMA = "mastermind.skill_tree/v1"
MAX_SKILL_FILES = 256
MAX_SKILL_FILE_BYTES = 4 * 1024 * 1024
MAX_SKILL_TREE_BYTES = 16 * 1024 * 1024

@dataclasses.dataclass(frozen=True)
class SkillTreeFile:
    relative_path: str
    sha256: str
    byte_length: int
    executable: bool

@dataclasses.dataclass(frozen=True)
class SkillTreeManifest:
    schema_version: str
    files: tuple[SkillTreeFile, ...]


def inspect_skill_tree(root: Path) -> SkillTreeManifest: ...
def skill_content_digest(root: Path) -> str: ...
def skill_content_digest_from_manifest(manifest: SkillTreeManifest) -> str: ...
```

### Digest law

`skill_content_digest` is SHA-256 over canonical UTF-8 JSON:

```json
{
  "schema_version": "mastermind.skill_tree/v1",
  "files": [
    {
      "relative_path": "SKILL.md",
      "sha256": "...",
      "byte_length": 123,
      "executable": false
    }
  ]
}
```

Canonical encoding:

```python
json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
```

Rules:

- `SKILL.md` is mandatory and must be a regular file;
- recursively include **every regular file** in the skill directory, not only `SKILL.md` — scripts, references, assets and provider metadata can change behavior;
- relative paths use POSIX `/` separators and are sorted by UTF-8 lexical order;
- include file byte length, SHA-256 and executable bit (`mode & 0o111 != 0`);
- reject symlinks at the root or any descendant even if the provider supports them;
- reject sockets, devices, FIFOs and other non-regular descendants;
- reject path escape / `..` / NUL;
- enforce file-count/per-file/total-byte caps before digesting unbounded content;
- do not include uid/gid/mtime because those are host-local deployment metadata, not source behavior;
- do not read credential values or environment variables.

### Step 1: write RED tests

Create tests for:

```text
single SKILL.md produces stable 64-hex digest
same tree created in a different absolute path has same digest
file creation order does not change digest
one-byte SKILL.md change changes digest
reference/script change changes digest
executable-bit change changes digest
new extra file changes digest
missing SKILL.md refuses
symlinked root refuses
symlinked child refuses
FIFO/non-regular child refuses
per-file/tree/file-count bounds refuse
path traversal cannot be represented
```

### Step 2: run RED

```bash
python3 -m pytest -q -p no:cacheprovider tests/test_operator_capability_digest.py
```

Expected: import failure.

### Step 3: implement minimum pure utility

Keep the module filesystem-only and authority-free. It must not know Job, Attempt, provider, registry, marketplace or worker identities.

### Step 4: run GREEN

```bash
python3 -m pytest -q -p no:cacheprovider tests/test_operator_capability_digest.py
```

### Step 5: commit

```bash
git add control_plane/operator_capability_digest.py tests/test_operator_capability_digest.py
git commit -m "feat(exec): define exact operator skill tree digest"
```

---

## Task 2 — compile accepted source-generation truth into existing `CapabilityIdentity`

**Files:**
- Modify: `control_plane/executive_agent_capabilities.py`
- Modify: `config/executive_agent_capabilities.json`
- Modify: `tests/test_executive_agent_capabilities.py`
- Reuse: the accepted BSC-F2 registry/source-generation fields; do **not** add another registry file.

### Required behavior

After accepted F2, one production-unarmed profile is added for the first vertical, conceptually:

```text
operator.appserver.readonly.mastermind-operator.receive-commission.v1
```

It remains:

```text
execution_surface = codex-app-server
sandbox_policy = read-only
approval_policy = never
write_capable = false
plugins = []              # still no plugin grant in CAP-S1
mcp_servers = [] unless current profile law requires an existing exact read-only MCP
skills = [receive-commission capability identity]
production_armed = false
```

The exact profile/config syntax must consume F2's **accepted canonical source grant**, not duplicate repository path/commit/digests under a new CAP-S1-only table.

When `ExecutionCapabilityProfile.capability_manifest(...)` compiles a required custom skill, the resulting existing `CapabilityIdentity` must include:

```python
CapabilityIdentity(
    kind="skill",
    name="receive-commission",
    skill_content_digest=<exact 64-hex digest derived from accepted source inventory>,
    harness_binary_digest=<existing behavior>,
)
```

### Source-to-skill digest rule

The expected `skill_content_digest` must be computed from the accepted F2 per-file source inventory using the same `mastermind.skill_tree/v1` algorithm as Task 1. Do not rely on:

- Git tree SHA alone;
- Git blob SHA alone;
- marketplace version string;
- plugin version string;
- skill name;
- current mutable working tree without exact protected commit identity.

For the first vertical, the protected source is the `receive-commission` skill under the accepted `mastermind-operator` plugin generation. The expected digest follows the accepted generation, not this planning commit forever.

### Step 1: write RED tests

Extend `tests/test_executive_agent_capabilities.py`:

```text
accepted skill source grant compiles kind=skill + exact skill_content_digest
same skill name with changed file digest changes policy/profile digest
revoked source generation cannot resolve a new profile/Attempt
missing skill in plugin source inventory refuses registry load/resolve
malformed/non-hex file digest refuses
profile cannot name a skill without an accepted exact source grant
plugins remain empty for CAP-S1
production_armed remains false
```

Also assert the current MCP/native-helper/browser profiles remain byte-for-byte equivalent in semantic output.

### Step 2: run RED

```bash
python3 -m pytest -q -p no:cacheprovider tests/test_executive_agent_capabilities.py
```

### Step 3: implement only the existing-registry extension

Use F2's accepted grant type/loader. Add only the minimum skill lookup/digest derivation needed to populate the already-existing field.

Do not add:

```text
config/operator_skills.json
SkillRegistry
PluginInstallDB
CapabilityPackStore
```

### Step 4: run GREEN

```bash
python3 -m pytest -q -p no:cacheprovider \
  tests/test_operator_capability_digest.py \
  tests/test_executive_agent_capabilities.py
```

### Step 5: commit

```bash
git add control_plane/executive_agent_capabilities.py config/executive_agent_capabilities.json tests/test_executive_agent_capabilities.py
git commit -m "feat(exec): seal exact custom skill content in capability profiles"
```

---

## Task 3 — observe exact Codex loaded skill content before the first turn

**Files:**
- Modify: `control_plane/codex_operator_adapter.py`
- Modify: `tests/test_codex_operator_adapter.py`
- Modify: `scripts/ohf/fake_app_server.py` only if protocol-faithful test fixtures require an additional real App Server field already present in the installed runtime.
- Modify: `tests/test_ohf_protocol_fidelity.py` only if the fake protocol fixture changes.
- Reuse: `control_plane/operator_capability_digest.py`

### Current source seam

Protected source already does:

```python
skills_raw = client.request("skills/list", skills_list_params(str(self.workspace_root)))
skills = parse_skills_list(skills_raw)
...
ObservedCapabilityIdentity(kind="skill", name=name)
```

The fake App Server already returns a skill row with `name`, `enabled`, `path`, and `scope`.

### Required behavior

For every observed skill row with a usable path inside an allowed observed root, produce:

```python
ObservedCapabilityIdentity(
    kind="skill",
    name=name,
    skill_content_digest=skill_content_digest(skill_path),
)
```

Allowed roots in the first Codex vertical are closed to:

- the exact configured `workspace_root`; and
- the exact dedicated `codex_home` used by that Worker realm.

A skill path outside those roots may still be recorded by **name only** as an ambient/unclassified provider capability, but it cannot satisfy a required custom skill whose requested identity carries a digest.

### Path/identity rules

- canonicalize and containment-check without following an untrusted symlink chain;
- reject a required skill if its row path is missing, non-directory, escaped or symlinked;
- use the full tree digest from Task 1;
- never read a path merely because the model/provider returned it if it is outside the closed roots;
- do not hash the entire provider home; only the discovered skill directory under explicit bounds;
- no raw skill body is added to Events/receipts;
- `skills/list` failure remains effect-unknown/attestation failure under current adapter law;
- provider support for symlinked skills does not override Mastermind's stricter exact-identity rule.

### Duplicate-name law

Current Codex documentation allows multiple skills sharing one `name`. Therefore a required exact custom skill is satisfied only when the observed capability multiset contains exactly one matching `(name, skill_content_digest)` under the comparator's existing duplicate/ambient law. Same-name/different-digest rows may not be silently merged.

If current `compare_launch` collapses duplicates by name, add the **smallest correction to the existing comparator** and tests; do not introduce provider-specific comparison code.

### Step 1: write RED tests

Extend `_make_harness()` so the fixture can write controlled skill tree variants. Add:

```text
required exact skill digest + exact observed tree -> ALLOW
same skill name + changed SKILL.md -> REFUSE
same skill name + extra reference file -> REFUSE
missing required skill -> REFUSE
skill row with path outside workspace/codex_home cannot satisfy exact requirement
symlinked skill root refuses exact requirement
symlinked child refuses exact requirement
duplicate same-name exact + different content refuses ambiguity/ambient widening
observed built-in/unrequested skill does not satisfy custom required identity
no raw SKILL.md content appears in attestation serialization/logs
```

### Step 2: run RED

```bash
python3 -m pytest -q -p no:cacheprovider \
  tests/test_codex_operator_adapter.py \
  tests/test_ohf_attestation.py
```

### Step 3: implement the minimum adapter observation

Do not change `supports_config_staging` in CAP-S1. This wave observes a pre-provisioned or repo-local exact skill on the existing Codex surface; provider-neutral staging is CAP-M1 after HF1.

### Step 4: run GREEN + protocol regressions

```bash
python3 -m pytest -q -p no:cacheprovider \
  tests/test_operator_capability_digest.py \
  tests/test_executive_agent_capabilities.py \
  tests/test_codex_operator_adapter.py \
  tests/test_ohf_attestation.py \
  tests/test_ohf_protocol_fidelity.py
```

### Step 5: commit

```bash
git add control_plane/codex_operator_adapter.py tests/test_codex_operator_adapter.py scripts/ohf/fake_app_server.py tests/test_ohf_protocol_fidelity.py
git commit -m "feat(ohf): attest exact loaded Codex skill content"
```

Only add fake-server/protocol files if actually changed.

---

## Task 4 — prove CAP-S1 through the real Codex installed path

**Files:**
- Add/modify only the existing OHF laboratory/canary script path selected by current protected source after reconciliation.
- Add a redacted evidence document only if current repository proof convention requires it.
- Do not add production arming.

### Canary setup

Use an isolated read-only Worker realm and dedicated `CODEX_HOME`. Provision the **accepted exact generation** of `receive-commission` before the Worker is considered ready.

Preferred source path is a provider-native reviewed plugin/skill install or immutable local projection of the accepted bundle generation. Do **not** copy the skill into an application/product worktree merely to make discovery convenient unless that worktree is a dedicated laboratory fixture.

No marketplace/network install happens during the Attempt.

### Discriminating model probe

Run one real read-only operator Attempt whose turn explicitly invokes the skill in current Codex syntax:

```text
$receive-commission
```

The prompt supplies a harmless synthetic commission and asks the model to return the classification/acknowledgement shape required by the skill without changing files or external state.

The proof must establish both:

1. **environment truth:** exact requested/observed `skill_content_digest` matched before the turn; and
2. **usefulness truth:** the worker actually used the skill and returned the expected workflow behavior on a discriminating probe.

A name in `/skills` without the exact digest does not pass. A digest match without a real model turn does not prove the feature useful.

### Negative canaries

Run isolated laboratory variants, never production profiles:

- same name, one-byte changed `SKILL.md` → launch refusal before turn;
- same name, added reference file → refusal;
- required skill absent → refusal;
- symlinked source → refusal;
- extra ambient custom skill in an exact profile → refusal if current manifest law classifies it as influence capability.

### Required proof bundle

Capture only secret-safe evidence:

```text
Attempt/profile ID + profile digest
capability policy version/digest
accepted plugin/source generation
expected skill_content_digest
observed skill_content_digest
Codex harness version/binary digest
sandbox/approval/network state
provider session identity only at existing redacted precision
launch decision
model probe result summary
process-death/writer-release receipt
negative-canary refusal codes
```

Never persist auth file contents, access tokens, private environment values or full sensitive local paths beyond existing redaction law.

### Test gate before canary

```bash
python3 -m pytest -q -p no:cacheprovider \
  tests/test_operator_capability_digest.py \
  tests/test_executive_agent_capabilities.py \
  tests/test_codex_operator_adapter.py \
  tests/test_ohf_attestation.py \
  tests/test_ohf_auth_isolation.py \
  tests/test_ohf_protocol_fidelity.py
python3 scripts/ci_pytest.py
```

### CAP-S1 acceptance

CAP-S1 becomes `PROVEN_LIVE` only for the exact laboratory/read-only profile when the real installed-path canary and negative falsifiers pass. It does **not** arm write-capable plugin use or claim cross-provider parity.

---

# 2. CAP-M1 — deterministic provider-native materialization after HF1

**Prerequisites:** accepted CAP-S1 + accepted HF1. Re-pin current source; HF1 may have moved names/paths. The accepted HF1 contract wins.

**Observable mission:** stage the exact accepted capability bundle generation into an Attempt-owned provider-native directory without starting the provider, writing credentials, mutating the authoritative workspace, or changing the sealed authority envelope.

## Task 5 — add the provider-neutral materialization contract to the accepted HF1 seam

**Expected files after HF1:**
- Create: `control_plane/operator_capability_materializer.py`
- Create: `tests/test_operator_capability_materializer.py`
- Modify: accepted `control_plane/worker_execution_contract.py` only if one additional provider-neutral receipt reference is required.
- Modify: `control_plane/operator_harness_contract.py` only if `StageConfigReceipt` needs a strictly additive field already compatible with OHF law.

If HF1 lands a different accepted common-contract path, stop and re-plan against that exact protected source rather than creating a parallel contract.

### Interfaces

```python
MATERIALIZATION_RECEIPT_SCHEMA = "mastermind.capability_materialization_receipt/v1"

@dataclasses.dataclass(frozen=True)
class MaterializedFile:
    relative_path: str
    sha256: str
    byte_length: int
    executable: bool

@dataclasses.dataclass(frozen=True)
class CapabilityMaterializationReceipt:
    schema_version: str
    execution_profile_id: str
    execution_profile_digest: str
    capability_policy_digest: str
    bundle_capability_id: str
    bundle_generation: str
    bundle_source_commit: str
    provider: str
    files: tuple[MaterializedFile, ...]
    skills: tuple[tuple[str, str], ...]  # name, skill_content_digest
    wrote_credentials: bool
    mutated_workspace: bool
    started_process: bool
```

The materializer consumes an already-resolved accepted grant/profile and provider projection rules. It is not allowed to query marketplaces or choose capabilities.

### Closed staging law

- output root is created by the supervisor under the Attempt run/staging directory;
- output path cannot be inside the authoritative source worktree;
- no symlinks/hardlinks to mutable external source;
- each file is written from already-reviewed bytes/source generation;
- credentials are never materialized;
- source and destination file inventory/digests must agree;
- provider-native generated manifest/config is deterministic and itself included in the receipt;
- stage operation starts no provider/MCP/browser process;
- failure before provider start is `NO_EFFECT`/retryable only under existing operation law;
- receipt is evidence/artifact, not lifecycle truth.

### RED tests

```text
same input generation + provider projection -> byte-identical staging and receipt
staging root inside workspace refuses
source symlink refuses
provider projection tries to write credential marker -> refuses
unexpected generated file refuses
file digest mismatch refuses
materializer never starts a process
materializer never reads parent provider credentials
second invocation with same immutable input is deterministic
changed bundle generation changes receipt digest/inventory
```

### Verification

```bash
python3 -m pytest -q -p no:cacheprovider \
  tests/test_operator_capability_digest.py \
  tests/test_operator_capability_materializer.py \
  tests/test_worker_execution_contract.py \
  tests/test_codex_operator_adapter.py
```

---

## Task 6 — make Codex the first native materializer implementation

**Files:**
- Create: `control_plane/codex_capability_materializer.py`
- Create: `tests/test_codex_capability_materializer.py`
- Modify: `control_plane/codex_operator_adapter.py`
- Modify: `tests/test_codex_operator_adapter.py`

### Current-provider law to preserve

Current Codex docs support repo/user/admin/system skill locations and plugin distribution. Mastermind must choose a process-scoped/dedicated-home projection that does not mutate a product worktree and does not use a model-driven installer.

The implementation must be based on the exact accepted Codex runtime at execution time. Do not assume that a documented local marketplace path is process-isolated until falsified.

### Required behavior

- accepted bundle source → deterministic Codex-native staging under the Attempt/dedicated Worker realm;
- provider config enables only the required staged custom capability generation;
- existing system/built-in skills are classified through ambient capability law, not mistaken for company custom grants;
- adapter reports `supports_config_staging=True` only after `stage_operator_config(...)` actually implements the existing OHF side-effect contract;
- `observed_attestation()` still independently computes/observes effective capability identity;
- materialization receipt and runtime observation must agree before work.

### Key falsifiers

```text
same-name user skill outside staged generation cannot shadow required company skill
provider supports symlinked skills but Mastermind staging contains none
hot reload after attestation cannot change effective company skill generation unnoticed
local/global plugin cache cannot override staged generation
model cannot invoke skill-installer/plugin installer to widen capability
```

---

# 3. CAP-C1 — first non-Codex parity vertical on Claude

**Prerequisites:** HF1 accepted; CAP-M1 accepted; Claude adapter/provider readiness accepted; exact installed Claude Code documentation/runtime re-pinned.

**Observable mission:** one read-only Claude worker executes the same synthetic commission with the same canonical `receive-commission` source generation and semantically identical capability profile.

**Expected files:**
- Create: `control_plane/claude_capability_materializer.py`
- Create: `tests/test_claude_capability_materializer.py`
- Modify the exact Claude HF1/PF1 adapter path accepted by current protected source.
- Add adapter tests beside the accepted Claude adapter tests.

Do not create `claude_broker.py` or Claude lifecycle tables.

### Provider projection

Use current Claude-native plugin/skill layout and a process-scoped/local plugin directory only if the exact installed runtime proves:

- source is the staged immutable generation;
- no automatic marketplace mutation;
- no ambient project/user plugin shadowing;
- no unreviewed hooks are enabled;
- no secret environment inheritance outside the provider's accepted auth realm;
- runtime effective capabilities can be observed at sufficient precision.

### Acceptance

Same canonical skill source generation and digest must produce:

```text
Codex requested digest == Claude requested digest
Codex observed digest == Claude observed digest == requested digest
provider-native staged file paths may differ
provider session identities may differ
Executive capability semantics may not differ
```

One discriminating real-model probe must pass on both providers. Provider parity is not accepted from fixture tests alone.

---

# 4. CAP-G1 — Grok parity without a bespoke package fork

**Prerequisites:** Grok G0 readiness + HF1 + CAP-M1.

Current xAI docs state Grok Build can read Claude Code plugins/skills/MCPs. Start by feeding the **same Claude-compatible staged source projection** to Grok.

Create a Grok-specific projection only if an exact canary demonstrates a real incompatibility. If one is required, its generated files are included in the same source/materialization receipt and may not change company workflow semantics.

Critical test: Grok documents `allowed-tools` as non-enforcing for skills. Therefore a canary must prove Mastermind tool/network/write authority comes from the sealed execution profile and host sandbox, never skill metadata.

No `grok_broker` and no provider failover on ambiguous operation.

---

# 5. CAP-Z1 — ZCode / GLM parity with environment isolation

**Prerequisites:** governed ZCode Worker realm + HF1 + CAP-M1.

Current ZCode docs support `.zcode-plugin/plugin.json` and Claude-compatible fallback. Start with the shared source projection where possible.

ZCode explicitly treats enabled plugins as code-execution trust and can expose inherited environment variables. Acceptance therefore requires:

```text
sanitized provider process environment
no credential values in plugin files
no mutable symlink import in production proof
no local/remote plugin sync mutation during an Attempt
reload behavior cannot switch generation after seal
exact staged/observed skill digest
```

Model identity (for example GLM) remains separate from the ZCode execution surface identity.

---

# 6. CAP-P1 — exact full `mastermind-operator` plugin generation

**Prerequisites:** accepted BSC-F2 implementation + CAP-S1 + at least one non-Codex skill parity proof.

**Observable mission:** grant one exact `mastermind-operator` plugin generation through the existing registry and prove all four current workflow skills are the accepted source inventory:

```text
receive-commission
return-progress
escalate-decision
finish-operation
```

The plugin grant must bind source commit/generation/manifest/inventory/revocation exactly as BSC-F2 requires. Provider-native materializers project that same generation.

MCP/app references remain independent capability identities. Installing the plugin never grants Business/Executive/Dialogue authority by itself.

Negative tests must cover:

```text
same plugin version + changed source bytes -> refuse
same skill inventory + changed one file -> refuse
extra skill/hook/MCP in observed plugin -> refuse exact profile
revoked generation -> new Attempt ineligible
provider-native manifest drift -> refuse
plugin installed but app generation/auth binding mismatched -> modifying use refused
```

---

# 7. CAP-B1X — cross-provider browser parity

**Prerequisites:** Worker Browser B1 real installed-path proof + HF1 + second provider adapter.

Do not add another browser implementation. Reuse:

```text
operator.browser.local-review.v1
mastermind.browser_review_receipt/v1
existing browser/devserver supervisor/resource lifecycle
```

The second provider must consume the same browser resource identity and produce useful structured + visual proof. Its capability-pack materializer may configure the provider-facing Playwright MCP reference, but it does not start or own the browser resource.

Acceptance requires the same discriminating pixel-visible fixture used by the existing Browser Fabric proof law.

Only after B1X should a separate wave consider the already-designed exact company-production read-only inspect profile. Arbitrary public web remains a different capability and is not bundled into CAP-B1X.

---

# 8. CAP-H1 — multi-host capability parity

**Prerequisites:** MH1 accepted + two READY host-local Worker realms + at least one accepted provider-native bundle projection.

The same source generation/profile must run on a second host without:

- copying provider credentials;
- sharing a mutable writable plugin cache;
- changing bundle identity;
- introducing a host scheduler;
- switching host after an effect-unknown provider operation.

Host/resource preference remains Capacity Fabric policy. The materializer receives an already-selected Worker/host realm and stages locally.

---

# 9. Full regression and adversarial review gate

Every implementation PR in this program must run its focused tests plus the current repository gate. At minimum, after CAP-S1:

```bash
python3 -m pytest -q -p no:cacheprovider \
  tests/test_operator_capability_digest.py \
  tests/test_executive_agent_capabilities.py \
  tests/test_codex_operator_adapter.py \
  tests/test_ohf_attestation.py \
  tests/test_ohf_auth_isolation.py \
  tests/test_ohf_protocol_fidelity.py
python3 scripts/ci_pytest.py
```

After HF1/materialization, add the current accepted common-worker suites:

```bash
python3 -m pytest -q -p no:cacheprovider \
  tests/test_worker_execution_contract.py \
  tests/test_worker_adapter_broker_contract.py \
  tests/test_executive_worker_broker.py \
  tests/test_executive_operator_broker.py \
  tests/test_executive_operator_supervisor.py \
  tests/test_codex_operator_adapter.py
```

Use the current exact test file names after rebase; do not resurrect paths removed by accepted HF1.

## Sol adversarial review checklist

For every PR, Sol asks:

1. What useful worker capability exists now that did not before?
2. Is the profile source identity exact, or are we trusting name/version prose?
3. Can same-name/different-content pass anywhere?
4. Does provider packaging or a skill file accidentally grant authority?
5. Did the worker create a new registry/broker/lifecycle/resource allocator?
6. Can ambient global/user/project extensions influence the worker without being represented?
7. Can the provider hot-reload capability bytes after the seal?
8. Are credentials or inherited environment values visible to plugin code/model output?
9. Did staging mutate an authoritative source worktree?
10. Did any test use a fake provider behavior that the real installed runtime does not expose?
11. Is the real model able to use the capability, not merely list it?
12. Did a browser resource become ambient/unrestricted?
13. Did a remote/provider ambiguity trigger illegal retry/failover?
14. Is green CI being confused with production proof?

---

# 10. Required continuation handoff after every wave

Every accepted wave leaves a durable handoff containing:

```text
operation key
protected base + exact merged SHA
PR + exact head/tree reviewed
capability-state transition
execution_profile_id + digest
capability policy version/digest
bundle/source generation + immutable source commit
deterministic materialization receipt schema/version if applicable
requested + observed skill/plugin/MCP/resource identities
real provider/host canary facts
negative falsifiers run
production-armed state
open dependency/collision set
exact next wave
explicit statement of what remains NOT_BUILT / BUILT_NOT_PROVEN
```

Do not leave a future Sol session to infer provider capability parity from a merge message or this chat.

---

# 11. Immediate sequencing ruling

The implementation order is:

```text
active existing gates continue
    ├─ BSC-F2 installed source/app generation attestation
    └─ CF2 → RF1 → HF1 common provider boundary

then
CAP-S1 exact Codex custom-skill content proof
  ↓
CAP-M1 deterministic provider-native materialization
  ↓
CAP-C1 Claude parity
  ├─ CAP-G1 Grok parity when Grok readiness is accepted
  └─ CAP-Z1 ZCode/GLM parity when governed surface is accepted
  ↓
CAP-P1 full mastermind-operator plugin-generation parity

separate resource tracks:
Worker Browser B1 production proof → CAP-B1X second-provider browser parity
HF1 + MH1 → CAP-H1 multi-host parity
```

Do not collapse these into one implementation PR. Each line must create one independently useful, reviewable capability and prove it through the real production/runtime path before the next authority envelope is widened.
