# Chat-Native Meta-CEO Core Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Protect ChatGPT Pro Chat as Mastermind's default Sol cognition plane and require an explicit bounded receipt before any metered Workspace Agent, Work, Business-credit, or API reasoning route.

**Architecture:** Add one detailed protected source law and amend the already-mandatory Executive worker-routing addendum so every meaningful Sol/model delegation consumes the rule without modifying the collision-bound Skillpack files in open PR #147. Enforce the architecture with deterministic repository tests. Existing Executive OS, Agent OS, RuntimeBinding, Wake, Capacity, dialogue, GitHub, Linear, and Business Surface owners remain unchanged.

**Tech Stack:** Markdown source law, Python `pytest` contract tests, GitHub protected-branch CI.

**Spec:** `docs/superpowers/specs/2026-08-29-chat-native-meta-ceo-core-model-design.md`

## Global Constraints

- Operation: `chat-native-meta-ceo-core-model-20260829-sol-001`.
- Start from protected `Mastermind@75b90cfeb4752d2a356a463b351382c1e0c25cb1` and re-pin before release.
- Do not modify `docs/sol_skills/**`; open PR #147 owns those paths and freezes its current procedure bytes pending behavioral evidence.
- Do not modify any BSC carrier branch or current Web-Sol/RuntimeBinding/Wake implementation path.
- ChatGPT Pro Chat is the default Sol cognition route while included-plan interactive capacity is available.
- Metered Sol cognition requires `WHY_METERED`, `WHY_PRO_CHAT_INSUFFICIENT`, `EXPECTED_MAX_COST`, `HARD_BUDGET_CAP`, `STOP_CONDITION`, and `BUDGET_AUTHORITY`.
- Business/plugins/MCP remain optional connection and authority adapters, not the default cognition plane.
- This wave creates no runtime router, lifecycle, queue, session database, browser control, credential, workspace/account effect, or production provisioning claim.
- One logical modifying operation uses one GitHub branch and one pull request until canonically reconciled.

---

### Task 1: Add the failing Chat-native cognition contract

**Files:**
- Create: `tests/test_chat_native_meta_ceo_core_model.py`

**Interfaces:**
- Consumes: protected Personal-Pro architecture at `research/MASTERMIND_SOL_EXECUTIVE_SHELL_PRO_NATIVE_ARCHITECTURE_2026-08-20.md` and current mandatory routing addendum.
- Produces: deterministic assertions that define the required law filename, addendum linkage, default/metered route envelopes, hierarchy, scaling, companion-surface boundary, and no-duplicate-owner rules.

- [ ] **Step 1: Write the failing test**

Create a `pytest` module using the repository's existing text-contract style:

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _normalized(text: str) -> str:
    return " ".join(text.split())
```

The tests must fail because `docs/EXECUTIVE_CHAT_NATIVE_SOL_HIERARCHY_LAW.md` does not yet exist and the routing addendum does not yet contain the Chat-first/metered-exception contract.

- [ ] **Step 2: Verify the test is discriminating RED**

Run:

```bash
python -m pytest -q tests/test_chat_native_meta_ceo_core_model.py
```

Expected result: failure naming the missing law file or missing `COGNITION_ROUTE: CHAT_PRO_DEFAULT`; no collection, syntax, import, or unrelated failure.

- [ ] **Step 3: Commit the RED test**

```bash
git add tests/test_chat_native_meta_ceo_core_model.py
git commit -m "test: require Chat-native Sol cognition law"
```

### Task 2: Protect the operational cognition-economics law

**Files:**
- Create: `docs/EXECUTIVE_CHAT_NATIVE_SOL_HIERARCHY_LAW.md`
- Modify: `docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md`

**Interfaces:**
- Consumes: the approved architecture spec and existing mandatory routing law.
- Produces: one canonical source law automatically reached through the already-mandatory routing addendum for every meaningful Sol/model delegation.

- [ ] **Step 1: Create the detailed law**

The law must define:

```text
COGNITION_ROUTE: CHAT_PRO_DEFAULT
COGNITION_ROUTE: METERED_EXCEPTION
WHY_METERED
WHY_PRO_CHAT_INSUFFICIENT
EXPECTED_MAX_COST
HARD_BUDGET_CAP
STOP_CONDITION
BUDGET_AUTHORITY
METERED_ROUTE_REFUSED / WAITING_FOR_LAWFUL_ROUTE
```

It must also freeze:

- one Chairman-facing Meta-CEO Chat office with replaceable RuntimeBindings;
- Chat-native Program CEO, Project Sol, Integrator, and Auditor defaults;
- deterministic always-on Mastermind control and event-driven Chat wake;
- scaling by multiplexing, parking, bounded fanout, and session recycling;
- Business/MCP as companion connection surface;
- Workspace Agents, Work, and API as metered exceptions;
- preservation of every existing lifecycle, memory, binding, wake, capacity, dialogue, and evidence owner.

- [ ] **Step 2: Amend the mandatory routing addendum**

Insert a high-precedence section immediately after the core rule that:

1. identifies the detailed law by exact path;
2. states that ChatGPT Pro Chat is the default Sol-class cognition surface;
3. rejects a Workspace-Agent-front-end plus API-Meta-CEO default stack;
4. requires the complete metered exception receipt;
5. preserves current capacity and usage-policy honesty;
6. keeps Business/Plugins/MCP as optional companions;
7. states that the economic route never grants lifecycle or organizational authority.

Update later decomposition and route-receipt sections so Sol-class commissions record `COGNITION_ROUTE` before the worker/model route.

- [ ] **Step 3: Run the focused test**

```bash
python -m pytest -q tests/test_chat_native_meta_ceo_core_model.py
```

Expected result: all focused tests pass.

- [ ] **Step 4: Run adjacent routing regressions**

```bash
python -m pytest -q \
  tests/test_chat_native_meta_ceo_core_model.py \
  tests/test_worker_avenue_routing_skill.py
```

Expected result: all tests pass; existing Fable, Terra, CTO Sol, capacity-selectable, exact-session, and Chairman-placement laws remain intact.

- [ ] **Step 5: Commit the GREEN law**

```bash
git add \
  docs/EXECUTIVE_CHAT_NATIVE_SOL_HIERARCHY_LAW.md \
  docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md
git commit -m "docs: make Chat-native Sol cognition the default"
```

### Task 3: Prove scope, compatibility, and release honesty

**Files:**
- Verify only: all files in this pull request.

**Interfaces:**
- Consumes: Tasks 1-2 exact head.
- Produces: immutable exact-head proof and a reviewable release carrier for protected source law only.

- [ ] **Step 1: Verify exact changed paths**

Expected path set:

```text
docs/EXECUTIVE_CHAT_NATIVE_SOL_HIERARCHY_LAW.md
docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md
docs/superpowers/specs/2026-08-29-chat-native-meta-ceo-core-model-design.md
docs/superpowers/plans/2026-08-29-chat-native-meta-ceo-core-model.md
tests/test_chat_native_meta_ceo_core_model.py
```

No `docs/sol_skills/**`, runtime, config, app, workflow, credential, Agent OS, Linear, Slack, Business account, or browser implementation path may appear.

- [ ] **Step 2: Run repository text and syntax checks**

```bash
python -m py_compile tests/test_chat_native_meta_ceo_core_model.py
python -m pytest -q \
  tests/test_chat_native_meta_ceo_core_model.py \
  tests/test_worker_avenue_routing_skill.py
git diff --check origin/master...HEAD
```

Expected result: all pass with no warnings or whitespace errors.

- [ ] **Step 3: Open one draft pull request**

The PR body must name:

- exact operation and protected pickup SHA;
- exact five-file scope;
- the open #147 collision and deliberate no-touch boundary;
- the conceptual BSC compatibility boundary;
- RED test receipt and GREEN exact head;
- `SPEC_ONLY / PROTECTED_SOURCE_LAW`, not runtime provisioning or fleet completion.

- [ ] **Step 4: Obtain hosted exact-head proof**

Require the repository `test` workflow and applicable security/static analyses on the exact PR head. A green test proves only the protected routing/source-law contract.

- [ ] **Step 5: Perform final Sol review**

Verify:

- primary persona remains the Chairman speaking to one Meta-CEO Chat;
- Chat-native Sol reasoning is the default economic route;
- metered routes are bounded exceptions rather than forbidden capabilities;
- no current BSC, Web-Sol, RuntimeBinding, Wake, Capacity, or Skillpack owner was duplicated;
- no runtime or production-live claim appears;
- future CNM-R1/S1/P1/H1/C1/FLEET1 waves remain separate.

- [ ] **Step 6: Release with expected-head protection**

Re-fetch protected `master`. If it moved, compare the exact five paths and history-preservingly reconcile the same branch. Merge only when the PR is current-base, exact-head green, independently reviewed, and the expected head is supplied.

- [ ] **Step 7: Record continuation**

After protection, update the current Chairman Control Room / organizational-continuity projection to state:

```text
Chat-native Meta-CEO core law = PROTECTED SOURCE LAW
runtime provisioning / exact Pro-mode attestation / hierarchy canary = NOT BUILT
```

The next implementation action is CNM-R1: add a deterministic cognition-route validation/projection seam inside the existing routing/Capacity owner, not a second router.