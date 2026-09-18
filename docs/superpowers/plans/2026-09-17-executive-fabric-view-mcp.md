# Executive Fabric View MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give an authenticated Web CEO one truthful, read-only Fabric-root view without changing the frozen BSC-E1 / EXEC-MCP-A five-tool contract.

**Architecture:** Preserve legacy Executive MCP `1.0.0` and its pinned five-tool schema byte-for-byte. Add `executive_fabric` only to the separately versioned static `web_ceo_v1` profile. Both profiles reuse the existing schema primitives, bounded gateway/executor, A1 auth, Mastermind Executive App, CeoIngress and Executive Runtime; the Fabric tool delegates lifecycle derivation to `control_plane.fabric_job_view`. The v2 App-read frame is host-bound profile selection, never request input. No new lifecycle, registry, queue, scheduler, cancellation, dispatch, retry, auth or result store is created.

**Tech Stack:** Python 3.12, MCP Python SDK, existing Executive MCP/App/CeoIngress owners, existing `mastermind.fabric_job_view.v1` projector, pytest.

**Specs:** `docs/FABRIC_JOB_VIEW.md` and `docs/EXECUTIVE_WEB_CEO_FABRIC_READ_AMENDMENT.md`.

> **Architecture correction (2026-09-17):** The first implementation widened global `TOOL_SPECS` from five to six. Hosted CI correctly failed five protected BSC-E1/Wake freeze guards. Current protected architecture also explicitly prohibits in-place widening for the existing Astra/BSC-E1 client. That approach is superseded. The task detail below is retained as implementation archaeology where useful, but any reference to changing the existing five-tool contract must be read as changing only `web_ceo_v1`.

## Global Constraints

- Protected integration base for the corrected carrier: `320f586126b7c82c843ef17612f12d40d20a42e0`.
- Existing Executive OS remains sole Job/Attempt/Worker/Event lifecycle owner.
- `control_plane.fabric_job_view` is consumed unchanged; PR #124's stale projector path is not edited.
- Tool is read-only and cannot dispatch, cancel, retry, reassign, wake, merge, deploy, or touch credentials/providers.
- Runtime/database reads stay through the projector's existing `create=False` path; no raw SQL.
- No absolute operator/runtime path may cross the MCP boundary.
- One response remains bounded by the existing `MAX_RESPONSE_BYTES` envelope.
- Source result stops at Draft/HOLD; install, app registration, Ready, merge, and production proof are later gates.

---

### Task 1: Freeze the `executive_fabric` tool contract

**Files:**
- Create: `tests/test_executive_mcp_fabric_view.py`
- Modify: `integrations/executive_mcp/schemas.py`
- Modify: `docs/superpowers/plans/2026-09-17-executive-fabric-view-mcp.md`

**Interfaces:**
- Consumes: existing `ToolSpec`, `validate_tool_arguments`, `_JOB_ID_RE`, and schema snapshot law.
- Produces: validated arguments in exactly one of these forms:
  - `{"view": "roots", "limit": <1..50>}` with default `limit=50`.
  - `{"view": "root", "root_job_id": "JOB-<n>"}`.

- [ ] **Step 1: Write failing contract tests**

```python
def test_executive_fabric_is_read_only_and_advertised():
    spec = tool_spec("executive_fabric")
    assert spec.read_only is True
    assert "executive_fabric" in tool_names()


def test_executive_fabric_validates_closed_modes():
    assert validate_tool_arguments("executive_fabric", {"view": "roots"}) == {
        "view": "roots", "limit": 50
    }
    assert validate_tool_arguments(
        "executive_fabric", {"view": "root", "root_job_id": "JOB-7"}
    ) == {"view": "root", "root_job_id": "JOB-7"}


@pytest.mark.parametrize("payload", [
    {},
    {"view": "roots", "root_job_id": "JOB-1"},
    {"view": "root"},
    {"view": "root", "root_job_id": "JOB-1", "limit": 5},
    {"view": "roots", "limit": 0},
    {"view": "roots", "limit": 51},
    {"view": "other"},
])
def test_executive_fabric_rejects_ambiguous_or_unbounded_inputs(payload):
    with pytest.raises(GatewayError) as exc:
        validate_tool_arguments("executive_fabric", payload)
    assert exc.value.code == "invalid_input"
```

- [ ] **Step 2: Run RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.12 -m pytest -q -p no:cacheprovider \
  tests/test_executive_mcp_fabric_view.py
```

Expected: FAIL because `executive_fabric` is not a registered tool.

- [ ] **Step 3: Implement the minimal closed contract**

Add one read-only `ToolSpec` named `executive_fabric`; encode the two closed request shapes in its advertised JSON schema; add authoritative server-side validation; bump `SERVER_VERSION` to `1.1.0`; refresh the pinned schema digest only after the tests exercise the exact intended surface.

- [ ] **Step 4: Run GREEN and schema guard tests**

```bash
PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.12 -m pytest -q -p no:cacheprovider \
  tests/test_executive_mcp_fabric_view.py \
  tests/test_executive_mcp.py::test_schema_snapshot_is_pinned \
  tests/test_executive_mcp.py::test_schema_snapshot_is_sensitive_to_a_sixth_tool
```

Expected: PASS after updating the old "sixth tool must never exist" guard to reject an unreviewed seventh tool.

- [ ] **Step 5: Commit the contract**

```bash
git add docs/superpowers/plans/2026-09-17-executive-fabric-view-mcp.md \
  integrations/executive_mcp/schemas.py tests/test_executive_mcp_fabric_view.py
git commit -m "feat(exec-mcp): freeze read-only fabric view contract"
```

---

### Task 2: Route the tool through the canonical Fabric projector

**Files:**
- Modify: `tests/test_executive_mcp_fabric_view.py`
- Modify: `integrations/executive_mcp/adapter.py`

**Interfaces:**
- Consumes:
  - `fabric_job_view.list_roots(runtime_root, limit=...)`.
  - `fabric_job_view.read_fabric_view(runtime_root, root_job_id)`.
  - existing `GatewayConfig.runtime_root`, `_runtime_label()`, bounded read executor, and response envelope.
- Produces: the projector's canonical document inside `mastermind.executive_mcp_result.v1`, with host runtime paths replaced by the existing non-secret runtime label.

- [ ] **Step 1: Write failing adapter tests**

```python
@pytest.mark.asyncio
async def test_executive_fabric_lists_roots_through_canonical_projector(...):
    # Patch only the I/O seam, return a canonical root-list document containing
    # the temporary absolute runtime path, call the real gateway, and assert:
    # - the projector receives GatewayConfig.runtime_root and limit;
    # - the response is ok and preserves schema/roots/count;
    # - the absolute path is absent from the entire envelope;
    # - the stable `readonly:<basename>` label is present.


@pytest.mark.asyncio
async def test_executive_fabric_reads_one_root_through_canonical_projector(...):
    # Assert root_job_id routing, canonical schema, child/review/result preservation,
    # and absence of the absolute runtime path.


@pytest.mark.asyncio
async def test_executive_fabric_projector_failure_is_typed_and_path_safe(...):
    # Projector raises an OSError containing the runtime path. The gateway must
    # return backend_unavailable without leaking that path or a traceback.
```

- [ ] **Step 2: Run RED**

Expected: contract validation passes, but the adapter returns unknown/not-found because no read dispatch exists.

- [ ] **Step 3: Implement minimal adapter composition**

Import `control_plane.fabric_job_view`; add the `executive_fabric` branch to `_read`; implement one helper that selects `list_roots` or `read_fabric_view`; recursively replace configured runtime path strings with `_runtime_label()` in returned data/degradation text; convert projector exceptions to a path-safe `backend_unavailable`; leave the projector and Runtime untouched.

- [ ] **Step 4: Run GREEN and existing read-path tests**

```bash
PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.12 -m pytest -q -p no:cacheprovider \
  tests/test_executive_mcp_fabric_view.py \
  tests/test_executive_mcp.py \
  tests/test_fabric_job_view.py
```

- [ ] **Step 5: Commit adapter composition**

```bash
git add integrations/executive_mcp/adapter.py tests/test_executive_mcp_fabric_view.py
git commit -m "feat(exec-mcp): expose canonical fabric job view"
```

---

### Task 3: Prove the real MCP server surface and document the ceiling

**Files:**
- Modify: `tests/test_executive_mcp_fabric_view.py`
- Modify: `docs/FABRIC_JOB_VIEW.md`
- Modify only if discriminating tests require it: `integrations/executive_mcp/server.py`

**Interfaces:**
- Consumes: `build_tools()` and `build_mcp_server()` from the existing server.
- Produces: one authenticated-app-compatible advertised tool; no new route, resource, prompt, sampling, or write handler.

- [ ] **Step 1: Write failing/guard server tests**

```python
def test_server_advertises_exactly_one_new_read_tool():
    tools = {tool.name: tool for tool in build_tools()}
    assert tools["executive_fabric"].annotations.readOnlyHint is True


@pytest.mark.asyncio
async def test_low_level_server_calls_gateway_once_for_executive_fabric(...):
    # Use the real low-level MCP server and a recording gateway. Assert one call,
    # exact normalized arguments, and no secondary tool invocation.
```

- [ ] **Step 2: Run the focused server tests**

If they pass immediately because the server is correctly table-driven, retain them as regression guards; no server production edit is warranted.

- [ ] **Step 3: Document the product boundary**

Amend `docs/FABRIC_JOB_VIEW.md` with the Executive MCP access shape, path-redaction rule, and explicit statement that visibility is not spawn/cancel/dispatch authority and remains `BUILT_NOT_PROVEN` until installed-app proof.

- [ ] **Step 4: Run the complete owning campaign**

```bash
PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.12 -m pytest -q -p no:cacheprovider \
  tests/test_executive_mcp_fabric_view.py \
  tests/test_executive_mcp.py \
  tests/test_executive_mcp_mutation.py \
  tests/test_executive_mcp_app_composition.py \
  tests/test_executive_mcp_e1_composition.py \
  tests/test_fabric_job_view.py
/opt/homebrew/bin/python3.12 -m compileall -q integrations/executive_mcp control_plane/fabric_job_view.py
git diff --check
```

- [ ] **Step 5: Commit documentation and guards**

```bash
git add docs/FABRIC_JOB_VIEW.md tests/test_executive_mcp_fabric_view.py \
  integrations/executive_mcp/server.py
git commit -m "test(exec-mcp): prove fabric view server surface"
```

- [ ] **Step 6: Publish a Draft/HOLD source checkpoint**

Push the same operation branch non-force, open one Draft PR, run Source Continuity checkpoint against the exact head/tree/path set, and return exact tests/checks/capability ceiling. No Ready, merge, installation, app registration, or production claim.
