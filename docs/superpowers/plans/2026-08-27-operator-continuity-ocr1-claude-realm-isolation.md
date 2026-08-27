# OCR-1 Claude Realm Isolation Falsifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove, on the real available hosts and without exposing credential values, whether the five paid Claude subscriptions can operate as distinct concurrent machine-addressable realms and which provider-supported authentication mechanism is safe to admit into Capacity Fabric.

**Architecture:** Extend the existing Macro Shared AI Provider Control owner rather than creating a Mastermind credential/account registry. A new read-only host probe consumes existing `claude_code_oauth_N` capability/ref-name discovery, launches the installed Claude binary with one realm credential at a time, uses provider-supported `claude auth status` plus a bounded `claude -p` health turn, and emits a closed secret-free receipt. The production proof compares realm behavior and concurrency but never writes tokens, account PII, raw auth status JSON, or a new provider ledger.

**Tech Stack:** Python 3.11+, Macro `engine.neuralweb.key_pool`, existing `scripts.preflight_claude_auth`, subprocess/asyncio, Claude Code CLI, pytest.

**Spec:** `mastermind:docs/superpowers/specs/2026-08-27-operator-continuity-realm-rebinding-design.md`

## Global Constraints

- Provider/account capacity, credential-presence mechanics, cooling and quota truth remain owned by Macro Shared AI Provider Control.
- No secret value, email/account PII, cookie, raw auth file or complete `claude auth status` payload may enter Git, stdout receipts, Slack, Agent OS or Executive OS.
- On macOS, `CLAUDE_CONFIG_DIR` is not accepted as credential isolation evidence; official Claude docs state login credentials are stored in macOS Keychain.
- `CLAUDE_CODE_OAUTH_TOKEN` may be evaluated because current Claude docs explicitly support one-year subscription tokens for scripts/CI. Provisioning/generation is a human-admin action and is not performed by this wave.
- The probe may make only bounded auth/status and harmless model health calls. It creates no Executive Job, Worker, Attempt, route, Wake, Slack message or persistent daemon.
- Unknown or unsupported auth identity is a truthful refusal, not permission to infer that two realms are distinct.
- Existing `provider_capacity.v1` schema is not widened in OCR-1. Any new field needed by Capacity Fabric returns to Sol and CF1/CF2 owners.

---

### Task 1: Add a closed secret-free realm-probe contract

**Repository:** `mastermindx-market-intelligence/macro`

**Files:**
- Create: `engine/claude_realm_probe.py`
- Test: `tests/test_claude_realm_probe.py`

**Interfaces:**
- Consumes: capability ids/ref names from existing `engine.neuralweb.key_pool`; no credential values in public inputs.
- Produces: `RealmProbeReceipt`, `RealmPairwiseReceipt`, `sanitize_auth_status()`, `build_host_receipt()`.

- [ ] **Step 1: Write failing contract tests**

```python
from engine.claude_realm_probe import (
    RealmProbeReceipt,
    RealmPairwiseReceipt,
    build_host_receipt,
    sanitize_auth_status,
)


def test_sanitize_auth_status_drops_pii_and_secret_shaped_values():
    raw = {
        "loggedIn": True,
        "authMethod": "oauth_token",
        "email": "person@example.com",
        "organization": "Private Org",
        "token": "sk-secret-shaped-value-123456789",
    }
    assert sanitize_auth_status(raw) == {
        "logged_in": True,
        "auth_method": "oauth_token",
    }


def test_host_receipt_contains_no_account_fingerprint_or_raw_identity():
    realm = RealmProbeReceipt(
        realm_ref="claude_code_oauth_1",
        auth_ok=True,
        auth_method="oauth_token",
        ping_ok=True,
        auth_identity_observed=True,
        observed_identity_slot="realm-local-1",
        error_class=None,
    )
    receipt = build_host_receipt(
        host_ref="opaque-host-a",
        realms=[realm],
        pairwise=[],
        concurrent_probe_passed=True,
    )
    rendered = repr(receipt).lower()
    assert "@" not in rendered
    assert "token" not in rendered.replace("oauth_token", "")
    assert "realm-local-1" not in rendered
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `pytest -q tests/test_claude_realm_probe.py`

Expected: import failure because `engine.claude_realm_probe` does not exist.

- [ ] **Step 3: Implement the minimal closed dataclasses and sanitizer**

```python
@dataclass(frozen=True)
class RealmProbeReceipt:
    realm_ref: str
    auth_ok: bool
    auth_method: str | None
    ping_ok: bool
    auth_identity_observed: bool
    observed_identity_slot: str | None = field(repr=False)
    error_class: str | None = None


@dataclass(frozen=True)
class RealmPairwiseReceipt:
    left_realm_ref: str
    right_realm_ref: str
    distinct_identity: bool | None


def sanitize_auth_status(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "logged_in": raw.get("loggedIn") is True or raw.get("logged_in") is True,
        "auth_method": _bounded_method(raw.get("authMethod") or raw.get("auth_method")),
    }
```

`observed_identity_slot` is in-memory only and `repr=False`; the public serializer must omit it entirely.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `pytest -q tests/test_claude_realm_probe.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/claude_realm_probe.py tests/test_claude_realm_probe.py
git commit -m "feat(provider): add secret-free Claude realm probe contract"
```

---

### Task 2: Reuse existing pool discovery without widening secret ownership

**Files:**
- Modify: `engine/claude_realm_probe.py`
- Test: `tests/test_claude_realm_probe.py`

**Interfaces:**
- Consumes: `discover_present_keys()`, `get_secret_ref()` and `is_cooling()` from the existing Macro key pool.
- Produces: `discover_probe_specs(root=None) -> tuple[RealmProbeSpec, ...]` containing capability id + env-var **name** only.

- [ ] **Step 1: Add a failing discovery test using monkeypatched key-pool functions**

```python
def test_discovery_returns_only_capability_and_ref_names(monkeypatch):
    monkeypatch.setattr("engine.claude_realm_probe.discover_present_keys", lambda root=None: ["claude_code_oauth_1"])
    monkeypatch.setattr("engine.claude_realm_probe.get_secret_ref", lambda cap_id, root=None: "CLAUDE_CODE_OAUTH_TOKEN_1")
    monkeypatch.setattr("engine.claude_realm_probe.is_cooling", lambda cap_id, root=None: False)
    specs = discover_probe_specs()
    assert [(x.realm_ref, x.secret_ref_name) for x in specs] == [
        ("claude_code_oauth_1", "CLAUDE_CODE_OAUTH_TOKEN_1")
    ]
    assert not hasattr(specs[0], "token")
```

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_claude_realm_probe.py::test_discovery_returns_only_capability_and_ref_names`

- [ ] **Step 3: Implement `RealmProbeSpec` and discovery**

```python
@dataclass(frozen=True)
class RealmProbeSpec:
    realm_ref: str
    secret_ref_name: str


def discover_probe_specs(root: Path | None = None) -> tuple[RealmProbeSpec, ...]:
    rows = []
    for cap_id in discover_present_keys(root):
        if not cap_id.startswith("claude_code_oauth_") or is_cooling(cap_id, root=root):
            continue
        ref = get_secret_ref(cap_id, root=root)
        if ref:
            rows.append(RealmProbeSpec(cap_id, ref))
    return tuple(rows)
```

- [ ] **Step 4: Run tests**

Run: `pytest -q tests/test_claude_realm_probe.py`

- [ ] **Step 5: Commit**

```bash
git add engine/claude_realm_probe.py tests/test_claude_realm_probe.py
git commit -m "feat(provider): discover Claude realm probe specs"
```

---

### Task 3: Add a secret-owning subprocess boundary for one realm

**Files:**
- Modify: `engine/claude_realm_probe.py`
- Modify only if reuse requires it: `scripts/preflight_claude_auth.py`
- Test: `tests/test_claude_realm_probe.py`

**Interfaces:**
- Consumes: one `RealmProbeSpec`; credential value is resolved inside the private probe call from the already-owned environment ref.
- Produces: one `RealmProbeReceipt`; no raw stdout/stderr is returned.

- [ ] **Step 1: Add failing tests for environment precedence and redaction**

```python
def test_probe_sets_only_selected_oauth_token_and_clears_higher_precedence_auth(monkeypatch):
    captured = {}
    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["env"] = kwargs["env"]
        return CompletedProcess(argv, 0, stdout='{"loggedIn":true,"authMethod":"oauth_token"}\n', stderr="")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN_1", "secret-one")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-win")
    monkeypatch.setattr("engine.claude_realm_probe.subprocess.run", fake_run)
    _run_auth_status(RealmProbeSpec("claude_code_oauth_1", "CLAUDE_CODE_OAUTH_TOKEN_1"), "/usr/bin/claude")
    assert captured["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == "secret-one"
    assert "ANTHROPIC_API_KEY" not in captured["env"]
    assert "ANTHROPIC_AUTH_TOKEN" not in captured["env"]
```

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_claude_realm_probe.py -k selected_oauth_token`

- [ ] **Step 3: Implement the private environment builder and two bounded calls**

`_realm_env()` must remove `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, cloud-provider selection variables and any inherited `CLAUDE_CODE_OAUTH_TOKEN`, then inject exactly the chosen value as `CLAUDE_CODE_OAUTH_TOKEN` into the child environment.

Call 1:

```text
claude auth status
```

Call 2:

```text
claude -p --output-format json "Reply with exactly: realm-probe-ok"
```

Use fixed short timeouts. Parse only allowlisted booleans/method fields from auth status and a success/non-success result from the health turn. Never forward provider stderr except an allowlisted low-cardinality `auth|usage_limit|timeout|not_installed|transport|error` class.

- [ ] **Step 4: Add hostile-output tests**

Test malformed JSON, secret-shaped stdout/stderr, timeouts, missing binary, auth failure and rate limit. Every receipt must remain bounded and secret-free.

- [ ] **Step 5: Run focused + existing provider tests**

Run:

```bash
pytest -q tests/test_claude_realm_probe.py
pytest -q tests/test_preflight_claude_auth.py tests/test_provider_capacity.py
```

- [ ] **Step 6: Commit**

```bash
git add engine/claude_realm_probe.py scripts/preflight_claude_auth.py tests/test_claude_realm_probe.py
git commit -m "feat(provider): probe one Claude subscription realm safely"
```

---

### Task 4: Prove pairwise distinction without persisting account PII

**Files:**
- Modify: `engine/claude_realm_probe.py`
- Test: `tests/test_claude_realm_probe.py`

**Interfaces:**
- Consumes: raw `claude auth status` identity fields inside one process invocation only.
- Produces: pairwise `distinct_identity=True|False|None`; raw identity material is discarded before receipt serialization.

- [ ] **Step 1: Add failing pairwise tests**

```python
def test_pairwise_identity_emits_only_boolean_distinction():
    left = _PrivateRealmObservation("r1", identity=("claudeai", "acct-A"))
    right = _PrivateRealmObservation("r2", identity=("claudeai", "acct-B"))
    row = compare_private_identities(left, right)
    assert row == RealmPairwiseReceipt("r1", "r2", True)
    assert "acct-A" not in repr(row)
    assert "acct-B" not in repr(row)


def test_missing_provider_identity_is_unknown_not_distinct():
    left = _PrivateRealmObservation("r1", identity=None)
    right = _PrivateRealmObservation("r2", identity=("claudeai", "acct-B"))
    assert compare_private_identities(left, right).distinct_identity is None
```

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_claude_realm_probe.py -k pairwise`

- [ ] **Step 3: Implement private identity extraction and immediate comparison**

Keep the complete provider identity only in `_PrivateRealmObservation` with `repr=False` and no public serializer. `build_host_receipt()` receives only public receipts and already-reduced pairwise booleans.

If installed `claude auth status` does not expose a provider identity for `CLAUDE_CODE_OAUTH_TOKEN`, emit `distinct_identity=None`. Do not manufacture distinctness from capability labels.

- [ ] **Step 4: Run tests**

Run: `pytest -q tests/test_claude_realm_probe.py`

- [ ] **Step 5: Commit**

```bash
git add engine/claude_realm_probe.py tests/test_claude_realm_probe.py
git commit -m "feat(provider): compare Claude realms without account disclosure"
```

---

### Task 5: Add bounded concurrent isolation proof CLI

**Files:**
- Create: `scripts/claude_realm_isolation_probe.py`
- Modify: `engine/claude_realm_probe.py`
- Test: `tests/test_claude_realm_isolation_probe_cli.py`

**Interfaces:**
- Produces exactly one JSON document with schema `mastermind.claude_realm_isolation_probe.v1`.
- Exit code `0` only for a structurally valid probe execution; acceptance/refusal lives in `verdict`, not process success.

- [ ] **Step 1: Write CLI contract tests**

Expected receipt keys:

```python
{
  "schema",
  "host_ref",
  "observed_at",
  "claude_version",
  "realms",
  "pairwise",
  "concurrent_probe_passed",
  "verdict",
  "reason_codes",
}
```

Accepted verdict vocabulary:

```text
ACCEPTED_DISTINCT_REALMS
REFUSED_IDENTITY_UNOBSERVABLE
REFUSED_REALMS_NOT_DISTINCT
REFUSED_CONCURRENT_AUTH_COLLISION
REFUSED_AUTH_FAILURE
REFUSED_CLAUDE_UNAVAILABLE
```

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_claude_realm_isolation_probe_cli.py`

- [ ] **Step 3: Implement CLI**

The CLI:

1. resolves the existing Claude binary helper;
2. discovers present non-cooling realms;
3. probes each sequentially;
4. runs two-at-a-time harmless health turns for all pair combinations, bounded by a fixed concurrency ceiling of 2;
5. repeats auth status after concurrent calls to detect realm drift;
6. reduces private identity to pairwise booleans before rendering JSON;
7. scans serialized bytes against existing capability-redline secret patterns before stdout.

Do not write a receipt file by default. `--output <path>` is allowed only for a caller-provided owner-only evidence directory and must use atomic `0600` creation.

- [ ] **Step 4: Run focused, semantic and secret-redline tests**

Run:

```bash
pytest -q tests/test_claude_realm_probe.py tests/test_claude_realm_isolation_probe_cli.py
python3 scripts/check_capability_redline.py
python3 -m compileall -q engine scripts
```

- [ ] **Step 5: Commit**

```bash
git add engine/claude_realm_probe.py scripts/claude_realm_isolation_probe.py tests/test_claude_realm_isolation_probe_cli.py
git commit -m "feat(provider): add Claude realm isolation falsifier"
```

---

### Task 6: Real-host production-inert proof

**Files:**
- No source changes unless a concrete defect is found.
- Sanitized evidence follows the repository's existing proof-artifact convention; never commit raw provider output.

**Interfaces:**
- Consumes: real host + already-provisioned pool tokens/realms.
- Produces: sanitized `mastermind.claude_realm_isolation_probe.v1` receipt and one Sol review packet.

- [ ] **Step 1: Re-pin current Macro main and protected Mastermind Skillpack**

Record exact revisions in the proof packet.

- [ ] **Step 2: Run the probe on each intended Claude worker host**

Run from a clean current Macro checkout with the host's normal secret-owning environment. Never paste credentials into the command line.

- [ ] **Step 3: Require one truthful verdict**

`ACCEPTED_DISTINCT_REALMS` is necessary to release the corresponding realms for later PF1/Capacity work. Any refusal stops this wave; do not repair by logging into/out of accounts repeatedly from the probe.

- [ ] **Step 4: Repeat once after process restart**

The same realm labels must remain usable/distinct, and no realm may silently pick up another account after restart.

- [ ] **Step 5: Return to Sol**

Return:

```text
Macro base/head
changed files
host_ref(s)
Claude binary version/digest evidence
realm labels tested
secret-free verdict + reason codes
pairwise distinct/unknown matrix
concurrency verdict
restart verdict
focused/full CI
zero-secret/redline proof
exact recommendation: accepted realm mechanism or falsifier
```

## Stop Condition

OCR-1 stops after Sol accepts one real secret-free realm-isolation mechanism or records a falsifier. It does not implement CF2-I, RF1, HF1, PF1, Executive claims, Wake, Agent Relay, OpenClaw, Steward or multi-host dispatch.
