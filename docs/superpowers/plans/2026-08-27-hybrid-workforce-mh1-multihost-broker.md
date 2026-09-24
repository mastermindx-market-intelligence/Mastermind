# MH1 Authenticated Multi-Host Worker Broker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the one canonical Executive Runtime execute an already-claimed Attempt on a host-local Worker Broker on M1/M2/PC through one authenticated private transport, while keeping provider credentials local, preserving exact Attempt identity, and treating remote uncertainty as `EFFECT_UNKNOWN` rather than cross-host retry permission.

**Architecture:** MH1 extends the existing typed Worker Broker protocol across a mutually authenticated TLS transport. The remote gateway is a stateless transport proxy: it authenticates the control principal/host binding, validates one closed request envelope, and forwards the existing broker request to the host-local AF_UNIX broker. It owns no Job/Attempt/Worker state, queue, retry ledger, cursor, provider routing, or credential. Endpoint/certificate material is root-managed local configuration, not Provider Capacity truth and not checked-in lifecycle identity. Executive OS remains on one control host. The existing Worker claim and Capacity Fabric `host_ref` determine which host transport is lawful before the network call.

**Tech Stack:** Python 3.11+ stdlib `ssl`, sockets/asyncio, existing Executive Worker Broker, existing Executive Runtime, pytest.

**Spec:** `docs/superpowers/specs/2026-08-27-executive-workforce-hybrid-role-topology-design.md`

## Global Constraints

- Execute only after HF1 is accepted and current Capacity Fabric host/Worker claim law is re-pinned.
- One canonical Executive Runtime/database/queue remains on the control host. Remote hosts do not run an Executive scheduler or lifecycle database.
- Provider credentials/auth homes remain on the remote worker host and are accessed only by the host-local reviewed adapter/broker.
- Do not use GitHub Actions, tmux, Slack, generic SSH commands, shared writable filesystems, or remote shell access as lifecycle/execution authority.
- Remote timeout/disconnect after a modifying broker operation begins is `EFFECT_UNKNOWN`; never repeat the modifying operation or move the Attempt to another host until the same Attempt is reconciled.
- One logical operation keeps one `Attempt`/Worker/host binding until canonical reconciliation.
- Do not widen Phase 1F-C `placement_snapshot_json`; host transport evidence is separate bounded execution evidence.
- Private IPs/hostnames/certificate paths do not enter `mastermind.provider_capacity.v1`, Agent OS, Slack, or public receipts.
- No new external dependencies unless a concrete stdlib TLS limitation is proven and separately reviewed.

---

### Task 1: Freeze the remote broker envelope and local transport binding

**Files:**
- Create: `control_plane/remote_worker_transport.py`
- Create: `tests/test_remote_worker_transport.py`

**Interfaces:**
- `REMOTE_BROKER_REQUEST_SCHEMA = "mastermind.remote_worker_broker_request/v1"`
- `REMOTE_BROKER_RESPONSE_SCHEMA = "mastermind.remote_worker_broker_response/v1"`
- `BrokerTransportBinding` is runtime/local-config input only.
- `RemoteBrokerRequest` binds the existing Executive/Worker operation identity to an exact payload hash.

- [ ] **Step 1: Write RED contract tests**

Pin the request shape to exactly:

```text
schema
host_ref
job_id
attempt_id
worker_id
operation_id
broker_operation
request_sha256
broker_request
```

and the response shape to exactly:

```text
schema
host_ref
job_id
attempt_id
worker_id
operation_id
request_sha256
outcome
broker_response
observed_at
```

`operation_id` is a stable bounded identity supplied by the Executive operation/Attempt context; it is not minted by the remote host.

Refuse unknown keys, malformed IDs, changed payload under the same operation identity, mismatched request hash, and response identity drift.

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_remote_worker_transport.py -q
```

- [ ] **Step 3: Implement canonical JSON/hash and closed validation**

Use stdlib canonical JSON (`sort_keys=True`, compact separators, `allow_nan=False`) and SHA-256. Never place certificate material, endpoint address, provider home or credential in the envelope.

- [ ] **Step 4: Define local transport binding**

```python
@dataclasses.dataclass(frozen=True)
class BrokerTransportBinding:
    host_ref: str
    endpoint_host: str
    endpoint_port: int
    expected_server_certificate_sha256: str
    client_certificate_path: Path
    client_private_key_path: Path
    ca_certificate_path: Path
    timeout_seconds: float = 30.0
```

This object is loaded only from root-managed control-host configuration and must be redacted from durable/public receipts. `host_ref` must equal the already-selected Capacity Fabric/Worker host identity; the network endpoint cannot create or change host identity.

- [ ] **Step 5: Run GREEN and commit**

```bash
python -m pytest tests/test_remote_worker_transport.py -q

git add control_plane/remote_worker_transport.py tests/test_remote_worker_transport.py
git commit -m "feat(exec): freeze remote worker transport contract"
```

---

### Task 2: Implement the stateless mTLS remote gateway

**Files:**
- Create: `ops/executive_os/remote_worker_gateway.py`
- Create: `ops/executive_os/remote_worker_gateway_config.py`
- Create: `tests/test_remote_worker_gateway.py`

**Interfaces:**
- Gateway authenticates mutual TLS, validates fixed host/control identities, and forwards one request to the existing local `WorkerBrokerClient`/AF_UNIX broker.
- Gateway stores no lifecycle/retry state.

- [ ] **Step 1: Write gateway security tests**

Use local test certificates/temporary sockets and assert refusal for:

```text
no client certificate
wrong client certificate/CA
server certificate mismatch at client
host_ref mismatch
worker_id outside gateway allowlist
unknown broker operation
malformed/oversized envelope
request hash mismatch
attempt/job/worker identity mismatch
attempt to address an arbitrary local Unix socket
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_remote_worker_gateway.py -q
```

- [ ] **Step 3: Implement root-managed gateway configuration**

The checked-in loader/schema accepts local configuration fields for the exact `host_ref`, fixed listen address/port, certificate/key/CA paths, expected control-client certificate identity/fingerprint, one fixed local worker-broker socket path, and allowed Worker ids. Production config values remain off Git.

- [ ] **Step 4: Implement one-request forwarding**

For each authenticated connection:

1. read one bounded length-prefixed request;
2. validate mTLS peer and closed envelope;
3. verify configured host/Worker identity;
4. forward only the embedded existing broker operation/request to the fixed local AF_UNIX broker;
5. frame one response bound to the original request hash/Attempt/operation ids;
6. close the network connection.

No remote shell, argv, file read/write API, provider selection, worktree discovery, queue or generic socket proxy.

- [ ] **Step 5: Add restart/no-persistence test**

Restart the gateway between two read-only status operations and prove it needs no cursor/database/history to answer; lifecycle comes from Executive/broker/provider state, not the gateway.

- [ ] **Step 6: Run GREEN and commit**

```bash
python -m pytest tests/test_remote_worker_gateway.py -q

git add ops/executive_os/remote_worker_gateway.py ops/executive_os/remote_worker_gateway_config.py tests/test_remote_worker_gateway.py
git commit -m "feat(exec): add stateless mTLS worker gateway"
```

---

### Task 3: Implement the control-side remote broker client

**Files:**
- Create: `control_plane/remote_worker_broker_client.py`
- Create: `tests/test_remote_worker_broker_client.py`
- Modify: `control_plane/remote_codex_operator_adapter.py`

**Interfaces:**
- `RemoteWorkerBrokerClient` presents the same typed `request_sync(operation, payload, ...)` behavior consumed by existing remote/operator adapter seams, but binds every call to an existing Job/Attempt/Worker/host operation context.
- No automatic retry for modifying broker operations.

- [ ] **Step 1: Write client identity tests**

Assert that the client refuses construction/call when its bound `host_ref`, Job, Attempt or Worker is missing/malformed. One client instance is bound to one current Attempt/Worker/host operation context; it cannot be reused to target a different active Attempt by changing request payload.

- [ ] **Step 2: Write timeout semantics tests**

For modifying operations (`start`, `cancel`, `ohf-start`, `ohf-resume`, `ohf-begin-turn`, `ohf-interrupt`, `ohf-stop`, provider-equivalent mutations), simulate:

```text
connect failure before request write -> typed unavailable/no effect
full request written + response lost -> EFFECT_UNKNOWN, zero retry
partial/unknown write -> EFFECT_UNKNOWN, zero retry
```

Read-only `status`/`reconcile` may be performed later as new explicitly identified read operations against the same Attempt/host; they are not a replay of the modifying operation.

- [ ] **Step 3: Implement mTLS connection and response authentication**

Use an `ssl.SSLContext` configured for client certificate verification and server hostname/cert validation plus the reviewed fingerprint check. Bound request/response sizes and timeouts. Validate every returned identity/hash before exposing the embedded broker response.

- [ ] **Step 4: Reuse the existing adapter seam**

Make `RemoteCodexOperatorAdapter` depend on the structural broker-client interface rather than concrete AF_UNIX-only `WorkerBrokerClient`, so the same Codex App Server adapter can operate over local or MH1 transport without duplicating OHF/session semantics.

- [ ] **Step 5: Run tests**

```bash
python -m pytest \
  tests/test_remote_worker_broker_client.py \
  tests/test_remote_worker_gateway.py \
  tests/test_remote_worker_transport.py \
  tests/test_codex_operator_adapter.py \
  -q
```

- [ ] **Step 6: Commit**

```bash
git add control_plane/remote_worker_broker_client.py control_plane/remote_codex_operator_adapter.py tests/test_remote_worker_broker_client.py
git commit -m "feat(exec): add authenticated remote broker client"
```

---

### Task 4: Bind remote execution to the already-claimed Worker/host

**Files:**
- Modify: `control_plane/executive_supervisor.py`
- Modify: `tests/test_executive_operator_supervisor.py`
- Modify: `tests/test_executive_os_runtime.py`
- Modify: `tests/test_remote_worker_broker_client.py`

**Interfaces:**
- Existing Runtime/CF2 claim selects the Worker before transport resolution.
- Runtime/local composition resolves that Worker's accepted `host_ref` to one `BrokerTransportBinding`.
- Network transport cannot select or change Worker/provider/account/model.

- [ ] **Step 1: Add placement/transport separation tests**

Prove:

```text
worker claim exists before transport binding
remote endpoint cannot change worker_id/provider/model/account_label
host_ref mismatch between selected Worker/capacity evidence and transport binding refuses
no endpoint available -> Job remains canonically claimed/blocked according to existing runtime law; no second Worker is silently selected
```

Do not add host/address fields to the frozen `placement_snapshot_json`.

- [ ] **Step 2: Add same-Attempt reconciliation tests**

When a remote modifying response is `EFFECT_UNKNOWN`, require the supervisor/controller to keep the same Attempt/Worker/host identity and perform the existing status/reconcile path. A different Worker/host may receive later work only after the original Attempt reaches a canonical terminal state permitting a new Attempt under current retry law.

- [ ] **Step 3: Implement only the transport-resolution seam**

Inject a `WorkerTransportResolver` into the control-side supervisor/composition. It maps the already-claimed Worker/host identity to either the existing local AF_UNIX client or one MH1 `RemoteWorkerBrokerClient`. It does not rank workers or observe quota.

- [ ] **Step 4: Run runtime/supervisor regressions**

```bash
python -m pytest \
  tests/test_executive_os_runtime.py \
  tests/test_executive_operator_supervisor.py \
  tests/test_remote_worker_broker_client.py \
  -q
```

- [ ] **Step 5: Commit**

```bash
git add control_plane/executive_supervisor.py tests/test_executive_operator_supervisor.py tests/test_executive_os_runtime.py tests/test_remote_worker_broker_client.py
git commit -m "feat(exec): bind remote transport after worker claim"
```

---

### Task 5: Use existing Worker capacity as the GUI/computer-use mutex

**Files:**
- Modify: `config/executive_agent_capabilities.json`
- Modify: `tests/test_executive_agent_capabilities.py`
- Modify: `tests/test_executive_operator_supervisor.py`

**Interfaces:**
- GUI/computer-use is an explicit execution capability/resource profile assigned only to Worker realms whose host environment provides an isolated actuator.
- The existing Worker `BUSY`/claim lifecycle provides exclusivity; no second GUI scheduler is created.

- [ ] **Step 1: Add resource-exclusivity tests**

Pin one capability id/profile for an interactive desktop actuator using the existing capability registry naming conventions. Assert two concurrent Jobs cannot claim the same single Worker realm merely because both request GUI capability. A second independent isolated desktop must be represented by a second eligible Worker/resource realm, not by a hidden port/mutex table.

- [ ] **Step 2: Preserve Browser Resource Fabric ownership**

The profile grants only the right to request the already-governed browser/devserver/computer-use resource. It does not give a worker access to Chairman browser profiles, arbitrary external internet, or a second actuator.

- [ ] **Step 3: Run tests and commit**

```bash
python -m pytest \
  tests/test_executive_agent_capabilities.py \
  tests/test_executive_operator_supervisor.py \
  -q

git add config/executive_agent_capabilities.json tests/test_executive_agent_capabilities.py tests/test_executive_operator_supervisor.py
git commit -m "test(exec): bind GUI exclusivity to worker capacity"
```

---

### Task 6: One remote-host canary, then three-host proof

**Files:**
- Add only root-owned local service templates/install scripts and sanitized proof artifacts required by current operations convention.

- [ ] **Step 1: Security/install preparation**

On one non-control host, create a dedicated local gateway principal/service with minimal filesystem access, private-interface firewall rules and mTLS material through a human/admin secret ceremony. Never commit certificate private keys or private endpoint addresses.

- [ ] **Step 2: Read-only handshake canary**

From the control host, authenticate one remote status/identity request through mTLS -> gateway -> fixed AF_UNIX worker broker. Prove exact host_ref, Worker and certificate identities without starting provider work.

- [ ] **Step 3: One bounded remote Executive child Job**

Use a harmless low-risk task. Prove:

```text
one canonical Job/Attempt on control host
→ one already-selected remote Worker/host
→ mTLS remote broker request
→ host-local adapter and credentials
→ real result
→ response authentication
→ canonical terminal transition on control host
```

No remote lifecycle DB/queue.

- [ ] **Step 4: Kill-point/effect-unknown drill**

Drop the network after the remote host accepts a modifying request but before the control host receives the response. Prove there is no blind resend or other-host failover; reconciliation stays with the same Attempt/host until canonical outcome is known.

- [ ] **Step 5: Extend to M1/M2/PC**

After the first remote host passes, independently install/attest the same gateway contract on the other eligible machines. Each host has its own certificate/host_ref/Worker realm/provider credentials. Do not clone credentials or one runtime database.

- [ ] **Step 6: Three-host fan-out proof**

Create one root Job with at least three bounded independent child Jobs when current policy/independence permits. Claim them on three distinct eligible host Worker realms and prove concurrent execution/return while the single control-host Executive Runtime remains the only lifecycle owner.

- [ ] **Step 7: Hosted tests and adversarial review**

Run:

```bash
python -m pytest \
  tests/test_remote_worker_transport.py \
  tests/test_remote_worker_gateway.py \
  tests/test_remote_worker_broker_client.py \
  tests/test_executive_os_runtime.py \
  tests/test_executive_operator_supervisor.py \
  tests/test_executive_worker_broker.py \
  -q
python -m compileall -q control_plane ops/executive_os

git diff --check
```

Require hosted CI/CodeQL and independent security review of mTLS identity, private endpoint exposure, request replay/effect-unknown law, credential locality, and absence of remote lifecycle state.

- [ ] **Step 8: Return to Sol**

Return exact code head, host classes (opaque), gateway/client binary/config digests, certificate identity fingerprints only where safe, one-host and three-host Job/Attempt/Worker receipts, kill-point reconciliation proof, tests/CI/security verdict, and explicit `ONE EXECUTIVE RUNTIME / ZERO REMOTE QUEUES`.

## Stop Condition

MH1 stops when one canonical Executive Runtime can drive authenticated host-local brokers across M1/M2/PC, provider credentials remain local, a remote response-loss drill proves same-Attempt reconciliation with no cross-host retry, and real multi-host child work completes through the existing lifecycle. It does not create host-local Executive schedulers or a generic remote shell.
