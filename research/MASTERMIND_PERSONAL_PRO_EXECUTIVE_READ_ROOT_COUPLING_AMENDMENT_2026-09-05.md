# Personal-Pro Executive read-root coupling amendment

**Date:** 2026-09-05  
**Parent study:** `research/MASTERMIND_PERSONAL_PRO_EXECUTIVE_CONVERGENCE_2026-09-05.md`  
**Program:** MAS-48 / Personal-Pro Mastermind Executive Surface Convergence  
**Status:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`  
**Capability:** the program remains `PARTIAL`; Personal-Pro production reads and parity are not accepted.

## 0. Narrow purpose and supersession

This amendment corrects one source-level statement in parent study §2.3.

The parent says readonly `GatewayConfig.runtime_root` **defaults** to the selected repository root. At protected Mastermind `767409b6d3e7103a3b11428b870357d4a01bbe26`, the coupling is stronger:

> the readonly Executive MCP has no independently configurable runtime-root coordinate; lifecycle reads are bound to `repo_root` by the current gateway contract.

This amendment supersedes only the weaker word **defaults** and any inference that an operator can point readonly lifecycle reads at a separate canonical production Runtime through existing configuration. It does not supersede:

- the existing-MCP-reuse-first decision;
- the A/B/C/D Personal-account client test;
- PR #99's Personal-Pro shell architecture;
- the transport-neutral hot-state / `MMX/SOL_STATE_V1` contract;
- C1's original effect-unknown state or RuntimeBinding;
- S0-R1, B2 or C2 gates;
- the authenticated Executive app's existing owners;
- any current host, tunnel, account or service authority.

No source implementation, configuration, runtime, account, tunnel, credential or production behavior changes through this records-only amendment.

## 1. Exact current source finding

The evidence was read from the same protected commit, not inferred from documentation alone.

### 1.1 `GatewayConfig` has one read root

`integrations/executive_mcp/adapter.py` defines readonly configuration with:

```text
mode
repo_root
fixture
macro_root_flag
bind_host
boot_packet_timeout
max_response_bytes
now
```

There is no independent readonly `runtime_root` field.

Its property is:

```python
@property
def runtime_root(self) -> Path:
    if self.fixture is not None:
        return Path(self.fixture.runtime_root)
    return self.repo_root
```

`load_gateway_config(...)` permits only:

```text
fixture
macro_root
bind_host
boot_packet_timeout
repo_root
```

Therefore an operator cannot select one repository/grounding root and a different lifecycle-runtime root in readonly mode through the existing contract.

### 1.2 All four reads inherit the coupling

The gateway's rich state and inbox path calls:

```text
ceo_boot_packet.build_packet(repo_root=config.repo_root, ...)
executive_inbox.build_inbox(repo_root=config.repo_root, ...)
```

The Job and intent-status tools call the runtime factory with:

```text
config.runtime_root
```

which is the same `repo_root` in readonly mode.

`control_plane/executive_inbox.py` independently defines the Runtime database as:

```text
data/control_plane/executive.sqlite3
```

relative to the one supplied `repo_root`, checks that database without creating it, and opens it with `Runtime.at(root, create=False)`.

Consequently:

```text
executive_state
executive_inbox
executive_job
ceo_intent_status
```

all derive lifecycle data from the same selected repository root under current readonly composition.

### 1.3 The authenticated Executive app inherits the same read path

`integrations/mastermind_executive_app/gateway.py` deliberately reuses `ExecutiveMcpGateway` for the four read tools. Its `read_only_gateway_config(repo_root)` constructs:

```python
GatewayConfig(mode=ServerMode.READONLY, repo_root=Path(repo_root))
```

It does not supply another Runtime coordinate. The app's dedicated CeoIngress write client does not fix or alter its read-root coupling.

### 1.4 The client cannot prove this away

The MCP server advertises the static five-tool surface and correct read/write annotations. The client can establish whether it scans, exposes, enables and invokes those tools. It cannot determine merely from `tools/list`, `ok=true`, `generated_at`, server mode or a successful fixture result that the selected root is the canonical installed production Runtime.

A lawful deployment could intentionally co-locate reviewed repository inputs and the canonical Runtime database beneath one root. Current source does not prove that the Chairman host does or does not use such a mapping. That is a native host fact.

## 2. Evidence currently available

Historical receipts establish only bounded observations:

- the September 4 BSC tunnel was ready but served fixture mode from checkout `7191702e3b0104525b6b26cd30ddb53d89a8a663`;
- the September 5 Production qualification again observed fixture mode and an absent Runtime database at that reviewed checkout;
- root-owned production database/configuration remained unknown behind permissions rather than proven absent;
- the existing W3C host operation owns the approved root-only census and has not yet returned a production read binding;
- no actual Personal-Pro Executive tool invocation has been performed by this program.

These facts do **not** establish:

- that production has no Runtime database;
- that the current tunnel still serves the same source;
- that no lawful single-root mapping exists;
- that Personal Pro rejects the mixed manifest;
- that a source repair is already authorized;
- that rich MCP orientation can replace diagnostic admission hot state.

## 3. Revised proof matrix

The Personal-account canary now has two independent verdict axes.

### 3.1 Client / product axis

| Case | Observation | Product conclusion |
|---|---|---|
| A | unchanged server scans and four reads can be invoked | client reuse is viable; no production-root conclusion |
| B | reads work and modify invocation is platform-blocked | reuse reads; retain a separate selected write carrier |
| C | controlled evidence proves the mixed manifest rejects the whole server | permit the smallest read-only projection of the same schemas/gateway after excluding association/auth/tunnel/schema failures |
| D | account permits modify invocation | prove inert/fixture behavior and confirmations; technical availability is not production authority |

### 3.2 Runtime-root axis

| Case | Observation | Architecture conclusion |
|---|---|---|
| R0 | owner-native evidence proves selected `repo_root` is intentionally the canonical installed Runtime root | reuse existing gateway unchanged for qualified reads |
| R1 | selected repository root and canonical Runtime root are distinct | current readonly gateway cannot provide canonical lifecycle reads without a bounded existing-owner correction |
| R2 | root identity or database access remains unavailable/ambiguous | show degraded/unavailable; no source change or false-green canary |
| R3 | existing accepted owner-native service already supplies the required canonical read without this coupling | reuse that service through the existing MCP boundary rather than adding another backend |

A complete result is one client case plus one root case. Client Case A with root Case R2 is not production-read acceptance.

## 4. Smallest lawful correction, only if R1 is proved

The default remains **no source implementation before the native census**.

If the host proves R1, the repair must extend existing owners rather than create an API or Runtime sibling. The architecture review chooses the smaller compatible path:

### Path 1 — closed read-root coordinate inside the existing gateway

Introduce one host-controlled, non-request read-root coordinate that is separate from repository source/grounding inputs.

Conceptually:

```text
repo_root
  -> protected source identity
  -> boot packet / Agent OS / Macro grounding

runtime_read_root
  -> existing Runtime.at(..., create=False)
  -> Executive Inbox lifecycle projection
  -> Job and intent-status registries
```

The coordinate must be:

- operator-controlled, never a model/tool argument;
- absolute, normalized and bound to the accepted installed Runtime owner;
- readonly and `create=False` for every access;
- one value shared by state, inbox, Job and intent-status reads;
- absent from external error text and response fields except a closed non-secret generation/label;
- separately freshness- and source-attributed;
- incompatible with fixture write configuration unless the existing fixture contract explicitly owns it;
- inherited by the authenticated Executive app through the same gateway, not copied into another parser.

`executive_inbox.build_inbox` would need the smallest explicit separation between repository inputs and the Runtime read root. It must not silently change every caller, create a second inbox, migrate a database or make a missing Runtime look empty.

### Path 2 — existing owner-native canonical read service

Where an already accepted Executive diagnostic/read service supplies the same canonical data and security boundary, adapt only transport/composition so the existing MCP invokes that service. Reuse its schema, authentication, freshness and error contract. Do not expose the broad Operator socket, read SQLite directly from a Relay, or create a second service solely for the plugin.

### Rejected corrections

- another Executive MCP backend;
- a copied production database beneath a repository checkout;
- an empty Runtime created to make reads green;
- a symlink or bind trick that hides root identity from receipts;
- a Slack jobs database or plugin state store;
- a second Executive Inbox implementation;
- direct Relay SQLite reads;
- a public Internet endpoint solely for private Personal-Pro access;
- changing `generated_at` to mask stale backend data;
- removing `SOL_STATE` from write preflight merely because rich reads work.

## 5. Acceptance contract for any later source repair

A later implementation wave is independently useful only when it proves one real canonical read journey. At minimum:

1. RED reproduces R1 against the existing gateway: repository source is current while the canonical Runtime database is at a distinct approved root.
2. Configuration accepts exactly one non-request read root and refuses malformed, ambiguous, symlinked or unapproved coordinates according to the existing owner law.
3. `executive_state` and `executive_inbox` preserve repository/Macro grounding while taking lifecycle rows from the approved Runtime root.
4. `executive_job` and `ceo_intent_status` use that identical Runtime root.
5. All Runtime access stays `create=False`; before/after filesystem and logical Runtime digests prove zero write, migration, chmod, journal or lifecycle effect attributable to the reader.
6. Missing/unreadable/wrong-schema databases remain named degradation or typed refusal, never zero counts.
7. Fixture mode and its production-path refusal remain byte/behavior compatible unless separately reviewed.
8. The authenticated Executive app reuses the same corrected read composition.
9. External output exposes no absolute host path, token, credential, raw configuration or traceback.
10. A real Personal-Pro invocation returns source/mode/schema/root-generation/freshness receipts and agrees with an independent owner-native Runtime read.
11. Diagnostic hot-state/admission coverage is measured separately; no write-preflight retirement follows automatically.
12. Exact-head CI, security review, independent non-author review and real-account production proof are all distinct gates.

A merged correction without item 10 is `BUILT_NOT_PROVEN`. It is not Personal-Pro parity.

## 6. Program ordering after this correction

```text
current native host/root census
  -> Personal-account unchanged-manifest canary
     -> client Case A/B/C/D
     -> root Case R0/R1/R2/R3
        -> R0/R3: reuse, no source repair
        -> R1: smallest existing-owner read-root correction
        -> R2: remain degraded/blocked
  -> architecture freeze for rich read vs hot-state roles
  -> original C1 reconciliation and S0-R1 proof
  -> one selected production modification carrier
  -> harmless admission canary
  -> full Personal-Pro CEO journey and paired parity matrix
```

The account canary and host census may proceed independently where their authorities are disjoint, but final production-read acceptance requires their evidence to join.

## 7. Durable ruling and current effect

This amendment makes one technical source coupling explicit. It does not decide that a repair is required, does not select Path 1 or Path 2, and does not release a build wave.

Current verdict:

```text
existing five-tool MCP implementation: BUILT_NOT_PROVEN
Personal-Pro client behavior: DARK_OR_DISCONNECTED
canonical production read-root binding: DARK_OR_DISCONNECTED
routine Personal-Pro CEO workflow: PARTIAL
second backend / copied Runtime / new state store: REJECTED_BY_DESIGN
```

No Job, Attempt, Worker, Event, RuntimeBinding, Wake, Slack command, app association, tunnel, service, database, credential or provider effect occurred.

## 8. Reproducible source manifest

All source files below were read at protected Mastermind `767409b6d3e7103a3b11428b870357d4a01bbe26`:

- `integrations/executive_mcp/adapter.py`, blob `4c2a48ca15bd535fdc0b9503bb9e5295da16e791`;
- `integrations/executive_mcp/server.py`, blob `c762b2951e4bdad8956b646df58f6cd4609aaf8d`;
- `integrations/executive_mcp/schemas.py`;
- `integrations/mastermind_executive_app/gateway.py`, blob `a9a072f983b01132118a73bd47f5d0db6e5b09ed`;
- `control_plane/executive_inbox.py`, blob `f9c92ad181c0c0dda0b70780d8956e90459495a1`;
- `docs/EXECUTIVE_MCP.md`, blob `608e8cd18804d595ad069ce5203fb5c0e6db11fc`;
- `research/EXECUTIVE_OS_PERSONAL_PRO_RELAY_STATE_TRANSPORT_AMENDMENT_2026-08-20.md`, blob `be525a94be465abd220cc5a4a8651dd617e3b2f9`;
- `research/MASTERMIND_SOL_EXECUTIVE_SHELL_PRO_NATIVE_ARCHITECTURE_2026-08-20.md`, blob `88e295b5ec25be28e216bb734c0b068093529c45`.

Historical evidence references:

- Mastermind PR #482 comment `5550334229`;
- Slack `C0BSBM78V1N/1788507455.090679`;
- Slack `C0BSBM78V1N/1788521402.466429`;
- Personal-Pro census `C0BSBM78V1N/1788605608.765019`.

Action-time source, host and account evidence must be re-read before any implementation or production edge.
