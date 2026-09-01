# Mastermind Code Intelligence Fabric — F0 Language and Deployment Amendment

**Status:** `SPEC_ONLY / RECORDS_ONLY`  
**Parent architecture:** `research/MASTERMIND_CODE_INTELLIGENCE_FABRIC_F0_ARCHITECTURE_2026-08-30.md`  
**Current-base ruling:** `research/MASTERMIND_CODE_INTELLIGENCE_FABRIC_F0_CURRENT_BASE_RECONCILIATION_2026-08-30.md`  
**Applies to:** C0, Z0 and every later CodeIntel promotion wave  
**Current source observations:** protected `Mastermind@28d365cceaef6efb0a26e0ac9af51ead44695d60`, `macro@ede7e065a90b294e9835e98e5326a84e1c14d038`, protected `mastermind-terminal@afbc839e89c9e91d715c67872c44cf49895ee575`

This amendment closes two F0 gaps: company-representative language coverage and empirical service topology. It creates no language server, Serena process, Zoekt process, host installation, scheduler, webhook, polling loop, capability profile, workspace registry, service, credential, index or runtime capability.

For language qualification, semantic-backend identity, repository-controlled language configuration, deployment host selection, refresh cadence and staleness targets, this amendment is more specific than the original C0 and Z0 plans. Their path fences, tool contracts, authority boundaries and stop conditions remain binding.

## 1. Company-representative language floor

The first semantic qualification cannot be Python-only.

Mastermind and Macro contain major Python control-plane, research and data-system surfaces. Mastermind Terminal contains a protected TypeScript/TSX product surface with `terminal/tsconfig.json`; at the frozen Terminal pin, `terminal/lib/workspaceMigrate.ts` provides a real symbol/reference/consumer journey through `migrateLegacy`, its source-law relationships and its E2E/test consumers.

C0 therefore has two mandatory primary language families:

```text
Python
TypeScript + TSX
```

Shell, YAML, JSON, Markdown, SQL and other text remain discoverable through `codeDiscovery`. They do not receive persistent semantic-server machinery in V1 unless a frozen benchmark case proves a user or machine job that Python plus TypeScript/TSX semantics and global Zoekt cannot satisfy.

A backend cannot win C0 by passing one language and silently degrading the other. The C0 decision becomes:

```text
SERENA
DIRECT_LSP
NO_SAFE_BACKEND
```

only after the selected composition passes the shared security/worktree ruler for both primary language families. C0 may report per-language refusal reasons, but a partial backend is not promoted as the V1 exact-worktree semantic plane.

## 2. Fixed language-server set, never model-selected

The selected semantic capability profile owns one exact reviewed `language_server_set`. The set contains, for each language family:

```text
logical server identity
source repository + exact commit/tag
license and notice digests
build/publisher artifact provenance
binary/bundle SHA-256
fixed argv and closed environment
supported file extensions and workspace markers
configuration projection digest
server protocol/capability observation digest
```

The model cannot select, replace or configure a language server. No tool argument accepts a language-server name, executable, command, package path, environment, plugin path or configuration file.

The facade chooses a member of the attested set deterministically from the repository-relative file and reviewed extension/marker map. The worktree may contain `pyproject.toml`, `pyrightconfig.json`, `tsconfig.json`, `package.json` and equivalent semantic inputs, but those files never gain executable authority.

## 3. Repository configuration is data, not command authority

C0 must distinguish useful language configuration from executable widening.

Permitted repository inputs are bounded semantic facts such as source roots, include/exclude globs, module paths, compiler options, JSX mode, target libraries and type-checking strictness, subject to the selected server's reviewed parser.

The following are refused or proven inert:

- repository-selected server executable or version;
- arbitrary command or shell hook;
- automatic package download or type acquisition;
- network lookup;
- server/plugin path outside the sealed worktree and immutable capability bundle;
- TypeScript language-service plugins or `pluginProbeLocations` that execute repository or ambient package code;
- Python plugin/extension mechanisms that import repository-controlled executable code into the server process;
- configuration that changes the project root, adds another worktree, follows a symlink outside the seal or writes generated metadata into the candidate tree;
- server-side rename, code action, formatting, workspace edit, execute-command or file-operation capability exposed through the facade.

C0 must include hostile Python and TypeScript fixtures that attempt each applicable widening. If an otherwise useful server cannot prevent repository configuration from loading arbitrary executable plugins or crossing the sealed root, that server is refused rather than trusted because it runs in a read-only profile.

## 4. Mandatory C0 language matrix

The C0 plan's existing tasks are extended without widening their production path fence.

### Deterministic fixtures

Create parallel fixtures:

```text
tests/fixtures/code_intelligence/python_sample/**
tests/fixtures/code_intelligence/typescript_sample/**
```

Each fixture contains:

- interface/protocol or type contract;
- live implementation;
- deliberately similar dead sibling;
- producer, wrapper and consumer;
- tests importing the real consumer;
- one deterministic diagnostic;
- one hostile configuration/plugin case;
- Alpha/Beta worktree sentinels for cross-read testing.

### Real-source qualification

Python qualification uses the frozen O1/W1/A3 Mastermind cases already named by C0.

TypeScript/TSX qualification adds a frozen Terminal case at `afbc839e89c9e91d715c67872c44cf49895ee575`:

```text
symbol: migrateLegacy
producer: terminal/lib/workspaceMigrate.ts
known real consumers/evidence include the current workspace migration UX/E2E/test surfaces
job: locate declaration, references, related types/imports, test/source-law consumers and one change-impact boundary without reading another worktree
```

Before execution, C0 materializes the exact answer key from protected Terminal Git/GitHub evidence rather than treating this paragraph as the answer key.

### Measurements

C0 reports per language family and aggregate:

- startup/warmup time;
- steady-state and peak CPU/RAM;
- declaration/symbol/reference/implementation/diagnostic recall;
- false-positive and truncation burden;
- exact configuration and server identity;
- candidate-tree before/after digest;
- cross-worktree sentinel outcome;
- crash/restart and cleanup outcome;
- hostile configuration/plugin outcome.

The `BackendIdentity.language_server_identity/digest set` and the pre-turn `workspace_status` binding receipt include every active server, not merely the first server that started.

## 5. Multi-language workspace behavior

One Attempt-local facade may host more than one server process only from the exact reviewed set. It remains one subordinate semantic capability, not one lifecycle or scheduler per language.

Rules:

- launch lazily or eagerly according to C0 measurement, but record which process exists;
- one server failure degrades its language explicitly and cannot redirect that request to another worktree or ambient tool;
- no automatic install/restart loop;
- a restart is permitted only inside the same valid Attempt after binary, schema, workspace and candidate-tree re-attestation;
- all server processes share the same sealed root and external Attempt scratch boundary;
- the model sees one stable six-tool facade, not raw LSP methods or server identities;
- cross-language relationships beyond each server's real protocol are not fabricated. Global textual/canonical discovery remains the fallback.

## 6. Z0 deployment topology is an empirical decision

F0 does not choose a production host merely because Zoekt can run locally.

Z0 compares at least these deployment families as resource/operating envelopes, without installing either as production:

### T0 — colocated self-hosted discovery service

A dedicated service identity on an existing control/operations host may be acceptable only when measured index build, refresh and query load leaves reviewed CPU, RAM, disk, I/O and failure headroom and does not degrade Executive OS, Agent Relay, Control Room or another canonical runtime.

### T1 — separate self-hosted discovery node

A separate host may be preferred when isolation, disk/index size, refresh bursts or operational blast radius would make colocation unsafe. It remains a rebuildable search service, not a second company control plane.

Z0 records the measured envelope and recommends `T0`, `T1` or `NO_SAFE_TOPOLOGY`. It does not provision, select credentials for or deploy a host.

No model-facing request selects the host, endpoint, shard or refresh worker. The eventual HTTPS facade identity is fixed in the reviewed capability profile and attested by existing mechanisms.

## 7. Refresh and staleness law

The global index follows reviewed repository/ref manifests; it never becomes a general GitHub event bus or queue.

Z0 measures:

- initial full build time;
- one-repository incremental refresh time;
- protected/default-branch update detection-to-queryable latency;
- CPU/RAM/disk/I/O burst and steady state;
- failed refresh and prior-generation preservation;
- process restart and full rebuild time;
- credential outage and repository omission behavior.

The healthy product target is:

```text
protected/default ref update queryable within 5 minutes median
protected/default ref update queryable within 15 minutes at the reviewed healthy ceiling
```

These are promotion targets, not fabricated freshness. When the service misses them, responses expose the exact indexed SHA and `stale`/`degraded` state. A timestamp wrapper cannot make an old SHA fresh.

The production refresh mechanism is selected only after Z0 from the least-complex existing-capability-compatible option, for example a bounded deterministic repository poll or accepted source event path. It must:

- suppress unchanged refs without waking a reasoning model;
- keep credentials and repository URLs outside model context;
- use one current generation plus an atomic validated replacement;
- preserve the last healthy generation as explicitly stale when refresh fails;
- avoid a durable semantic queue, hidden replay cursor, retry database or one scheduler per repository;
- bound retries and never let a query request administer refresh;
- expose omission and coverage independently from process health.

Active PR refs remain excluded by default. A later selected-PR tier requires measured CI5 value, exact ref lifecycle/cleanup and its own bounded storage/resource law.

## 8. Z0 result and promotion consequences

The Z0 result adds:

```text
topology candidates and measured envelopes
recommended topology or NO_SAFE_TOPOLOGY
full/incremental/rebuild timings
healthy freshness budget and observed distribution
refresh trigger/mechanism recommendation
last-known-good generation behavior
operational owner and runbook requirements
```

Z0 cannot return `ZOEKT_FACADE_ACCEPTED_FOR_CI3` unless one topology and refresh composition is operationally plausible under the measured envelope. A good query benchmark with no safe host/cadence path yields `ZOEKT_REQUIRES_ARCHITECTURE_REVISION`.

CI3 still owns any production-inert service implementation. CI6 owns staged deployment proof. Z0 creates neither.

## 9. Capability truth and exact next action

```text
Python semantic qualification                    NOT_BUILT
TypeScript/TSX semantic qualification             NOT_BUILT
multi-language sealed facade                      NOT_BUILT
Zoekt production host topology                    NOT_SELECTED
Zoekt refresh mechanism/cadence                   NOT_SELECTED
language/deployment amendment                     SPEC_ONLY / RECORDS_ONLY
```

The exact next action remains release review of the complete F0 records carrier. After accepted F0 merge and durable Agent OS projection, C0 and Z0 implement these falsifiers under their already-bounded paths and stop before production integration.