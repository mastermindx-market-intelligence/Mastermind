# Astra External Fabric Delegation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make an Executive-owned Astra/Codex orchestrator offload bounded execution to the existing Mastermind Agent Fabric through the existing five-tool Executive MCP, complete one real external-provider work/review/result round trip, resume the exact Astra parent, and prove at least a 50% reduction in Astra + internal-Codex usage versus a comparable Codex-heavy baseline.

**Architecture:** Preserve the frozen five-tool MCP and its existing authenticated Executive App admission path. `submit_ceo_intent` remains a bounded caller surface that the App converts to CeoIngress v2; Executive Runtime/COO/Capacity own execution and placement, qualified external adapters own work, and the existing Codex RuntimeBinding/Wake path owns exact parent continuation. Codex configuration and instructions only make Astra a client of those owners; they do not create a scheduler, lifecycle store, provider selector, or retry plane.

**Tech Stack:** Python 3.12, existing Mastermind Executive Runtime/CeoIngress/COO/Capacity, existing `integrations.executive_mcp` + `integrations.mastermind_executive_app`, MCP Streamable HTTP, Codex CLI MCP registration/OAuth, existing `CodexOperatorAdapter` + Wake/RuntimeBinding, pytest.

**Spec:** `docs/superpowers/specs/2026-09-14-astra-external-fabric-delegation-design.md`

## Global Constraints

- Implementation base must be freshly rebased/recovered from protected `master`; the freeze was authored against `cf4c082d83fffe35daee81aa3d30bd27450bacf1`, not treated as an eternal implementation base.
- Keep the existing five-tool Executive MCP input schemas and tool names unchanged for this vertical.
- Reuse `integrations.mastermind_executive_app.admission.compose_admission`; do not add another modifying sink or call `ceo_intent.submit_intent` from Codex-facing code.
- `submit_ceo_intent` must still return an admission receipt with `dispatched=false`; later execution is owned by the existing strict-v2 COO cycle.
- Astra never supplies provider, model, account, provider home, credential, endpoint, host, UID/GID, socket, worker ID, branch, worktree, raw authority, or raw validation argv.
- One modifying operation keeps one stable `operation_key`/derived `request_ref`; on `effect_unknown`, reconcile the same request and never fail over or mint a new key.
- Do not copy worker transcripts into Astra's normal context. Consume canonical bounded Job/result/review projections and pull more evidence only on demand.
- Existing repo-local Codex internal agents remain Terra/medium with maximum concurrency 3 unless a separate reviewed change amends them; they are fallback, not the primary worker fabric.
- Do not edit #583-owned provider binding files until #583 or its accepted successor is protected and source ownership is reconciled.
- Do not arm autonomous continuation beyond current accepted source law; #612 or an accepted successor must cover the operational interval before a production-like canary.
- Do not create another Job/Attempt store, scheduler, quota registry, auth store, retry journal, transcript store, Wake bus, provider-spawn MCP tool, or generic shell execution surface.
- Every modifying worker uses the workspace assigned by its current harness; attended Web/host execution uses `mmx-workspace`; do not mint nested worktrees.
- Production proof requires a real external provider call, canonical result/review evidence, exact Astra-parent consumption, and usage comparison. Unit tests alone are not acceptance.

---

## File Structure for This Vertical

The first source PR should be intentionally small and client-side:

- `ops/codex_fabric/register_executive_mcp.py` — idempotent, non-secret Codex MCP registration verifier/installer. It owns no auth token and no Executive state.
- `tests/test_codex_fabric_registration.py` — hermetic fake-`codex` tests for registration, collision refusal, and no-secret/no-retry behavior.
- `tests/test_astra_external_fabric_contract.py` — cross-layer regression pins proving the existing five-tool submit path still produces the existing CeoIngress v2 frame and refuses caller-selected provider/account fields.
- `AGENTS.md` — concise Astra principal/delegation policy; no new authority is introduced here.
- `docs/runbooks/codex-astra-fabric-delegation.md` — operator/acceptance procedure for registration, auth, exact-parent qualification, canary, failure behavior, and token-economics proof.

Do **not** modify `integrations/executive_mcp/schemas.py`, `control_plane/ceo_intent.py`, `control_plane/executive_runtime.py`, `control_plane/executive_coo_cycle.py`, provider binding files, or Capacity policy in the first source PR unless a failing discriminating test proves the current owner cannot satisfy the frozen design. Such a failure ends this plan at the named owner boundary; it is not permission to broaden the PR.

---

### Task 1: Pin the Existing Five-Tool-to-v2 Delegation Contract

**Files:**
- Create: `tests/test_astra_external_fabric_contract.py`
- Read only: `integrations/executive_mcp/schemas.py`
- Read only: `integrations/mastermind_executive_app/admission.py`
- Read only: `control_plane/executive_ceo_ingress.py`
- Read only: `control_plane/ceo_request.py`

**Interfaces:**
- Consumes: `schemas.validate_tool_arguments("submit_ceo_intent", payload)`, `admission.compose_admission(AdmissionRequest)`, `ceo_request.app_request_ref(operation_key)`, `ceo_ingress.SUBMIT_SCHEMA_V2`.
- Produces: a regression test module establishing that Codex can keep the five-tool public shape while the App emits the v2 automated frame, with stable identity and no caller-selected physical execution fields.

- [ ] **Step 1: Write the failing cross-layer tests before any implementation change**

Create `tests/test_astra_external_fabric_contract.py` with a recording fake `CeoIngressClient` and tests equivalent to the following behavior:

```python
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from control_plane import ceo_request, executive_ceo_ingress as ceo_ingress
from integrations.executive_mcp.schemas import GatewayError, validate_tool_arguments
from integrations.mastermind_executive_app.admission import (
    AdmissionRequest,
    compose_admission,
)
from integrations.mastermind_executive_app.gateway import CeoIngressResponse, TRANSPORT_SENT_OK


VALID = {
    "operation_key": "astra-external-fabric-contract-001",
    "objective": "Read the bounded source and return the requested evidence.",
    "department": "executive-infrastructure",
    "priority": 10,
    "execution_profile": "research_only",
}
GROUNDING = {
    "mastermind_sha": "1" * 40,
    "macro_sha": "2" * 40,
    "boot_packet_schema": "mastermind.ceo_boot_packet.v1",
}


@dataclasses.dataclass
class RecordingClient:
    frames: list[dict] = dataclasses.field(default_factory=list)

    async def send_frame(self, _path, frame):
        self.frames.append(dict(frame))
        return CeoIngressResponse(
            transport=TRANSPORT_SENT_OK,
            ok=True,
            result={"dispatched": False, "job_id": "JOB-1"},
            error=None,
        )


def test_frozen_submit_shape_refuses_physical_routing_fields():
    for forbidden in ("provider", "model", "account", "provider_home", "endpoint", "host"):
        payload = dict(VALID)
        payload[forbidden] = "attacker-choice"
        with pytest.raises(GatewayError):
            validate_tool_arguments("submit_ceo_intent", payload)


@pytest.mark.asyncio
async def test_app_turns_five_tool_submit_into_v2_automated_frame(monkeypatch, tmp_path):
    client = RecordingClient()
    principal = make_submit_principal()  # local helper in this test, exact scopes only
    monkeypatch.setattr(
        "integrations.mastermind_executive_app.admission.observe_trusted_grounding",
        lambda **_kwargs: dict(GROUNDING),
    )
    outcome = await compose_admission(
        AdmissionRequest(
            payload=VALID,
            principal=principal,
            ceo_ingress_socket_path=tmp_path / "ceo-ingress.sock",
            mastermind_root=tmp_path,
            macro_root_flag=None,
            environ={},
            client=client,
        )
    )
    assert outcome.request_ref == ceo_request.app_request_ref(VALID["operation_key"])
    assert outcome.receipt["dispatched"] is False
    assert len(client.frames) == 1
    frame = client.frames[0]
    assert frame["schema"] == ceo_ingress.SUBMIT_SCHEMA_V2
    assert frame["request_ref"] == outcome.request_ref
    assert "operation_key" not in frame["request"]
    assert frame["request"]["objective"] == VALID["objective"]
```

Use the repository's existing `VerifiedPrincipal` construction pattern from `tests/test_mastermind_executive_app_admission.py` for `make_submit_principal()`; do not invent a weaker principal fixture.

- [ ] **Step 2: Add identity/effect-unknown regression cases**

Add tests asserting:

```python
def test_app_request_ref_is_stable_and_domain_owned():
    first = ceo_request.app_request_ref(VALID["operation_key"])
    second = ceo_request.app_request_ref(VALID["operation_key"])
    assert first == second
    assert first.startswith("req-")


@pytest.mark.asyncio
async def test_effect_unknown_never_causes_a_second_submit(...):
    # Recording client returns TRANSPORT_SENT_UNKNOWN for submit.
    # Assert compose_admission returns status == "effect_unknown".
    # Assert exactly one submit frame was sent.
    # Reconciliation is exercised through reconcile_by_request_ref and sends
    # STATUS_SCHEMA_V2 with the same request_ref, never another SUBMIT_SCHEMA_V2.
```

- [ ] **Step 3: Run the focused tests and prove they are green against current source**

Run:

```bash
python3 -m pytest -q \
  tests/test_astra_external_fabric_contract.py \
  tests/test_mastermind_executive_app_admission.py \
  tests/test_executive_mcp_app_composition.py
```

Expected: all pass. If the new test proves the current five-tool App no longer emits CeoIngress v2, stop and return to architecture review; do not add a sixth tool to make the test pass.

- [ ] **Step 4: Commit the contract pin**

```bash
git add tests/test_astra_external_fabric_contract.py
git commit -m "test: pin Astra external Fabric admission contract"
```

---

### Task 2: Add a Safe Codex MCP Registration Helper

**Files:**
- Create: `ops/codex_fabric/register_executive_mcp.py`
- Create: `tests/test_codex_fabric_registration.py`

**Interfaces:**
- Consumes: installed `codex` executable with `mcp get`, `mcp add`, and `mcp login`; explicit operator-supplied Streamable HTTP URL from the accepted Executive MCP installation receipt.
- Produces: `register(server_url: str, codex_bin: str = "codex") -> RegistrationReceipt`, where the receipt records server name, normalized URL, whether an entry was created, and whether login remains required. No token or OAuth credential is returned or stored.

The fixed server name is `mastermind-executive`. The helper accepts only loopback HTTP URLs with literal path `/mcp`, no userinfo, query, or fragment. It must not read Executive root-owned config and must not guess the installed port.

- [ ] **Step 1: Write registration tests with a fake Codex binary**

The fake binary records argv to a temporary file and returns deterministic JSON for `mcp get`. Add these cases:

```python
def test_new_registration_uses_streamable_http_without_secret_arguments(tmp_path): ...
def test_matching_registration_is_idempotent_and_does_not_re_add(tmp_path): ...
def test_existing_different_url_refuses_instead_of_overwriting(tmp_path): ...
def test_non_loopback_or_non_mcp_url_refuses_before_running_codex(tmp_path): ...
def test_registration_never_passes_bearer_token_or_literal_secret(tmp_path): ...
def test_missing_codex_binary_is_closed_error(tmp_path): ...
```

For the create case, assert the exact child argv is:

```text
codex mcp add mastermind-executive --url http://127.0.0.1:<accepted-port>/mcp
```

The helper must **not** execute `codex mcp login` automatically. OAuth login is a distinct attended enrollment step because it may require the provider/browser flow; after enrollment, credentials belong to Codex's supported credential store rather than this script.

- [ ] **Step 2: Run the registration tests and observe RED**

Run:

```bash
python3 -m pytest -q tests/test_codex_fabric_registration.py
```

Expected: failure because `ops.codex_fabric.register_executive_mcp` does not exist.

- [ ] **Step 3: Implement the minimal helper**

Implement these types and functions:

```python
@dataclasses.dataclass(frozen=True)
class RegistrationReceipt:
    server_name: str
    url: str
    created: bool
    login_required: bool


class RegistrationError(RuntimeError):
    pass


def normalize_loopback_mcp_url(value: str) -> str: ...
def register(server_url: str, *, codex_bin: str = "codex") -> RegistrationReceipt: ...
```

Required behavior:

1. parse with `urllib.parse.urlsplit`;
2. require `scheme == "http"`;
3. require hostname in `{127.0.0.1, localhost, ::1}`;
4. require an explicit port in `1024..65535`;
5. require exact path `/mcp`, empty username/password/query/fragment;
6. call `[codex_bin, "mcp", "get", "mastermind-executive", "--json"]` once;
7. if a valid existing entry has exact URL and is enabled, return `created=False`;
8. if an entry exists with another URL/transport, raise `RegistrationError` and do not mutate it;
9. if the entry is absent, call `[codex_bin, "mcp", "add", "mastermind-executive", "--url", url]` exactly once, then `get --json` once to verify the saved result;
10. never put an auth token, policy content, provider credential, Executive socket path, or root-owned config path into argv/environment/config.

Use `stdin=DEVNULL`, bounded subprocess timeouts, and opaque error messages. A timeout after `mcp add` is **effect-unknown for Codex config**: re-read with `mcp get` before deciding whether another add is safe. Do not blindly issue `mcp add` twice.

- [ ] **Step 4: Run RED-to-GREEN and mutation checks**

Run:

```bash
python3 -m pytest -q tests/test_codex_fabric_registration.py
python3 -m compileall -q ops/codex_fabric
```

Then locally mutate the collision branch to allow overwriting a different URL and prove `test_existing_different_url_refuses_instead_of_overwriting` goes red; revert and rerun green.

- [ ] **Step 5: Commit the registration helper**

```bash
git add ops/codex_fabric/register_executive_mcp.py tests/test_codex_fabric_registration.py
git commit -m "feat: register Executive MCP for Codex safely"
```

---

### Task 3: Make External Fabric Delegation the Astra Default, Without Expanding Authority

**Files:**
- Modify: `AGENTS.md`
- Create: `docs/runbooks/codex-astra-fabric-delegation.md`
- Create: `tests/test_astra_delegation_source_policy.py`
- Read only: `.codex/config.toml`

**Interfaces:**
- Consumes: the current `submit_ceo_intent`, `executive_job`, `ceo_intent_status`, and Executive state/inbox tools.
- Produces: source-visible Astra operating instructions that define external-delegation eligibility, principal-retained work, effect-unknown handling, compact return behavior, and the bounded internal-Codex fallback.

- [ ] **Step 1: Write source-policy tests first**

Create `tests/test_astra_delegation_source_policy.py` that reads `AGENTS.md` and `.codex/config.toml` and asserts all of these invariants:

```python
assert "External Fabric delegation" in agents
assert "submit_ceo_intent" in agents
assert "never choose a provider" in agents.lower()
assert "effect_unknown" in agents
assert "full worker transcript" in agents.lower()
assert "internal Codex" in agents
assert 'max_concurrent_threads_per_session = 3' in codex_config
assert 'default_subagent_model = "gpt-5.6-terra"' in codex_config
assert 'default_subagent_reasoning_effort = "medium"' in codex_config
```

Also assert the new section does not contain the forbidden direct-execution strings `pool run`, `spawn_minimax`, `spawn_glm`, `provider_home=`, or `account=`.

- [ ] **Step 2: Run the policy test and observe RED**

```bash
python3 -m pytest -q tests/test_astra_delegation_source_policy.py
```

Expected: failure because the new policy section is absent.

- [ ] **Step 3: Add a concise `External Fabric delegation` section to `AGENTS.md`**

The section must state, in operational language:

```text
Astra/principal behavior:
- Keep intent recovery, architecture, cross-return judgment, exceptions, and final acceptance.
- For bounded independently executable research, implementation, tests, repair, or independent review, prefer the existing Executive Fabric via submit_ceo_intent before opening internal Codex subagents.
- Author objective/profile/write/test constraints only. Never choose a provider, model, account, credential home, endpoint, host, or worker identity.
- An accepted admission with dispatched=false is normal; execution belongs to the COO cycle.
- On effect_unknown, reconcile the same request identity; never mint a new key or switch transports/providers/internal agents until canonical settlement.
- Consume bounded Executive Job/result/review evidence. Do not replay a full worker transcript into the parent unless a specific acceptance contradiction requires it.
- Internal Codex agents are pre-effect fallback only when Fabric is unavailable or lacks the required capability; record the fallback reason.
```

Do not change hierarchy, authority, Agent OS ownership, delivery workflow, or provider policy elsewhere in `AGENTS.md`.

- [ ] **Step 4: Write the operator runbook**

`docs/runbooks/codex-astra-fabric-delegation.md` must give the exact first-vertical procedure:

1. verify current protected source/Skillpack and source-owner collisions;
2. obtain the accepted installed Executive MCP loopback URL from the current installation owner/receipt;
3. run the registration helper;
4. run `codex mcp get mastermind-executive --json` and require enabled Streamable HTTP with the exact URL;
5. perform supported OAuth enrollment once with `codex mcp login mastermind-executive` using the currently approved scopes/policy; do not paste credentials into config;
6. start a **fresh** Codex/Astra session after registration/auth changes and inspect `/mcp` or equivalent current tool census;
7. require exactly the expected five Executive tools and no caller-controlled provider field;
8. qualify the exact Astra parent as an Executive-owned current Codex Operator/RuntimeBinding before claiming unattended return;
9. run the baseline and delegated canaries in Task 6;
10. on any `effect_unknown`, use the same `request_ref` reconciliation path and stop other modifying actions until settled.

The runbook must explicitly say that a manually opened arbitrary Codex tab is not accepted parent proof unless the current RuntimeBinding identifies that exact native session/generation.

- [ ] **Step 5: Re-run tests and commit**

```bash
python3 -m pytest -q tests/test_astra_delegation_source_policy.py
git diff --check
git add AGENTS.md docs/runbooks/codex-astra-fabric-delegation.md tests/test_astra_delegation_source_policy.py
git commit -m "docs: make Executive Fabric Astra's default worker path"
```

---

### Task 4: Qualify the Exact Astra Parent and No-Poll Return Path

**Files:**
- Read/verify: `control_plane/codex_operator_adapter.py`
- Read/verify: `control_plane/session_targets.py`
- Read/verify: `control_plane/runtime_binding_projection.py`
- Read/verify: `integrations/executive_wake/codex_app_server_rpc.py`
- Extend tests only if needed: `tests/test_codex_app_server_wake_rpc.py`
- No production source change is authorized by this task unless an existing exact-parent behavior fails a discriminating test and the current owner explicitly accepts that repair scope.

**Interfaces:**
- Consumes: an Executive-owned current Codex `RuntimeBinding` with `reasoning_surface="codex"`, one exact process generation/native handle, and existing Wake attention delivery.
- Produces: evidence that the Astra orchestrator used for the canary is the exact bound native Codex session that can receive a result-driven continuation, with no newest-tab/latest-session fallback.

- [ ] **Step 1: Run the existing exact-session Wake regression**

```bash
python3 -m pytest -q \
  tests/test_codex_app_server_wake_rpc.py \
  tests/test_runtime_binding_projection.py \
  tests/test_wake_ack_ingress.py
```

Expected: green.

- [ ] **Step 2: Add one Astra-specific binding discriminator only if coverage is absent**

If the existing suite does not already assert all four properties below in one path, add a focused test to `tests/test_codex_app_server_wake_rpc.py`:

```text
reasoning_surface == "codex"
exact native_handle/thread id agrees
exact binding_generation/process_generation agrees
attention uses turn/start on that current writer and never thread/resume, thread/fork, or discovery of a newer session
```

The test must use the existing `RuntimeBinding`, `CodexCurrentWriterWakeClient`, and adapter fixtures; do not create a second session registry.

- [ ] **Step 3: Prove arbitrary/unbound Codex sessions are refused**

Run or add a negative test where the native handle or generation differs. Required outcome: refusal/effect-unknown according to the current owner; never delivery to another Codex thread.

- [ ] **Step 4: Stop condition**

If the production Astra orchestrator cannot be materialized as an Executive-owned current Codex generation through existing owner paths, mark the first vertical `BLOCKED_PARENT_BINDING` and return to Sol with the exact missing binding capability. Do **not** add "latest Codex session" discovery, window automation, a session-name lookup, or model polling.

If the exact binding is supported, record the exact session alias, binding id/generation, process generation, and native handle in the private canary evidence and continue.

- [ ] **Step 5: Commit only if a test-only discriminator was required**

```bash
git add tests/test_codex_app_server_wake_rpc.py
git commit -m "test: pin exact Astra parent wake binding"
```

If no source/test change was necessary, record the verified existing test names in the PR/canary evidence and create no empty commit.

---

### Task 5: Consume, Do Not Duplicate, the First External Provider Lane

**Files:**
- Dependency/read: PR #583 or its protected successor
- Dependency/read: `config/subscription_provider_profiles.v1.json`
- Dependency/read after protection: `config/subscription_harness_bindings.v1.json`
- Dependency/read after protection: `control_plane/subscription_harness_bindings.py`
- Dependency/read: existing Capacity worker/placement configuration selected by the current owner
- No #583-owned file is modified from this plan until source ownership is terminal/reconciled.

**Interfaces:**
- Consumes: one reviewed external binding whose activation gates are `adapter_implemented`, `provider_realm_enrolled`, `capacity_known`, `real_canary_passed`, and `usage_policy_satisfied`.
- Produces: one Capacity-visible qualified external worker lane that the existing router may select without Astra naming it.

- [ ] **Step 1: Reconcile #583 at execution time**

Required state before proceeding:

```text
#583 (or accepted successor) is protected/merged
binding source is on current protected master
no active writer still owns the same provider-binding files
the selected Alibaba Codex Responses binding is at least BUILT_NOT_PROVEN
its autonomous_allowed flag is still false before the real canary
```

If these are not all true, stop this task at `BLOCKED_PROVIDER_BINDING_SOURCE`; do not reimplement the binding in this plan.

- [ ] **Step 2: Use the current provider/Capacity owner to establish the canary prerequisites**

The selected lane must have:

```text
adapter_implemented = true
provider_realm_enrolled = true
capacity_known = true
usage_policy_satisfied = true
real_canary_passed = false   # before the one-shot canary
```

Credential material remains in the existing provider-home/host trust boundary. Never print the credential, pass it in a prompt, copy it into Codex config, or commit it.

- [ ] **Step 3: Run one read-only real provider canary through the common worker path**

Use a harmless source-grounded research objective with no write paths. Drive the request through Executive admission/COO/Capacity/common worker; do not invoke the provider CLI directly from the Astra session.

Pass requires a canonical successful `WorkerResult`/collection result with:

```text
exact Job/Attempt/worker identity
exact source base/workspace identity
selected reviewed binding/provider realm
bounded useful output
clean process/session settlement
no effect uncertainty
no provider/account chosen by Astra
```

- [ ] **Step 4: Complete the existing activation ceremony, not a local shortcut**

Only after the real canary and all current activation gates pass may the existing owner move the binding/worker lane to its accepted autonomous state. Any such source/config change belongs to that provider/Capacity owner and its own PR, not this Codex client PR.

- [ ] **Step 5: Negative proof**

Demonstrate one refused placement with stale/unknown capacity or missing capability. Required behavior: parked/refused named state; no automatic internal-Codex/provider failover after a worker effect starts.

---

### Task 6: Run the End-to-End Token-Relief Canary

**Files:**
- No new authority/store files.
- Evidence: use existing Executive Job/Attempt/result records plus PR/canary evidence; if a repository evidence artifact is required by current owner procedure, store only bounded non-secret evidence under the existing `review_evidence/` convention.

**Interfaces:**
- Consumes: registered/authenticated Executive MCP in the exact Astra session, strict-v2 host admission, exact Codex RuntimeBinding/Wake, one qualified external provider lane.
- Produces: a real accepted project result and token-economics comparison proving the user-visible capability.

- [ ] **Step 1: Freeze one representative acceptance contract**

Use the same bounded project objective for both runs. It must require enough substantive repository reading/analysis or implementation work that a Codex-heavy execution would normally use internal agents/tool turns, but remain safe for the selected external lane.

Record before either run:

```text
objective
source base SHA
allowed write paths (empty for the first research canary is preferred)
validation/review requirement
acceptance evidence
usage unit available from Codex for the baseline and delegated run
```

Do not change the acceptance contract after seeing one run's usage.

- [ ] **Step 2: Capture the Codex-heavy baseline**

Run the objective with External Fabric delegation intentionally disabled for the baseline only, using the current bounded internal-Codex policy. Capture the best common available usage measure:

```text
Astra input/output/reasoning tokens if exposed
internal Codex subagent count and tokens/usage if exposed
otherwise one documented provider/harness usage proxy used identically for both runs
wall-clock is secondary, never a token substitute
```

Capture accepted output and independent review evidence. The baseline is evidence, not the desired production policy.

- [ ] **Step 3: Start a fresh exact-bound Astra session for the delegated run**

Verify:

```text
mastermind-executive MCP registered and enabled
five expected tools visible
auth valid for read + submit
exact Astra native session/generation has current RuntimeBinding
selected external lane is eligible through Capacity
no stale EFFECT_UNKNOWN operation exists for the operation key
```

- [ ] **Step 4: Submit the same class of objective through `submit_ceo_intent`**

Use one stable operation key. The Astra call supplies only the frozen five-tool business fields. Required immediate result is an accepted admission with `dispatched=false` and canonical job/request identity.

Astra does not invoke an internal subagent merely because the root is initially queued.

- [ ] **Step 5: Let existing COO/Capacity execute the program**

The current strict-v2 cycle performs planning/dispatch. At least one substantive work child must run on the qualified external lane. Any required independent review must use a distinct eligible reviewer under current review policy.

Do not keep Astra alive in a model polling loop. Result-driven continuation should use the exact existing RuntimeBinding/Wake path. If Wake is unavailable but the Job result is durable, stop at `BLOCKED_PARENT_RETURN` rather than calling provider completion end-to-end success.

- [ ] **Step 6: Consume only the compact canonical return**

Astra receives/reads:

```text
root/job/attempt state
source/artifact revision or digest
bounded result summary
validation evidence
review verdict/state
unresolved blockers / next required decision
bounding receipts when present
```

Do not inject the full worker transcript, complete shell log, or repeated repository source into the parent prompt.

- [ ] **Step 7: Astra performs final acceptance**

The result is accepted only if the original user job is complete and the independent review/validation evidence passes. A technically successful worker result with a rejecting review is not acceptance; route the existing bounded repair/re-review path instead.

- [ ] **Step 8: Calculate the token-economics gate**

Using the common usage unit from Step 1:

```text
reduction = 1 - (delegated_astra_plus_internal_codex_usage / baseline_astra_plus_internal_codex_usage)
```

Pass requires `reduction >= 0.50`, equivalent acceptance quality, at least one substantive external work unit, zero routine Chairman account-selection/message-shuttle steps, and no worker transcript replay into normal parent context.

If exact token counters are unavailable, use the predeclared common proxy and label the result `USAGE_PROXY`, never `TOKENS`.

- [ ] **Step 9: Exercise duplicate/restart/effect-negative proof**

Within the same canary program or a separately named non-destructive fault drill, prove:

```text
same operation identity does not create a duplicate root
lost submit response reconciles by the same request_ref
runtime/reasoning restart preserves accepted result and owed parent action
wrong/stale Astra RuntimeBinding cannot consume the continuation
```

No blind retry or provider swap is permitted for the effect-unknown case.

- [ ] **Step 10: Record the capability state truthfully**

If the complete real path passes, mark only this first vertical `PROVEN_LIVE` in its correct durable owners. Do not claim ready-frontier parity, GLM/MiniMax fleet completion, multi-host completion, or Web closed-tab autonomy.

If the path stops earlier, classify the exact sub-capability (`BUILT_NOT_PROVEN`, `PARTIAL`, `DARK_OR_DISCONNECTED`, or `BROKEN`) and leave the exact next action.

---

### Task 7: Current-Base Review, Release, and Closeout

**Files:**
- No new feature scope.
- Update only the correct existing durable records required by current procedure after acceptance.

**Interfaces:**
- Consumes: source changes from Tasks 1-3, any Task-4 test pin, external provider canary evidence from Task 5, end-to-end proof from Task 6.
- Produces: one reviewable source PR for the Codex client/policy changes plus exact production/capability evidence owned by the existing Executive/Capacity/Agent OS systems.

- [ ] **Step 1: Rebase/reconcile with current protected master and collision-check again**

No force push over another owner. If current master changes `AGENTS.md`, Executive MCP/App admission, Codex Wake, or the registration paths materially, re-run the relevant contract tests before continuing.

- [ ] **Step 2: Run the focused regression set**

```bash
python3 -m pytest -q \
  tests/test_astra_external_fabric_contract.py \
  tests/test_codex_fabric_registration.py \
  tests/test_astra_delegation_source_policy.py \
  tests/test_mastermind_executive_app_admission.py \
  tests/test_executive_mcp_app_composition.py \
  tests/test_executive_ceo_ingress.py \
  tests/test_codex_app_server_wake_rpc.py \
  tests/test_runtime_binding_projection.py \
  tests/test_wake_ack_ingress.py
python3 -m compileall -q ops/codex_fabric
git diff --check
```

Then run the repository's required current CI gate. Do not substitute the focused set for protected CI.

- [ ] **Step 3: Adversarial review against the frozen outcome**

Reviewer must answer:

```text
Did the implementation preserve the five-tool public contract?
Can Astra name a provider/account/credential/host anywhere? (must be no)
Can a lost response cause a blind retry/failover? (must be no)
Can an arbitrary Codex tab receive another session's Wake? (must be no)
Is any new durable scheduler/lifecycle/result store present? (must be no)
Can worker transcript bulk flow back into Astra by default? (must be no)
Did a real external lane do substantive work through the canonical path?
Was the result independently reviewed and consumed by the exact Astra parent?
Did measured Astra + internal-Codex usage fall at least 50% using a common unit?
```

Any negative answer on a required item blocks acceptance.

- [ ] **Step 4: Publish source through normal review**

Push the scoped branch, open/update its PR, wait for required checks, and merge only after review. Do not merge provider/Capacity changes from this client PR; those remain with their current owners.

- [ ] **Step 5: Update durable truth**

After accepted real proof:

- Executive OS remains owner of Job/Attempt/runtime evidence;
- Agent OS current workstream/handoff records the proven capability, important discoveries, and exact next action through its existing writer;
- GitHub PR records implementation/test/canary evidence;
- Linear/Control Room may project the result but do not become authority;
- Slack, if used, remains transport only.

- [ ] **Step 6: Leave the next independent program explicitly held**

The next program after this vertical is the existing-owner **ready-frontier dependency/parallelism** wave from #600, followed by provider-matrix expansion. Do not silently start either from this PR.

---

## Plan Self-Review

### Spec coverage

- Existing-five-tool reuse: Tasks 1-3.
- CeoIngress v2 / strict-v2 owner boundary: Tasks 1 and 6.
- No provider/account choice by Astra: Tasks 1, 3, 5, 7.
- Effect-unknown same-carrier reconciliation: Tasks 1, 3, 6, 7.
- Exact Codex parent return: Task 4 and Task 6.
- External first lane without duplicating #583: Task 5.
- Compact result / no transcript replay: Task 3 and Task 6.
- Internal Codex fallback bounded: Task 3.
- Token-economics proof: Task 6.
- No duplicate control plane: global constraints and Task 7 review.
- Production proof and durable closeout: Tasks 6-7.

### Scope check

This plan intentionally stops after the first independently useful external-delegation/token-relief loop. Ready-frontier parallelism, deeper child budgets, GLM/MiniMax activation, broader multi-host recovery, and Live Fabric UI work remain separate follow-on plans so the first PR cannot expand into a platform rewrite.

### Type/interface consistency

The plan reuses existing public identities and types: `operation_key` -> `app_request_ref` -> CeoIngress v2 `request_ref`; `submit_ceo_intent` stays the model-facing modifying tool; `RuntimeBinding`/Codex Wake own exact parent return; provider selection stays outside the caller request. No second serialized lifecycle type is introduced.