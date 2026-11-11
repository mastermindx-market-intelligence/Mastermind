# Grok Operations Full Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver one production-proven Grok Operations Bot that receives exact Mastermind Wake obligations, uses the existing Company Consultation fabric for current evidence and bounded helpers, returns one governed answer to the correct requester, and can later perform explicitly delegated operational continuation without becoming another control plane.

**Architecture:** Inbound work uses the existing Wake ledger/route/RuntimeBinding system and one `grok-computer` webhook adapter. Outbound answers and helper requests use the protected four-tool Company Consultation facet and W6-C runtime. A separate authenticated HTTP composition exposes only those four tools; Executive OS, Agent OS, Capacity, Dialogue, Wake, GitHub, and Control Room retain their existing ownership.

**Tech Stack:** Python 3.12+, existing Mastermind Executive Runtime/Wake/RuntimeBinding, MCP SDK already pinned by the repository, existing Business OAuth resource-server stack, Streamable HTTP, existing service/launchd and Secure MCP Tunnel owners, Grok Bot webhook routines and custom MCP.

**Specs:** `docs/superpowers/specs/2026-09-14-grok-bot-autonomy-foreman-design.md` plus controlling amendment `docs/superpowers/specs/2026-09-14-grok-bot-autonomy-infrastructure-amendment.md`.

## Global Constraints

- Current review pin for this plan: protected Mastermind `af9fce32861f9c1496b85a580e3569712170d92b`; re-pin Skillpack and current source before every modifying child.
- W6-C2 PR #615 exact head `97634130d4bd69c3592502b2bb0e71829c55405c` is `RELEASE_BLOCKED` by exact review `5196352060`. Do not implement against its draft schema, effect reducer, ingress, or answer lineage until the same carrier returns a protected accepted interface.
- Tasks 2 and 3 are the only C0-parallel source waves: they consume the already-protected generic Wake contract only and must remain unregistered, unarmed, provider-secret-free in fixtures, and incapable of claiming delivery or target consumption. Task 1 and Tasks 4 onward remain C0-gated.
- Executive OS remains the only Job/Attempt/Worker/Event lifecycle and admission authority.
- W6-C remains the only consultation/result lineage. No Grok callback database, queue, result store, retry service, or memory owner.
- The Executive five-tool app remains unchanged. Company Consultation is a distinct four-tool app and scope.
- One initial Bot, one active parent, one active consultation answer, zero forwarding/nested helpers.
- Webhook bodies contain opaque IDs only. No task prose, credentials, private paths, account IDs, or customer data.
- HTTP 200 from the Grok routine means provider accepted/start only. It never means target consumption, answer availability, work acceptance, or completion.
- Any ambiguous post-submit effect is `EFFECT_UNKNOWN`; reconcile the same nudge/target and never retry or fail over automatically.
- Provider/account/plan/client/mode/data/budget eligibility is re-read at action time. No subscription allowance or paid overflow is inferred.
- Source protection, install, connection, provider call, native consumption, production proof, and final acceptance are separate states.
- Every source task uses TDD; every operational task records exact immutable source/install/provider identities and negative proof.
- No production-admin browser login, generic SSH, local Mac actuation, OpenClaw upgrade, source-write connector, billing change, or on-demand usage change is part of G0–G6.

---

## Gate C0: Repair and protect the W6-C2 consultation return interface

**Carrier:** existing PR #615 only. No replacement PR, branch, result store, callback service, queue, retry plane, or provider path is permitted.

**Current exact blocker:** review `5196352060` on `97634130d4bd69c3592502b2bb0e71829c55405c`. Green CI is not acceptance. The repair must close all of these owners together:

- protected consultation-schema compatibility, including exact old v1 frames and fingerprints;
- real managed-current-writer composition through the existing Wake dispatcher and fixed attention instruction;
- exact persisted Wake attempt and typed provider-observation causality before semantic dispatch/native credit;
- one coherent reducer for restart, late-result reconciliation, projection, and downstream credit;
- canonical RuntimeBinding/current-writer evidence rather than a partial parallel SQL definition;
- exact stored requester/recipient/binding/correlation/artifact identity before answer availability;
- exact available-answer fingerprint and semantic digest before requester consumption;
- atomic one-answer and one-consumption reservation;
- trusted-time expiry/lateness and non-crediting correction/history behavior.

- [ ] Re-read protected master, exact #615 head, all unresolved reviews/threads/checks, and the seven-path delta.
- [ ] Preserve old v1 byte behavior or introduce an explicit new schema version and compatibility dispatch; retaining the string `v1` is not compatibility.
- [ ] Replace free-form/direct Codex attention with the canonical Wake/current-writer path, stable persisted nudge identity, fixed instruction, and opaque IDs only.
- [ ] Make consultation effect-bearing facts derive from the exact Wake attempt/provider observation; arbitrary WAKE-looking IDs and invented turn IDs must produce zero credit.
- [ ] Use one effect reducer and explicit same-attempt late-result reconciliation. No history may be simultaneously unblocked and `EFFECT_UNKNOWN`.
- [ ] Require canonical non-empty semantic fingerprints at Runtime ingress.
- [ ] Bind answer/correction availability to the stored request and atomically reserve the sole accepted slot.
- [ ] Require requester consumption to match the exact available answer fingerprint and semantic digest.
- [ ] Add fail-first controls for foreign requester, foreign recipient/binding, same-key changed answer, blank fingerprint, concurrent answers, expiry, correction history, restart/ABA, and real-adapter instruction/nudge identity.
- [ ] Run focused, 17-file importer, native round-trip, isolated-entrypoint, current-protected integrated, hosted `test`, and security checks on one immutable final head.
- [ ] Obtain fresh non-author Sol review and protect or explicitly supersede the accepted interface.
- [ ] Record the protected commit, complete schema table, exact public symbols, and no-rebuild boundaries in PR #624 before Task 1 or Task 4 begins.

**Stop:** C0 passes only when the exact return path has one canonical effect owner and exact result lineage. Tasks 2 and 3 may proceed independently; Task 1 and Tasks 4–17 remain held.

---

### Task 1: Add an honest Grok reasoning surface using the next lawful schema version

**Prerequisite:** Gate C0 PASS with an immutable protected consultation schema table. Do not assume `v2` is unused.

**Files:**
- Modify: `common/agent_dialogue_consultation_contract.py`
- Modify: `control_plane/session_targets.py`
- Modify: `integrations/slack_agent_dialogue/company_consultation_peer_resolver.py`
- Modify: `tests/test_agent_dialogue_consultation_contract.py`
- Modify: `tests/test_session_targets.py`
- Modify: `tests/test_company_consultation_peer_resolver.py`

**Interfaces:**
- Consumes the complete protected schema/version table returned by C0.
- Defines `GROK_CONSULTATION_SCHEMA` as the next unused version after the protected latest schema.
- Preserves every protected schema's accepted/rejected bytes, canonical JSON, fingerprints, budgets, correction behavior, and peer projections.
- Adds `grok-bot` only to `GROK_CONSULTATION_SCHEMA` and to the closed SessionTarget reasoning-surface vocabulary.
- Derives schema selection from the trusted current peer/RuntimeBinding projection, never model arguments.

- [ ] **Step 1: Freeze all protected compatibility vectors before adding Grok**

Build a corpus from exact protected frames and expected results/fingerprints for every existing schema generation. Tests must read literal frozen vectors rather than rebuilding expected fingerprints through the candidate implementation.

```python
@pytest.mark.parametrize("frame, expected", PROTECTED_CONSULTATION_VECTORS)
def test_all_protected_consultation_vectors_are_unchanged(frame, expected) -> None:
    assert classify_protected_vector(frame) == expected
```

- [ ] **Step 2: Write the failing Grok-version tests**

```python
def test_protected_schemas_reject_grok_without_changing_other_results() -> None:
    for schema in PROTECTED_CONSULTATION_SCHEMAS:
        with pytest.raises(ConsultationContractError):
            validate_consultation(
                consultation_fixture(schema=schema, reasoning_surface="grok-bot")
            )


def test_next_schema_accepts_only_attested_grok_surface() -> None:
    frame = consultation_fixture(
        schema=GROK_CONSULTATION_SCHEMA,
        reasoning_surface="grok-bot",
    )
    assert validate_consultation(frame)["recipient_binding"]["reasoning_surface"] == "grok-bot"
```

Run the focused contract/peer suites and require the new Grok case to fail while every frozen protected vector remains green.

- [ ] **Step 3: Add the closed schema/surface mapping**

Read the protected version table at action time. Add exactly one new constant for Grok; never rename, alias, or mutate a protected generation. Keep any legacy `CONSULTATION_SCHEMA` alias bound to its protected meaning.

```python
GROK_CONSULTATION_SCHEMA = next_unused_consultation_schema(
    PROTECTED_LATEST_CONSULTATION_SCHEMA
)
_REASONING_SURFACES_BY_SCHEMA = {
    **PROTECTED_REASONING_SURFACES_BY_SCHEMA,
    GROK_CONSULTATION_SCHEMA: frozenset(
        {*PROTECTED_LATEST_REASONING_SURFACES, "grok-bot"}
    ),
}
```

The code need not use this illustrative helper name; the implementation must use a closed literal version accepted in review, not calculate a schema dynamically at runtime.

- [ ] **Step 4: Add `grok-bot` to SessionTarget vocabulary only**

Do not add a target, dispatcher registration, workstream route, implementation bit, or production arm in this task.

- [ ] **Step 5: Make peer schema selection host-derived**

A Grok-bound peer receives the exact new schema only when the current typed peer/RuntimeBinding projection says `reasoning_surface == "grok-bot"`. Every protected surface keeps its protected schema behavior. Unknown or unattested surfaces refuse.

- [ ] **Step 6: Run compatibility, peer, and target suites**

```bash
python3 -m pytest \
  tests/test_agent_dialogue_consultation_contract.py \
  tests/test_company_consultation_peer_resolver.py \
  tests/test_session_targets.py \
  -q -p no:randomly -p no:cacheprovider -o addopts=''
```

Run the complete importer family for the touched contract and demonstrate that mutating one protected vector or fingerprint makes the compatibility test fail.

- [ ] **Step 7: Commit the one-version source wave**

```bash
git add common/agent_dialogue_consultation_contract.py \
  control_plane/session_targets.py \
  integrations/slack_agent_dialogue/company_consultation_peer_resolver.py \
  tests/test_agent_dialogue_consultation_contract.py \
  tests/test_company_consultation_peer_resolver.py \
  tests/test_session_targets.py
git commit -m "feat(consultation): add versioned Grok reasoning surface"
```

**Acceptance:** a real Grok-bound Worker/Attempt can be represented honestly with zero changed result in every protected consultation generation and without enabling execution.

---

### Task 2: Add the provider-free Grok Wake dispatcher

**Files:**
- Create: `integrations/executive_wake/grok_bot_routine.py`
- Create: `tests/test_grok_bot_routine_wake_dispatcher.py`

**Interfaces:**

```python
@dataclasses.dataclass(frozen=True)
class GrokRoutineWakeObservation:
    native_handle: str
    nudge_id: str
    accepted: bool
    request_id: str | None = None

@runtime_checkable
class GrokRoutineWakeClient(Protocol):
    async def deliver_wake(
        self,
        *,
        native_handle: str,
        nudge_id: str,
        binding_id: str,
        binding_generation: int,
        opaque_ids: Sequence[str],
    ) -> GrokRoutineWakeObservation: ...

@runtime_checkable
class GrokRoutineObservationSource(Protocol):
    async def observe_wake(
        self,
        *,
        native_handle: str,
        nudge_id: str,
    ) -> GrokRoutineWakeObservation | None: ...

class GrokBotRoutineWakeDispatcher:
    transport_id = "grok-computer"
    reasoning_surface = "grok-bot"
```

The dispatcher implements the existing `WakeDispatcher.nudge(wake)` and optional `reconcile(wake)` shape. It can return only ACCEPTED, TARGET_UNAVAILABLE, or FAILED. It never claims DELIVERED because webhook acceptance is not target consumption.

- [ ] **Step 1: Write failing adapter tests**

Cover: wrong type, missing native handle, wrong transport, wrong reasoning surface, accepted exact observation, provider refusal, pre-submit typed failure, post-call exception -> `WakeEffectUnknownError`, mismatched handle/nudge -> `WakeEffectUnknownError`, missing observation source, and reconciliation returning the exact accepted observation.

- [ ] **Step 2: Run the new test module**

```bash
python3 -m pytest tests/test_grok_bot_routine_wake_dispatcher.py -q -p no:randomly -o addopts=''
```

Expected: collection fails because the module does not exist.

- [ ] **Step 3: Implement the minimal typed dispatcher**

Use `TransportReceipt`, `TransportOutcome`, `WakeNudge`, `WakePreSubmitError`, `WakeEffectUnknownError`, and `utc_now_iso` from existing owners. Build `opaque_ids` as existing obligation IDs plus attempt command IDs. Validate returned `native_handle` and `nudge_id` exactly.

- [ ] **Step 4: Prove no false delivery**

Add an assertion that even `accepted=True` yields:

```python
assert receipt.outcome is TransportOutcome.ACCEPTED
assert receipt.reason_code == "accepted"
```

No test may produce `TransportOutcome.DELIVERED` from this adapter.

- [ ] **Step 5: Run adapter and generic Wake protocol suites**

```bash
python3 -m pytest \
  tests/test_grok_bot_routine_wake_dispatcher.py \
  tests/test_codex_app_server_wake_dispatcher.py \
  tests/test_executive_wake_persisted_dispatch.py \
  -q -p no:randomly -o addopts=''
```

- [ ] **Step 6: Commit**

```bash
git add integrations/executive_wake/grok_bot_routine.py \
  tests/test_grok_bot_routine_wake_dispatcher.py
git commit -m "feat(wake): add inert Grok routine dispatcher"
```

**Acceptance:** provider-independent source can convert one exact WakeNudge into one accepted Grok routine submission without implementing network, secrets, target enabling, or production routing.

---

### Task 3: Add the bounded webhook HTTP client and secret-resolution seam

**Files:**
- Create: `integrations/executive_wake/grok_bot_http.py`
- Create: `tests/test_grok_bot_routine_http.py`

**Interfaces:**

```python
@dataclasses.dataclass(frozen=True, repr=False)
class GrokRoutineCredential:
    url: str
    bearer_token: str = dataclasses.field(repr=False)
    generation: int
    target_digest: str

@runtime_checkable
class GrokRoutineCredentialSource(Protocol):
    def resolve(self, native_handle: str) -> GrokRoutineCredential: ...

@dataclasses.dataclass(frozen=True)
class BoundedHttpResult:
    status_code: int
    body: bytes
    request_id: str | None

@runtime_checkable
class BoundedJsonPoster(Protocol):
    async def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> BoundedHttpResult: ...

class GrokRoutineHttpClient(GrokRoutineWakeClient):
    ...
```

**Closed constants:** schema `mastermind.grok_bot_wake.v1`, 16 KiB request ceiling, 16 KiB response ceiling, 15-second deadline, HTTPS only, no URL credentials/query/fragment, no redirects, and no automatic retry.

- [ ] **Step 1: Write failing credential and request tests**

Cover: missing/blank/multiline token, non-HTTPS URL, embedded username/password, query/fragment, generation < 1, target-digest mismatch, oversized body/response, redirect status, 200 accepted, every non-200 definite no-start, token/body redaction, and post-call network exception -> effect unknown at the dispatcher.

- [ ] **Step 2: Run the HTTP tests**

```bash
python3 -m pytest tests/test_grok_bot_routine_http.py -q -p no:randomly -o addopts=''
```

Expected: collection fails because the module is absent.

- [ ] **Step 3: Implement deterministic payload construction**

```python
def grok_wake_payload(
    *,
    nudge_id: str,
    binding_id: str,
    binding_generation: int,
    opaque_ids: Sequence[str],
) -> bytes:
    return canonical_json_bytes(
        {
            "schema": "mastermind.grok_bot_wake.v1",
            "nudge_id": nudge_id,
            "binding_id": binding_id,
            "binding_generation": binding_generation,
            "opaque_ids": list(opaque_ids),
            "company_consultation_server": "mastermind-company-consultation-mcp",
        }
    )
```

Reject all unknown input fields at the caller boundary. Never pass the bearer token to logging, exceptions, dataclass repr, receipts, or response bodies.

- [ ] **Step 4: Implement one POST**

Resolve the credential once, set exactly `Content-Type: application/json` and `Authorization: Bearer <token>`, and call the injected poster once. Map 200 to `GrokRoutineWakeObservation(accepted=True)`. Map non-200 to `WakePreSubmitError` because documented provider semantics say a run did not start. If the poster raises after invocation, let the dispatcher classify `EFFECT_UNKNOWN`.

- [ ] **Step 5: Run HTTP and dispatcher suites**

```bash
python3 -m pytest \
  tests/test_grok_bot_routine_http.py \
  tests/test_grok_bot_routine_wake_dispatcher.py \
  -q -p no:randomly -o addopts=''
```

- [ ] **Step 6: Commit**

```bash
git add integrations/executive_wake/grok_bot_http.py \
  tests/test_grok_bot_routine_http.py
git commit -m "feat(wake): add bounded Grok webhook client"
```

**Acceptance:** exact provider request bytes and secrets are separated from RuntimeBinding and Wake receipts; one HTTP 200 yields acceptance only.

---

### Task 4: Compose an inert Grok target without arming production

**Prerequisites:** Gate C0 PASS and Task 1 protected. The generic dispatcher source alone is not sufficient.

**Files:**
- Modify: `config/wake_session_targets.json`
- Modify: `integrations/executive_wake/registry.py`
- Modify: `tests/test_session_targets.py`
- Modify: `tests/test_executive_wake_registry.py`
- Modify: `tests/test_wake_transport.py`

**Interfaces:**
- Adds logical target `EXECUTIVE-COO-GROK-A` with `reasoning_surface=grok-bot`, `wake_transport=grok-computer`, `target_enabled=false`.
- Registers an injected `GrokBotRoutineWakeDispatcher` only when supplied by trusted composition.
- Leaves `WAKE_TRANSPORT_DESCRIPTORS["grok-computer"].transport_implemented` false.
- Leaves registry `production_armed` false.

- [ ] **Step 1: Write failing target/registry tests**

Assert the new alias parses, requires a matching Grok RuntimeBinding, refuses Codex/Claude/ChatGPT bindings, and remains non-deliverable because both target and transport are disabled.

- [ ] **Step 2: Run target/registry tests**

```bash
python3 -m pytest \
  tests/test_session_targets.py \
  tests/test_executive_wake_registry.py \
  tests/test_wake_transport.py \
  -q -p no:randomly -o addopts=''
```

- [ ] **Step 3: Add the exact disabled target and injected registry seam**

Do not change default COO routing. No workstream points to Grok in checked-in policy. The registry accepts an explicitly injected Grok dispatcher but canonical transport checks continue to refuse delivery while `transport_implemented=false`.

- [ ] **Step 4: Prove source presence cannot arm execution**

```python
route = route_obligation(obligation, registry, binding=grok_binding)
assert route.reasoning_surface == "grok-bot"
assert route.wake_transport == "grok-computer"
assert route.transport_implemented is False
assert route.target_enabled is False
assert route.delivery_allowed is False
```

- [ ] **Step 5: Run suites and commit**

```bash
python3 -m pytest \
  tests/test_session_targets.py \
  tests/test_executive_wake_registry.py \
  tests/test_wake_transport.py \
  tests/test_grok_bot_routine_wake_dispatcher.py \
  -q -p no:randomly -o addopts=''

git add config/wake_session_targets.json integrations/executive_wake/registry.py \
  tests/test_session_targets.py tests/test_executive_wake_registry.py \
  tests/test_wake_transport.py
git commit -m "feat(wake): add disabled Grok logical target"
```

**Acceptance:** Grok has an honest logical identity but remains impossible to route in production.

---

### Task 5: Build the authenticated remote Company Consultation app

**Prerequisite:** Gate C0 PASS. Bind only to the protected W6-C runtime and result lineage.

**Files:**
- Create: `integrations/mastermind_company_mcp/http_app.py`
- Create: `integrations/mastermind_company_mcp/installed.py`
- Create: `tests/test_company_consultation_http_app.py`
- Create: `tests/test_company_consultation_installed.py`
- Modify: `integrations/mastermind_company_mcp/__init__.py`

**Interfaces:**

```python
COMPANY_CONSULTATION_SCOPE = "mastermind.company.consultation"

@dataclasses.dataclass(frozen=True)
class CompanyConsultationAppSettings:
    policy: ResourcePolicy
    gateway: CompanyConsultationGateway
    authenticator: JwtAuthenticator
    audit_sink: AuthAuditSink
    host: str = "127.0.0.1"
    max_request_bytes: int = 65536
    max_response_bytes: int = 262144


def create_company_consultation_app(
    settings: CompanyConsultationAppSettings,
) -> Any: ...


def build_installed_company_consultation_gateway(
    *,
    runtime: ConsultationRuntime,
    peer_resolver: CompanyConsultationPeerResolver,
    utc_now: Callable[[], str],
    program_ref: str,
) -> CompanyConsultationGateway: ...
```

Use the existing `build_company_consultation_mcp_server()` and Business OAuth stack. Do not expose the six Company Dialogue tools or the five Executive tools in this app.

- [ ] **Step 1: Write failing exact-inventory and OAuth tests**

Cover: metadata route, exact scope, exact four-tool inventory, read/write annotations, missing/extra/wrong scope, wrong audience/issuer/subject, duplicate Authorization, malformed/oversized/multipart body, non-loopback bind refusal, unavailable runtime/peer resolver, gateway exception redaction, and zero Executive/Dialogue tool leakage.

- [ ] **Step 2: Run the new app tests**

```bash
python3 -m pytest \
  tests/test_company_consultation_http_app.py \
  tests/test_company_consultation_installed.py \
  -q -p no:randomly -o addopts=''
```

Expected: collection fails before implementation.

- [ ] **Step 3: Implement the stateless ASGI composition**

Authenticate every MCP call before dispatch. Use one `CompanyConsultationGateway`; retain no app-local consultation, token, peer, or replay state. Enforce actual received-byte ceilings, complete-response buffering, fixed opaque errors, and shutdown of owned gateway resources.

- [ ] **Step 4: Implement installed gateway composition over W6-C**

The installed dispatcher maps the four semantic operations onto the protected W6-C2 runtime and current Company Dialogue carrier. It must not call provider APIs, create Jobs, or infer current peer identity from model arguments.

- [ ] **Step 5: Run app, W6-C, and auth suites**

```bash
python3 -m pytest \
  tests/test_company_consultation_http_app.py \
  tests/test_company_consultation_installed.py \
  tests/test_company_consultation_mcp.py \
  tests/test_agent_dialogue_consultation_contract.py \
  tests/test_business_mcp_auth_integration.py \
  -q -p no:randomly -o addopts=''
```

- [ ] **Step 6: Commit**

```bash
git add integrations/mastermind_company_mcp/http_app.py \
  integrations/mastermind_company_mcp/installed.py \
  integrations/mastermind_company_mcp/__init__.py \
  tests/test_company_consultation_http_app.py \
  tests/test_company_consultation_installed.py
git commit -m "feat(company-mcp): expose authenticated consultation facet"
```

**Acceptance:** a remote authenticated client can see and call only the four existing consultation tools through the current runtime; no Grok-specific return service exists.

---

### Task 6: Add sealed installation, launcher, audit, and tunnel composition

**Files:**
- Create: `ops/executive_os/company_consultation_mcp_entry.py`
- Create: `scripts/mastermind_company_consultation_app.py`
- Create: `config/business_mcp/company_consultation_policy.example.json`
- Modify: `ops/executive_os/control.json.template`
- Modify: `ops/executive_os/install.sh`
- Create: `tests/test_company_consultation_mcp_entry.py`
- Modify: `tests/test_executive_launchd_config.py`
- Create: `docs/runbooks/mastermind-company-consultation-app.md`

**Interfaces:**
- Dedicated installed component ID `company-consultation-mcp`.
- Dedicated least-privilege service principal/uid under the existing installer owner.
- Root-owned sealed release/config; Python `-I -B`; loopback bind only.
- Existing durable auth audit sink.
- One separately configured Secure MCP Tunnel/public HTTPS target; tunnel is reachability only.
- No secret in command arguments, repository, launchd plist, logs, or runbook.

- [ ] **Step 1: Write failing launcher/install tests**

Cover: exact source/release digest, exact policy path, explicit runtime root, loopback-only host, dedicated port, no defaults, no inherited Python path, no world-readable secrets, stale release/config refusal, unavailable W6-C runtime, and four-tool `--describe` output without binding a listener.

- [ ] **Step 2: Run the focused install tests**

```bash
python3 -m pytest \
  tests/test_company_consultation_mcp_entry.py \
  tests/test_executive_launchd_config.py \
  -q -p no:randomly -o addopts=''
```

- [ ] **Step 3: Implement the entry point and explicit CLI**

`--describe` reports server identity/version, tool schema digest, source release, required scope, and production-armed false without reading credentials or starting network service. Normal mode requires every coordinate explicitly and constructs the installed gateway/app once.

- [ ] **Step 4: Extend the existing installer composition**

Add the new component to `control.json.template` and `install.sh`; preserve existing Executive/Relay component identities and rollback. Installation creates no OAuth client or Grok connector automatically.

- [ ] **Step 5: Add the runbook**

Document source release, service installation, policy/issuer/client enrollment, tunnel association, intended Grok connector, rollback, revocation, log locations, and exact proof sequence. Use placeholders only for operator-supplied secret values in shell examples; never commit actual values. Do not use `TBD`/`TODO` language.

- [ ] **Step 6: Run install/app suites and commit**

```bash
python3 -m pytest \
  tests/test_company_consultation_mcp_entry.py \
  tests/test_executive_launchd_config.py \
  tests/test_company_consultation_http_app.py \
  tests/test_company_consultation_installed.py \
  -q -p no:randomly -o addopts=''

git add ops/executive_os/company_consultation_mcp_entry.py \
  scripts/mastermind_company_consultation_app.py \
  config/business_mcp/company_consultation_policy.example.json \
  ops/executive_os/control.json.template ops/executive_os/install.sh \
  tests/test_company_consultation_mcp_entry.py \
  tests/test_executive_launchd_config.py \
  docs/runbooks/mastermind-company-consultation-app.md
git commit -m "feat(company-mcp): add sealed consultation deployment"
```

**Acceptance:** exact source can be installed and exposed through the existing auth/tunnel architecture without connecting Grok or arming a worker.

---

### Task 7: Add Grok capability profile and provider-setup attestation

**Files:**
- Create: `config/grok_bot_operations.json`
- Modify: `config/executive_agent_capabilities.json`
- Modify: `control_plane/executive_agent_capabilities.py`
- Create: `control_plane/grok_bot_attestation.py`
- Create: `tests/test_grok_bot_attestation.py`
- Modify: `tests/test_executive_agent_capabilities.py`
- Create: `docs/runbooks/grok-bot-operations-setup.md`

**Interfaces:**

```python
GROK_BOT_ATTESTATION_SCHEMA = "mastermind.grok_bot_attestation.v1"

@dataclasses.dataclass(frozen=True)
class GrokBotAttestation:
    account_ref: str
    bot_ref: str
    profile_digest: str
    company_mcp_server_identity: str
    company_mcp_tool_schema_digest: str
    company_mcp_connection_generation: int
    routine_ref: str
    routine_instruction_digest: str
    routine_generation: int
    local_execution_enabled: bool
    on_demand_enabled: bool | None
    observed_at: str
```

The public receipt contains pseudonymous refs/digests only. It includes no email, webhook URL/key, OAuth token, subscription ID, browser cookie, internal endpoint, or raw provider output.

`config/grok_bot_operations.json` freezes:

- profile version/name/title;
- Sentinel and Foreman modes;
- exact Company Consultation server identity/tool digest;
- routine name and instruction digest;
- local execution expected false;
- one-Bot roster;
- forbidden connectors/actions;
- expected accepted source release.

- [ ] **Step 1: Write failing schema/profile tests**

Cover unknown fields, wrong tool digest, local execution true, missing routine generation, blank IDs, raw email/URL/token-like values, on-demand unknown/false/true projection, and exact public serialization.

- [ ] **Step 2: Run tests**

```bash
python3 -m pytest \
  tests/test_grok_bot_attestation.py \
  tests/test_executive_agent_capabilities.py \
  -q -p no:randomly -o addopts=''
```

- [ ] **Step 3: Add the unarmed capability profile**

Profile ID: `grok-operations-consultation-v1`. Enable only the four Company Consultation tools. Forbid source writes, credential/admin/billing changes, production deploy, PR merge, arbitrary network, generic shell, Job creation, provider selection, and acceptance authority. Keep production/autonomous flags false.

- [ ] **Step 4: Implement deterministic attestation validation**

Validate exact expected digests/generations. The validator consumes operator/provider observations and emits the redacted public receipt; it does not log in, create the Bot, connect MCP, or create routines.

- [ ] **Step 5: Write the owner setup runbook**

Include: verify the intended Cursor user and usage grant; create one Bot; paste the exact source-controlled profile; keep local execution off; connect only the Company Consultation MCP; complete OAuth; verify exactly four tools; create the webhook routine inactive; securely transfer URL/key to existing secret custody; record redacted attestation; test revocation; and leave every modifying connector absent.

- [ ] **Step 6: Run and commit**

```bash
python3 -m pytest \
  tests/test_grok_bot_attestation.py \
  tests/test_executive_agent_capabilities.py \
  tests/test_company_consultation_mcp_entry.py \
  -q -p no:randomly -o addopts=''

git add config/grok_bot_operations.json \
  config/executive_agent_capabilities.json \
  control_plane/executive_agent_capabilities.py \
  control_plane/grok_bot_attestation.py \
  tests/test_grok_bot_attestation.py \
  tests/test_executive_agent_capabilities.py \
  docs/runbooks/grok-bot-operations-setup.md
git commit -m "feat(grok): add unarmed operations profile and attestation"
```

**Acceptance:** Mastermind can distinguish the intended Bot/profile/connector/routine generation from an arbitrary Grok account without storing provider secrets or granting runtime authority.

---

### Task 8: Project Grok Operations in the existing Control Room

**Files:**
- Modify: `control_plane/autonomy_control_room_projection.py`
- Modify: `control_plane/chairman_control_room.py`
- Modify: `tests/test_autonomy_control_room_projection.py`
- Modify: `tests/test_chairman_control_room.py`

**Interfaces:**

```python
@dataclasses.dataclass(frozen=True)
class GrokOperationsProjection:
    session_alias: str
    reasoning_surface: str
    binding_generation: int | None
    binding_freshness: str
    wake_state: str
    consultation_state: str
    routine_state: str
    capability_state: str
    budget_state: str
    blocker_code: str | None
    needs_owner: str | None
    evidence_refs: tuple[str, ...]
```

This is a pure composition over existing Wake, RuntimeBinding, W6-C, capability/attestation, Capacity, and GitHub facts. It has no persistence and does not infer liveness.

- [ ] **Step 1: Write failing projection tests**

Cover no target, disabled source-only target, configured/unconnected, accepted wake/no consumption, consumed/no answer, answer/requester consumed, stale binding, `EFFECT_UNKNOWN`, paused routine, unknown budget, and forbidden raw secret/question/answer leakage.

- [ ] **Step 2: Run focused tests**

```bash
python3 -m pytest \
  tests/test_autonomy_control_room_projection.py \
  tests/test_chairman_control_room.py \
  -q -p no:randomly -o addopts=''
```

- [ ] **Step 3: Implement pure projection and render one responsibility block**

Use current source timestamps and explicit unknown/degraded values. Never derive running state from a provider routine being active or a Wake receipt being accepted.

- [ ] **Step 4: Run and commit**

```bash
python3 -m pytest \
  tests/test_autonomy_control_room_projection.py \
  tests/test_chairman_control_room.py \
  -q -p no:randomly -o addopts=''

git add control_plane/autonomy_control_room_projection.py \
  control_plane/chairman_control_room.py \
  tests/test_autonomy_control_room_projection.py \
  tests/test_chairman_control_room.py
git commit -m "feat(control-room): project Grok operations truthfully"
```

**Acceptance:** Chris can see whether Grok is configured, called, consumed, answered, blocked, stale, or uncertain without reading provider UI and without making Control Room an authority.

---

### Task 9: Complete exact-head integration and source release

**Files:** all paths from Tasks 1–8 only.

- [ ] Run compile on every changed Python path:

```bash
python3 -m py_compile $(git diff --name-only --diff-filter=ACMR origin/master...HEAD -- '*.py')
```

- [ ] Run focused complete Grok/W6-C/Wake/auth/Control Room suite:

```bash
python3 -m pytest \
  tests/test_agent_dialogue_consultation_contract.py \
  tests/test_company_consultation_peer_resolver.py \
  tests/test_company_consultation_mcp.py \
  tests/test_grok_bot_routine_wake_dispatcher.py \
  tests/test_grok_bot_routine_http.py \
  tests/test_session_targets.py \
  tests/test_executive_wake_registry.py \
  tests/test_wake_transport.py \
  tests/test_executive_wake_persisted_dispatch.py \
  tests/test_company_consultation_http_app.py \
  tests/test_company_consultation_installed.py \
  tests/test_company_consultation_mcp_entry.py \
  tests/test_grok_bot_attestation.py \
  tests/test_executive_agent_capabilities.py \
  tests/test_autonomy_control_room_projection.py \
  tests/test_chairman_control_room.py \
  tests/test_business_mcp_auth_integration.py \
  -q -p no:randomly -o addopts=''
```

- [ ] Run repository-required hosted CI/security on the exact head.
- [ ] Obtain independent architecture/security review covering secret custody, effect uncertainty, v1 compatibility, auth scope, duplicate owners, and false-green claims.
- [ ] Reconcile protected movement using exact changed paths and material-source comparison; do not merge master merely to report `behind_by=0`.
- [ ] Protect source with expected-head guard.
- [ ] Record state as `BUILT_NOT_PROVEN / PRODUCTION_INERT / NOT_INSTALLED`; do not flip the transport descriptor.

**Acceptance:** all required source is protected, exact-head verified, and still impossible to route in production.

---

### Task 10: Install and qualify the Company Consultation service

**Authority:** separate installation operation on the intended Executive host. No Bot/provider call yet.

- [ ] Bind the exact protected source SHA, configuration digest, service uid, policy ID, issuer/resource/scope, runtime root, port, and tunnel association.
- [ ] Install through the existing installer and confirm source/config seals, process identity, loopback listener, auth audit sink, and rollback package.
- [ ] Through the public HTTPS/tunnel path, prove OAuth metadata and exact four-tool inventory with an authorized fixture principal.
- [ ] Prove missing/wrong/extra scope, wrong audience/issuer/subject, revoked principal, stale release/config, oversized body/response, and backend unavailable.
- [ ] Restart service and tunnel; prove consultations remain in the existing W6-C runtime rather than app memory.
- [ ] Capture a redacted installation receipt. No Grok account is connected yet.

**Stop:** installed authenticated four-tool service is `BUILT_NOT_PROVEN / INSTALLED / GROK_NOT_CONNECTED`, or a named install/auth/tunnel blocker.

---

### Task 11: Configure one Grok Operations Bot and inactive routine

**Authority:** explicit owner/admin setup using `docs/runbooks/grok-bot-operations-setup.md`.

- [ ] Verify the intended Cursor user, plan/linked grant, weekly usage, on-demand state, and privacy setting. Do not enable or raise on-demand usage in this operation.
- [ ] Confirm the user is dedicated when separate credentials are required; otherwise record the shared-computer ceiling.
- [ ] Create exactly one Bot named `Grok Operations` and apply the exact source-controlled profile/version.
- [ ] Keep local execution off; install no broad browser/admin/source-write plugins.
- [ ] Add the custom Company Consultation MCP public URL and complete OAuth for the dedicated principal.
- [ ] Verify exactly four tools and the expected schema digest; call `company.peers` against an isolated authorized fixture.
- [ ] Create the webhook routine with the exact source-controlled instruction and leave it inactive until negative tests are prepared.
- [ ] Transfer URL/key through the existing secret handoff/custody path; store neither value in chat, GitHub, logs, or the Bot description.
- [ ] Generate and validate the redacted `GrokBotAttestation` receipt.
- [ ] Revoke and re-connect the Company MCP once to prove access can be removed without losing company state.

**Stop:** `BUILT_NOT_PROVEN / BOT_CONFIGURED / ROUTINE_INACTIVE`; no Executive Wake call and no claim of autonomous continuity.

---

### Task 12: Prove the first read-only returned-work journey

**Input:** one non-production returned-work obligation with a real current parent and immutable evidence.

- [ ] Create/admit the exact Grok Worker/Attempt and RuntimeBinding with the disabled logical target in a fixture/canary runtime.
- [ ] Deliver the obligation manually to the Bot without enabling canonical Wake; confirm it resolves only the assigned consultation/context.
- [ ] Require Sentinel output to distinguish known, unknown, normal wait, missing review, missing production proof, and reserved decision.
- [ ] Return one answer through Company Consultation and prove NATIVE_ACCEPTED, CONSUMED_BY_RECIPIENT, ANSWER_AVAILABLE, and CONSUMED_BY_REQUESTER in the existing runtime.
- [ ] Confirm the current parent accepts or rejects the answer explicitly and the Control Room projection matches.
- [ ] Prove wrong root/binding, stale artifact, revoked scope, and Company MCP unavailable.

**Stop:** `G0_READ_RETURN_PASS` or the exact connection/context/identity blocker. This does not yet implement Wake.

---

### Task 13: Prove the exact webhook Wake journey while still unarmed

**Input:** one isolated canary obligation; explicit provider-call authorization; routine active only for the finite proof.

- [ ] Activate the one routine and bind its exact routine generation to a new RuntimeBinding generation.
- [ ] Use a fixture/manual dispatcher composition despite the canonical descriptor remaining false; do not alter production routing.
- [ ] Send one exact webhook nudge. Capture provider HTTP status and request/run reference without logging the key/body secrets.
- [ ] Verify HTTP 200 records Wake ACCEPTED only.
- [ ] Verify the Bot consumes the intended consultation, returns its answer, and the requester consumes it.
- [ ] Prove non-200 definite no-run; wrong key; inactive routine; wrong binding generation; duplicate same nudge; changed payload conflict; post-submit lost response -> `EFFECT_UNKNOWN`; late provider evidence reconciliation without another POST.
- [ ] Pause the routine and prove canonical obligation/result state remains server-side.

**Stop:** `G1_WAKE_RETURN_PASS`, with transport still source-disabled, or a precise provider/identity/effect blocker.

---

### Task 14: Promote the Grok transport and target through a separate guarded release

**Files:**
- Modify: `control_plane/wake_transport.py`
- Modify: `config/wake_session_targets.json`
- Modify: `tests/test_wake_transport.py`
- Modify: `tests/test_session_targets.py`
- Modify: `tests/test_executive_wake_persisted_dispatch.py`

- [ ] Write failing tests requiring `transport_implemented=true` only for exact accepted source/install/provider receipt digests supplied by the production composition owner.
- [ ] Set the descriptor implementation bit only after Task 13 proof is accepted.
- [ ] Enable only `EXECUTIVE-COO-GROK-A`; leave every old `chatgpt-sol`/`grok-computer` placeholder disabled.
- [ ] Preserve global production disarm until the final exact production canary; use the existing environment/release owner for the production-armed policy.
- [ ] Run Wake/target/registry/full focused suites and hosted checks.
- [ ] Obtain independent release review and expected-head protection.
- [ ] Install the exact release, arm one canary policy, repeat Task 13 through canonical Wake, then either accept or roll back to disabled state.

**Acceptance:** one exact Grok target can receive canonical Wake; no other target or provider becomes armed by implication.

---

### Task 15: Prove one economical helper consultation

**Input:** one bounded evidence-comparison task whose answer is independently checkable.

- [ ] Ask `company.peers` for the current program; do not specify provider/account/model in prompt text.
- [ ] Confirm Capacity/Router/provider owner selects a route whose account/plan/client/mode and data rights permit this use and whose overflow cannot create unapproved spend.
- [ ] Call `company.consult` with one peer, one question, at most four evidence refs, and exact artifact revisions.
- [ ] Validate returned identity, evidence, scope, answer budget, and semantics. Provider/model success does not bypass validation.
- [ ] Where a naturally invalid first answer occurs, use the current correction path at most once; do not sabotage production to manufacture repair evidence.
- [ ] Have Grok synthesize the validated answer into its parent consultation and prove requester consumption.
- [ ] Prove zero forwarding, nested helper, source write, credential access, paid fallback, and provider self-selection.

**Stop:** `G2_HELPER_PASS` with measured usage basis and limitations, or the exact provider/budget/quality blocker.

---

### Task 16: Enable one event-driven responsibility and delegated operational decisions

**Prerequisites:** Tasks 14–15 accepted; #612 current delegation envelope and decision classes serviceable.

- [ ] Select one narrow material event class: a returned-work obligation awaiting evidence-based triage. Do not use a busy Slack keyword listener or periodic model polling.
- [ ] Bind the current parent, allowed decision classes, expiry, budget, active-child/repair ceiling, source scope, and stop condition in the existing authority owners.
- [ ] Permit Grok only `recommend`, `request_review`, `request_bounded_repair`, `continue_within_frozen_plan`, and `park_affected_dependency` where current source law admits them.
- [ ] Refuse thesis/architecture/priority/budget expansion, acceptance waiver, provider admission, production release, credentials, live capital, and Chairman-reserved decisions.
- [ ] Run one event while the initiating Web Sol conversation is inactive. Prove work/review/one repair/current-parent consumption and an explicit terminal or nonterminal edge.
- [ ] Prove Bot paused, usage exhausted, auth revoked, strategic question, and lost operational principal preserve durable obligations and independent native work.
- [ ] Project the outcome in Control Room and update Agent OS/GitHub evidence.

**Stop:** `G3_OPERATIONAL_CONTINUITY_PASS`; additional event classes, Bots, accounts, or authority require new bounded waves.

---

### Task 17: Evaluate ROI, harden, and close out

- [ ] Freeze the matched evaluation sample and promotion thresholds before reading outcomes.
- [ ] Compare direct qualified-worker execution, Grok-only triage, and Grok-plus-helper only for lawful matched task classes.
- [ ] Measure accepted useful outcomes, human interventions, requester-consumption latency, first-pass quality, repairs, false escalations, missed obligations, Grok usage basis, helper usage/cost, duplicate effects, and authority violations.
- [ ] Keep account-wide meter uncertainty explicit; do not invent per-run savings.
- [ ] Red-team prompt injection, stale memory, connector drift, tunnel outage, secret leakage, broad egress, shared-computer access, routine pause, provider UI change, and effect-unknown recovery.
- [ ] Accept, restrict, or reject each role/route independently. Remove any surface whose coordination cost or risk exceeds its value.
- [ ] Update Mastermind architecture/evidence, Agent OS decision/discovery/handoff, selected Linear projection, and bounded Slack visibility.
- [ ] Terminally close every worker/watcher cycle; record exact next action and do-not-redo laws.

**Final acceptance:** the real user/machine journey works end to end, Grok can disappear without losing company state, no duplicate owner was introduced, and measured value justifies the continuing allowance and operational role.
