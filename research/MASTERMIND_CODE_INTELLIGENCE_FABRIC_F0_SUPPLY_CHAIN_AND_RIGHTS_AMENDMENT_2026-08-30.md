# Mastermind Code Intelligence Fabric — F0 Supply-Chain and Rights Amendment

**Status:** `SPEC_ONLY / RECORDS_ONLY`  
**Parent architecture:** `research/MASTERMIND_CODE_INTELLIGENCE_FABRIC_F0_ARCHITECTURE_2026-08-30.md`  
**Applies to:** C0 semantic falsifier, Z0 discovery falsifier, CI1–CI6, every later backend/index upgrade  
**Frozen against:** protected `Mastermind@8f0babf473e6e4e8efce697014bd48c594227d94`

This amendment supplies the rights-safe and software-supply-chain gate that the parent architecture requires but did not spell out completely. It creates no implementation, binary, package mirror, SBOM service, vulnerability database, MCP server, host install, credential, index, process, worker profile or runtime capability.

For upstream identity, license evidence, binary provenance and notice obligations, this amendment is more specific than the parent architecture and the two 2026-08-30 C0/Z0 plans. It does not change their product, authority, workspace, tool-surface or no-rebuild boundaries.

## 1. Exact upstream rights evidence

The initially approved experiment pins are:

| Component | Exact source identity | License at that identity | Exact license blob |
|---|---|---|---|
| Serena | `oraios/serena@949a27ef1e5fda1a6e7b561e777bcece345c6ffd` (`v1.7.0`) | MIT | `d27bba648a59b23cadf39b9e74fd0684ea2e15dd` |
| Zoekt | `sourcegraph/zoekt@5f833dde1bc4b1a8f99007617b4b721e44506c4f` | Apache License 2.0 | `261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64` |

These facts permit the bounded internal experiments under the corresponding license terms. They do **not** authorize a floating upgrade, an unreviewed fork, distribution without required notices, or production promotion of an opaque prebuilt binary.

The direct-LSP candidate remains intentionally unselected. C0 may admit one candidate only after recording:

```text
repository and exact source commit/tag
license name and exact license/notice blob digests
build or package identity
exact executable/bundle SHA-256
transitive dependency lock or module graph
required attribution/NOTICE obligations
known license incompatibility or usage restriction = none, or typed refusal
```

Missing or ambiguous rights evidence yields `UPSTREAM_RIGHTS_UNRESOLVED` and that candidate cannot win C0.

## 2. Source-to-binary provenance

Every executable or bundle used by C0/Z0 and every later production profile must be traceable as:

```text
reviewed source repository + exact commit
-> exact build recipe/toolchain/container base or verified publisher artifact
-> dependency lock/module graph
-> binary/bundle SHA-256
-> license/NOTICE manifest
-> vulnerability/advisory observation timestamp
```

The following are forbidden as authoritative identities:

- `latest` tags;
- mutable branch names without an accompanying exact commit;
- PATH-only executable resolution;
- `uvx`, `pipx`, `npx`, `go install`, Homebrew or another package launcher without an exact immutable package/version/artifact digest and retained provenance;
- mutable container tags;
- downloading or compiling inside a model turn;
- repository-controlled executable or package selection;
- a binary digest with no source/license relationship;
- a source pin with no proof of the actual executed bytes.

C0/Z0 may use a host-prepared exact binary only when the runner verifies owner, mode, symlink state and digest before and after launch. CI1/CI3 must define the production build/install owner and immutable bundle format rather than inheriting an experiment scratch path.

## 3. Required experiment report fields

The C0 `mastermind.codeintel_c0_result.v1` and Z0 `mastermind.codeintel_z0_result.v1` schemas must include, for every upstream executable or library:

```text
component_id
source_repository
source_commit
source_tag, nullable
license_spdx_or_exact_name
license_blob_sha
notice_blob_shas
build_recipe_digest or verified_publisher_artifact_digest
binary_or_bundle_sha256
dependency_manifest_sha256
advisory_observed_at
known_unresolved_rights_or_supply_chain_findings
```

A report that omits these fields is incomplete even when semantic/search tests pass. License text itself need not be copied into the benchmark transcript; exact source/blob identity and the later shipped notices remain the durable evidence.

## 4. Production promotion gate

Before CI4 grants a canary profile and before CI6 production rollout, the selected composition requires:

1. one reviewed component inventory with exact source, binary and configuration identities;
2. retained required MIT/Apache/other notices in the installed bundle or accompanying distribution as the licenses require;
3. an SBOM or equivalently complete content-addressed dependency manifest;
4. no unresolved license conflict for Mastermind's intended internal use, modification, deployment and any foreseeable distribution;
5. current security-advisory review for every selected component and language server;
6. deterministic rebuild or verified-publisher reproduction evidence;
7. upgrade law: a version, source, dependency, tool schema, executable or notice change creates a new reviewed capability identity and re-runs the relevant C0/Z0/CI1–CI5 gates;
8. rollback retains the prior reviewed bundle and never silently installs a floating replacement.

A vulnerability advisory does not automatically imply rejection; Sol adjudicates exploitability and mitigation against the actual disabled surface. An unresolved executable-origin or license ambiguity does imply refusal.

## 5. Data-rights and privacy boundary

CodeIntel may index and analyze only repositories/refs already lawfully available to the exact Mastermind host/principal and admitted by the reviewed repository manifest. It acquires no right to ingest third-party proprietary corpora, competitor source, leaked code, unlicensed datasets or arbitrary user directories.

The selected engines run self-hosted. Source text, snippets, symbol names, paths and index contents are not sent to an external code-intelligence SaaS. Model/tool responses remain bounded to the authorized worker context; repository credentials, absolute host paths and binary locations remain outside model arguments and result payloads.

Generated indexes, caches and benchmark transcripts inherit the confidentiality of their source repositories. Disposal/retention is defined before the first real private-repository run; experiment convenience is not permission to publish or persist code evidence in a new organizational memory plane.

## 6. Wave-specific consequences

### C0

C0 compares pinned Serena with one exact direct-LSP candidate. It may return:

```text
SERENA
DIRECT_LSP
NO_SAFE_BACKEND
```

only after the selected candidate passes both semantic/security falsifiers and this rights/provenance gate. A semantically superior backend with unresolved executable or license identity is not selectable.

### Z0

Z0 builds or verifies Zoekt only from the exact pinned source identity. Its result records Go toolchain/build recipe, module/dependency graph, resulting binary digests and Apache-2.0 notice obligations. A working index built from an unrecorded mutable toolchain is not a reproducible Z0 pass.

### CI1–CI6

The existing `ExecutionCapabilityRegistry` remains the capability authority. Supply-chain metadata belongs in the reviewed immutable capability/bundle evidence and attestation projection selected by CI1; this amendment does not create a package registry, artifact lifecycle, updater, vulnerability control plane or license database.

## 7. F0 acceptance consequence

F0 remains `SPEC_ONLY / RECORDS_ONLY`. This amendment closes the architecture's rights-safe input boundary but proves no third-party component installed, built, safe, useful or live.

The exact next action remains C0 and Z0 after F0 acceptance. Their commissions must cite this amendment after the parent architecture and before their implementation plans wherever upstream identity, license, binary provenance or notice obligations are involved.