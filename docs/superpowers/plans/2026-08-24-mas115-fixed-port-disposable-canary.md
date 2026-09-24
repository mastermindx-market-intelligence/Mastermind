# MAS-115 Fixed-Port Disposable Multilogin Canary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing MAS-115 Multilogin disposable-profile canary use one fixed loopback port, configure that exact port through one fail-closed profile update, and prove the full C0-C10 path without Chairman-seat or private-data exposure.

**Architecture:** Advance the persisted provision to a fixed-origin policy, derive `127.0.0.1:65535` only in source, and place pure port-policy validation in a small new module. Keep credential ownership, bounded vendor HTTP, exact-profile lifecycle, and live orchestration in the existing secret-owning helper; make the one configuration command structurally incapable of selecting a profile, port, endpoint, or extra field.

**Tech Stack:** Python 3.12, stdlib `dataclasses`/`hashlib`/`http.server`, `httpx` bounded transport, pytest 9, macOS Keychain helper, Multilogin cloud and launcher APIs, W3C WebDriver.

**Spec:** `docs/superpowers/specs/2026-08-24-mas115-fixed-port-disposable-canary-design.md`

## Global Constraints

- Protected Mastermind base is `7136b30a63ac47bdfc0a44e4d5080e0cd345de42`; use the existing carrier `codex/mas115-fixed-port-20260824-9ju4rk`.
- The only canary origin is `http://127.0.0.1:65535`; the port is not a CLI argument, environment value, provision value, fallback, or dynamic allocation.
- Persisted provision schema v3 uses `"origin_policy": "mas115_fixed_loopback_v1"` and contains no `benign_origin` field.
- Only the exact legacy v2 origin `http://127.0.0.1:7777` may migrate, atomically and before Keychain/vendor access.
- The only vendor mutation is `POST https://api.multilogin.com/profile/partial_update` with exact profile identity, preserved auto-update boolean, `ports_masking="mask"`, and `ports=[65535]`.
- Executive Runtime remains lifecycle authority; this work adds no queue, worker/session controller, identity registry, retry plane, or durable receipt store.
- Agent OS remains organizational memory; GitHub remains implementation/evidence truth.
- No raw credential, profile ID, folder ID, URL, name, notes, proxy, fingerprint payload, cookie, session, response body, or raw process arguments may enter output or receipts.
- `EFFECT_UNKNOWN` is never retried. Read-only reconciliation on the same carrier is the only automatic next action.
- No Chairman profile may be started, stopped, configured, navigated, inspected, or used for foreground proof in this plan.
- Green CI, merge, deployment, live configuration, C0-C10 PASS, and final MAS-115 acceptance remain separate states.
- Implementation uses strict TDD: add one failing behavior, run its exact test and observe the expected failure, make the smallest production change, rerun, and commit the independently reviewable unit.

---

## File Structure

- `integrations/chairman_surfaces/mas115_multilogin_port_policy.py` — new pure module containing fixed constants, provision-policy constants, exact Profile Metas classifier, private preservation digest, exact partial-update body builder, and closed redacted configuration receipts. It imports no live HTTP, Keychain, browser, process, setup, or control-plane module.
- `integrations/chairman_surfaces/nonseat_canary.py` — advance persisted provision validation to v3, add exact legacy-to-v3 candidate validation, require the fixed origin policy at runtime, and make hermetic provisions derive the fixed live origin.
- `integrations/chairman_surfaces/nonseat_canary_vendors.py` — add only fixed Multilogin Metas/update transport methods, fixed-port loopback binding/self-test, configuration orchestration, ordinary-run exact-policy preflight, and no-retry reconciliation.
- `scripts/mas115_setup.py` — build v3 provisions, atomically migrate the one accepted v2 file, expose `configure-canary-port`, and continue routing credentials through the existing native helper.
- `tests/test_mas115_multilogin_port_policy.py` — new exhaustive pure contract/mutation suite for metadata classification, request construction, preservation digest, and receipt hygiene.
- `tests/test_nonseat_canary.py` — update constitutional canary fixtures and replace the blanket no-profile-update falsifier with an exact structural allowlist; test HTTP ordering, fixed binding, config lifecycle, ambiguity, and ordinary-run enforcement.
- `tests/test_mas115_setup.py` — test v3 provision creation, exact atomic v2 migration, command routing, and pre-secret refusal order.
- `docs/CHAIRMAN_CONTROL_ROOM.md` — replace stale random-origin/no-update guidance with the exact fixed-port setup journey and capability boundary.

---

### Task 1: Pure fixed-port policy and exact Multilogin metadata classifier

**Files:**

- Create: `integrations/chairman_surfaces/mas115_multilogin_port_policy.py`
- Create: `tests/test_mas115_multilogin_port_policy.py`

**Interfaces:**

- Consumes: standard Python objects representing a bounded Multilogin Profile Metas response; no credential or transport.
- Produces: `CANARY_PORT: int`, `CANARY_ORIGIN: str`, `ORIGIN_POLICY: str`, `LEGACY_PROVISION_SCHEMA: str`, `LEGACY_BENIGN_ORIGIN: str`, `CONFIG_RECEIPT_SCHEMA: str`, `PortPolicySnapshot`, `PortPolicyRefusal`, `classify_profile_metas(payload, profile_id, folder_id)`, `build_partial_update_body(profile_id, snapshot)`, and `configuration_receipt(code, flags)`.

- [ ] **Step 1: Write the failing happy-path classifier and exact-body tests**

```python
from integrations.chairman_surfaces import mas115_multilogin_port_policy as policy


PROFILE_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
FOLDER_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def _metas(*, ports=None, mode="mask", auto=True):
    fingerprint = {} if ports is None else {"ports": ports}
    return {
        "status": {
            "error_code": "",
            "http_code": 200,
            "message": "List of profiles metadata",
        },
        "data": {
            "profiles": [{
                "id": PROFILE_ID,
                "folder_id": FOLDER_ID,
                "browser_type": "mimic",
                "in_use_by": "",
                "is_auto_update": auto,
                "parameters": {
                    "flags": {"ports_masking": mode},
                    "fingerprint": fingerprint,
                    "storage": {"is_local": False, "save_service_worker": False},
                },
                "last_update_at": "before",
                "last_updated_by": "synthetic",
            }]
        },
    }


def test_default_masked_classifies_and_builds_only_exact_body():
    snapshot = policy.classify_profile_metas(
        _metas(), profile_id=PROFILE_ID, folder_id=FOLDER_ID,
    )
    assert snapshot.state == policy.DEFAULT_MASKED
    assert snapshot.auto_update_core is True
    assert policy.build_partial_update_body(PROFILE_ID, snapshot) == {
        "profile_id": PROFILE_ID,
        "auto_update_core": True,
        "parameters": {
            "flags": {"ports_masking": "mask"},
            "fingerprint": {"ports": [65535]},
        },
    }


def test_exact_configured_is_idempotent_and_not_mutable():
    snapshot = policy.classify_profile_metas(
        _metas(ports=[65535]), profile_id=PROFILE_ID, folder_id=FOLDER_ID,
    )
    assert snapshot.state == policy.EXACT_CONFIGURED
    with pytest.raises(policy.PortPolicyRefusal) as raised:
        policy.build_partial_update_body(PROFILE_ID, snapshot)
    assert raised.value.code == policy.UNSUPPORTED_PORT_STATE
```

- [ ] **Step 2: Run the focused tests and verify the module is missing**

Run:

```bash
/private/tmp/mastermind-fixed-port-repair.9Ju4RK/venv/bin/python -m pytest -q \
  tests/test_mas115_multilogin_port_policy.py::test_default_masked_classifies_and_builds_only_exact_body \
  tests/test_mas115_multilogin_port_policy.py::test_exact_configured_is_idempotent_and_not_mutable
```

Expected: collection fails with an import error for `mas115_multilogin_port_policy`.

- [ ] **Step 3: Implement constants, closed types, classifier, digest, and exact body**

```python
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass

CANARY_PORT = 65535
CANARY_ORIGIN = "http://127.0.0.1:65535"
ORIGIN_POLICY = "mas115_fixed_loopback_v1"
LEGACY_PROVISION_SCHEMA = "mastermind.mas115_nonseat_canary_provision.v2"
LEGACY_BENIGN_ORIGIN = "http://127.0.0.1:7777"
CONFIG_RECEIPT_SCHEMA = "mastermind.mas115_multilogin_port_configuration.v1"

DEFAULT_MASKED = "DEFAULT_MASKED"
EXACT_CONFIGURED = "EXACT_CONFIGURED"
UNSUPPORTED_PORT_STATE = "UNSUPPORTED_PORT_STATE"


class PortPolicyRefusal(ValueError):
    CODES = frozenset({"MALFORMED_PROFILE_METAS", UNSUPPORTED_PORT_STATE})

    def __init__(self, code: str):
        if code not in self.CODES:
            raise ValueError("unknown port-policy refusal")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class PortPolicySnapshot:
    state: str
    auto_update_core: bool
    preservation_digest: str


def _preservation_digest(profile: dict) -> str:
    preserved = copy.deepcopy(profile)
    preserved.pop("last_update_at", None)
    preserved.pop("last_updated_by", None)
    parameters = preserved["parameters"]
    parameters["flags"].pop("ports_masking", None)
    parameters["fingerprint"].pop("ports", None)
    material = json.dumps(preserved, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def classify_profile_metas(payload, *, profile_id: str, folder_id: str) -> PortPolicySnapshot:
    malformed = (
        not isinstance(payload, dict)
        or set(payload) != {"status", "data"}
        or payload.get("status") != {
            "error_code": "",
            "http_code": 200,
            "message": "List of profiles metadata",
        }
        or not isinstance(payload.get("data"), dict)
        or set(payload["data"]) != {"profiles"}
        or not isinstance(payload["data"].get("profiles"), list)
        or len(payload["data"]["profiles"]) != 1
    )
    if malformed:
        raise PortPolicyRefusal("MALFORMED_PROFILE_METAS")
    profile = payload["data"]["profiles"][0]
    required = {
        "id", "folder_id", "browser_type", "in_use_by", "is_auto_update",
        "parameters",
    }
    malformed = (
        not isinstance(profile, dict)
        or not required.issubset(profile)
        or not isinstance(profile_id, str)
        or not isinstance(folder_id, str)
        or profile.get("id") != profile_id
        or profile.get("folder_id") != folder_id
        or profile.get("browser_type") != "mimic"
        or profile.get("in_use_by") != ""
        or type(profile.get("is_auto_update")) is not bool
        or not isinstance(profile.get("parameters"), dict)
        or not isinstance(profile["parameters"].get("flags"), dict)
        or not isinstance(profile["parameters"].get("fingerprint"), dict)
    )
    if malformed:
        raise PortPolicyRefusal("MALFORMED_PROFILE_METAS")
    mode = profile["parameters"]["flags"].get("ports_masking")
    ports = profile["parameters"]["fingerprint"].get("ports", [])
    if not isinstance(ports, list) or any(type(item) is not int for item in ports):
        raise PortPolicyRefusal("MALFORMED_PROFILE_METAS")
    if mode == "mask" and ports == []:
        state = DEFAULT_MASKED
    elif mode == "mask" and ports == [CANARY_PORT]:
        state = EXACT_CONFIGURED
    else:
        raise PortPolicyRefusal(UNSUPPORTED_PORT_STATE)
    return PortPolicySnapshot(
        state=state,
        auto_update_core=profile["is_auto_update"],
        preservation_digest=_preservation_digest(profile),
    )


def build_partial_update_body(profile_id: str, snapshot: PortPolicySnapshot) -> dict:
    if snapshot.state != DEFAULT_MASKED:
        raise PortPolicyRefusal(UNSUPPORTED_PORT_STATE)
    return {
        "profile_id": profile_id,
        "auto_update_core": snapshot.auto_update_core,
        "parameters": {
            "flags": {"ports_masking": "mask"},
            "fingerprint": {"ports": [CANARY_PORT]},
        },
    }
```

Keep this validation literal: require the exact outer/status/data envelopes, one profile, matching string IDs, `browser_type=="mimic"`, `in_use_by==""`, `is_auto_update` as a non-subclassed boolean, dictionaries at `parameters`/`flags`/`fingerprint`, and a port list containing only non-boolean integers. Classify only `mask` plus absent/empty ports as `DEFAULT_MASKED`, and `mask` plus `[65535]` as `EXACT_CONFIGURED`; raise `UNSUPPORTED_PORT_STATE` for every other value.

- [ ] **Step 4: Add the full mutation/falsifier parameter matrix**

```python
@pytest.mark.parametrize(
    "mutation",
    (
        "wrong-envelope", "wrong-message", "two-profiles", "wrong-profile",
        "wrong-folder", "wrong-browser", "owned", "missing-auto", "integer-auto",
        "missing-parameters", "missing-flags", "missing-fingerprint",
        "boolean-port", "string-port", "duplicate-port", "extra-port",
        "natural", "custom", "unknown-mode",
    ),
)
def test_profile_metas_drift_never_classifies_as_mutable(mutation):
    payload = _mutated_metas(mutation)
    with pytest.raises(policy.PortPolicyRefusal):
        policy.classify_profile_metas(payload, profile_id=PROFILE_ID, folder_id=FOLDER_ID)


def test_preservation_digest_ignores_only_target_and_vendor_audit_fields():
    before = policy.classify_profile_metas(_metas(), profile_id=PROFILE_ID, folder_id=FOLDER_ID)
    after_payload = _metas(ports=[65535])
    row = after_payload["data"]["profiles"][0]
    row["last_update_at"] = "after"
    row["last_updated_by"] = "vendor-user"
    after = policy.classify_profile_metas(after_payload, profile_id=PROFILE_ID, folder_id=FOLDER_ID)
    assert before.preservation_digest == after.preservation_digest
    row["parameters"]["storage"]["save_service_worker"] = True
    drifted = policy.classify_profile_metas(after_payload, profile_id=PROFILE_ID, folder_id=FOLDER_ID)
    assert drifted.preservation_digest != before.preservation_digest
```

- [ ] **Step 5: Implement and test closed redacted configuration receipts**

```python
CONFIG_CODES = frozenset({
    "CONFIGURED", "ALREADY_CONFIGURED", "CONFIGURED_AFTER_RECONCILIATION",
    "AUTH_EXPIRED_NO_PROOF", "REJECTED_NO_PROOF", "EFFECT_UNKNOWN",
    "UNSUPPORTED_PORT_STATE", "PRESERVATION_DRIFT", "VENDOR_ERROR",
})


def configuration_receipt(
    code: str, *, updated: bool, reconciled: bool,
    preservation_unchanged: bool, auto_update_unchanged: bool,
    exact_profile_stopped: bool,
) -> dict:
    if code not in CONFIG_CODES:
        raise ValueError("unknown configuration result")
    return {
        "schema": CONFIG_RECEIPT_SCHEMA,
        "verdict": "PASS" if code in {
            "CONFIGURED", "ALREADY_CONFIGURED", "CONFIGURED_AFTER_RECONCILIATION",
        } else "HOLD" if code in {"EFFECT_UNKNOWN", "PRESERVATION_DRIFT"} else "REFUSED",
        "code": code,
        "updated": bool(updated),
        "reconciled": bool(reconciled),
        "predicates": {
            "preservation_unchanged": bool(preservation_unchanged),
            "auto_update_unchanged": bool(auto_update_unchanged),
            "exact_profile_stopped": bool(exact_profile_stopped),
        },
    }
```

Test exact top-level/predicate key sets and scan serialized receipts for `://`, profile/folder IDs, names, notes, proxy values, and synthetic credentials.

- [ ] **Step 6: Run the pure policy suite**

Run:

```bash
/private/tmp/mastermind-fixed-port-repair.9Ju4RK/venv/bin/python -m pytest -q \
  tests/test_mas115_multilogin_port_policy.py
```

Expected: PASS.

- [ ] **Step 7: Commit the pure policy unit**

```bash
git add \
  integrations/chairman_surfaces/mas115_multilogin_port_policy.py \
  tests/test_mas115_multilogin_port_policy.py
git commit -m "feat(mas115): define fixed Multilogin port policy"
```

---

### Task 2: Provision schema v3 and exact legacy migration

**Files:**

- Modify: `integrations/chairman_surfaces/nonseat_canary.py:64-98,194-429,1163-1205`
- Modify: `scripts/mas115_setup.py:187-257,318-405`
- Modify: `tests/test_nonseat_canary.py:43-114,880-930,1110-1170,2219-2268`
- Modify: `tests/test_mas115_setup.py:184-215,337-390`

**Interfaces:**

- Consumes: policy constants from Task 1 and the existing fresh three-seat census.
- Produces: `PROVISION_SCHEMA == "mastermind.mas115_nonseat_canary_provision.v3"`, strict v3 `load_provision(path, bindings_loader, now)`, `load_legacy_provision_for_migration(path, bindings_loader, now)`, and setup `_migrate_legacy_provision(path, bindings_loader, now)`.

- [ ] **Step 1: Write failing v3 and migration tests**

```python
def test_build_provision_uses_fixed_policy_not_origin():
    stopped = _mlx(1, running=False)
    provision = setup.build_provision(stopped, browser_type="mimic")
    assert provision == {
        "schema": "mastermind.mas115_nonseat_canary_provision.v3",
        "vendor": "multilogin",
        "profile_id": stopped["profile_id"],
        "folder_id": stopped["folder_id"],
        "browser_type": "mimic",
        "origin_policy": policy.ORIGIN_POLICY,
        "disposable_ack": canary.REQUIRED_ACK,
    }
    assert "benign_origin" not in provision


def test_legacy_migration_accepts_only_exact_v2_origin_and_preserves_identity(tmp_path):
    path = tmp_path / "provision.json"
    legacy = _legacy_v2_provision()
    setup._atomic_private_json(legacy, path)
    migrated = setup._migrate_legacy_provision(
        path, bindings_loader=_no_collision_loader, now=_NOW,
    )
    assert migrated["schema"] == canary.PROVISION_SCHEMA
    assert migrated["origin_policy"] == policy.ORIGIN_POLICY
    assert "benign_origin" not in migrated
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text()) == migrated


@pytest.mark.parametrize("origin", (
    "http://127.0.0.1:65535", "http://localhost:7777",
    "https://127.0.0.1:7777", "http://evil.example:7777",
))
def test_legacy_migration_refuses_every_nonhistorical_origin(tmp_path, origin):
    legacy = _legacy_v2_provision()
    legacy["benign_origin"] = origin
    path = _write_provision(tmp_path, legacy)
    assert setup._migrate_legacy_provision(
        path, bindings_loader=_no_collision_loader, now=_NOW,
    ) == (None, "DISALLOWED_TARGET")
```

- [ ] **Step 2: Run the focused tests and verify v2/field failures**

Run:

```bash
/private/tmp/mastermind-fixed-port-repair.9Ju4RK/venv/bin/python -m pytest -q \
  tests/test_mas115_setup.py::test_build_provision_uses_fixed_policy_not_origin \
  tests/test_mas115_setup.py::test_legacy_migration_accepts_only_exact_v2_origin_and_preserves_identity \
  tests/test_mas115_setup.py::test_legacy_migration_refuses_every_nonhistorical_origin
```

Expected: FAIL because the current schema is v2, `benign_origin` is still persisted, and the migration entrypoint does not exist.

- [ ] **Step 3: Implement shared strict provision validation**

In `nonseat_canary.py`:

```python
PROVISION_SCHEMA = "mastermind.mas115_nonseat_canary_provision.v3"
_PROVISION_ALLOWED_KEYS = frozenset({
    "schema", "vendor", "profile_id", "folder_id", "browser_type",
    "origin_policy", "disposable_ack",
})
_PROVISION_REQUIRED_KEYS_BASE = frozenset({
    "schema", "vendor", "profile_id", "origin_policy", "disposable_ack",
})


def load_legacy_provision_for_migration(path=None, *, bindings_loader=None, now=None):
    target = Path(path).expanduser() if path else Path(DEFAULT_PROVISION_PATH).expanduser()
    doc = _read_provision_document(target)
    if doc is None:
        return None, "PROVISION_MISSING"
    expected = {
        "schema", "vendor", "profile_id", "folder_id", "browser_type",
        "benign_origin", "disposable_ack",
    } if doc.get("vendor") == "multilogin" else {
        "schema", "vendor", "profile_id", "benign_origin", "disposable_ack",
    }
    if (
        set(doc) != expected
        or doc.get("schema") != policy.LEGACY_PROVISION_SCHEMA
        or doc.get("benign_origin") != policy.LEGACY_BENIGN_ORIGIN
    ):
        return None, "DISALLOWED_TARGET"
    candidate = {key: value for key, value in doc.items() if key != "benign_origin"}
    candidate["schema"] = PROVISION_SCHEMA
    candidate["origin_policy"] = policy.ORIGIN_POLICY
    return _validate_provision_document(
        candidate, bindings_loader=bindings_loader, now=now,
    )
```

The v3 validator requires `origin_policy == policy.ORIGIN_POLICY`, rejects `benign_origin`, retains exact UUID/case normalization and fresh non-collision behavior, and returns no dynamic detail. The legacy function must never accept a v3 file, unknown field, alternate origin spelling, alternate scheme/host/port, or incomplete bindings.

- [ ] **Step 4: Implement atomic setup migration and v3 creation**

```python
def build_provision(row: dict, *, browser_type: str | None) -> dict:
    manager, folder_id, profile_id = _identity(row)
    if row.get("running") is True:
        raise SetupRefusal("the disposable profile must be stopped before it can be provisioned")
    doc = {
        "schema": canary.PROVISION_SCHEMA,
        "vendor": manager,
        "profile_id": profile_id,
        "origin_policy": port_policy.ORIGIN_POLICY,
        "disposable_ack": canary.REQUIRED_ACK,
    }
    if manager == "multilogin":
        if browser_type not in ("mimic", "stealthfox"):
            raise SetupRefusal("the disposable Multilogin browser core must be positively identified")
        doc["folder_id"] = folder_id
        doc["browser_type"] = browser_type
    return doc


def _migrate_legacy_provision(path=canary.DEFAULT_PROVISION_PATH, *, bindings_loader=None, now=None):
    migrated, code = canary.load_legacy_provision_for_migration(
        path, bindings_loader=bindings_loader, now=now,
    )
    if migrated is None:
        return None, code
    _atomic_private_json(migrated, path)
    loaded, code = canary.load_provision(
        path, bindings_loader=bindings_loader, now=now,
    )
    return (loaded, None) if loaded is not None else (None, code)
```

Retain these exact browser/folder assignments from the current `build_provision`; do not widen the accepted vendors or cores.

- [ ] **Step 5: Update runtime/hermetic provision shape**

Make `assert_disposable(profile)` require both `origin_policy == ORIGIN_POLICY` and a runtime-only `benign_origin == CANARY_ORIGIN`. Make `allowed_url(url, benign_origin)` compare against `CANARY_ORIGIN` directly. Update `build_hermetic_harness(vendor)` and test helpers to produce v3 policy plus the derived live origin; stored-file tests must contain no origin.

- [ ] **Step 6: Run provision/setup suites**

Run:

```bash
/private/tmp/mastermind-fixed-port-repair.9Ju4RK/venv/bin/python -m pytest -q \
  tests/test_mas115_setup.py tests/test_nonseat_canary.py -k \
  'provision or disposable or origin or binding_census or allowed_url'
```

Expected: PASS.

- [ ] **Step 7: Commit schema and migration**

```bash
git add \
  integrations/chairman_surfaces/nonseat_canary.py \
  scripts/mas115_setup.py \
  tests/test_nonseat_canary.py \
  tests/test_mas115_setup.py
git commit -m "feat(mas115): bind provisions to fixed origin policy"
```

---

### Task 3: Fixed loopback binding and pre-Keychain self-test

**Files:**

- Modify: `integrations/chairman_surfaces/nonseat_canary.py:64-125`
- Modify: `integrations/chairman_surfaces/nonseat_canary_vendors.py:24-72,702-785,1011-1112`
- Modify: `tests/test_nonseat_canary.py:595-724,1074-1105,1682-1734`

**Interfaces:**

- Consumes: `policy.CANARY_PORT` and `policy.CANARY_ORIGIN` from Task 1; validated v3 provision from Task 2.
- Produces: `CANARY_PORT_UNAVAILABLE` canary refusal, `LoopbackBenignOrigin(token)` with no port argument, `self_test() -> bool`, and helper ordering `provision -> bind/self-test -> Keychain -> vendor client`.

- [ ] **Step 1: Write failing fixed-bind and no-fallback tests**

```python
def test_loopback_origin_binds_only_fixed_port_and_self_tests():
    origin = vendors.LoopbackBenignOrigin(token="integration-token")
    try:
        assert origin.base_url == policy.CANARY_ORIGIN
        assert origin.self_test() is True
        assert origin.saw("/a") is False
        assert origin.saw("/auth") is False
    finally:
        origin.close()


def test_busy_fixed_port_refuses_before_keychain_or_http(tmp_path):
    path = _write_v3_provision(tmp_path)
    calls = []

    def busy_origin(*, token):
        calls.append("origin")
        raise OSError("synthetic busy port")

    code = vendors.main(
        ["--vendor", "multilogin", "--provision-path", str(path)],
        stdout=io.StringIO(), bindings_loader=_no_collision_loader,
        origin_factory=busy_origin,
        credential_stream_factory=lambda: calls.append("keychain"),
        client_factory=lambda: calls.append("client"), now=_NOW,
    )
    assert code == 2
    assert calls == ["origin"]


def test_loopback_origin_constructor_has_no_port_parameter():
    assert tuple(inspect.signature(vendors.LoopbackBenignOrigin).parameters) == ("token",)
```

- [ ] **Step 2: Run the fixed-origin tests and observe dynamic-port/order failures**

Run:

```bash
/private/tmp/mastermind-fixed-port-repair.9Ju4RK/venv/bin/python -m pytest -q \
  tests/test_nonseat_canary.py::test_loopback_origin_binds_only_fixed_port_and_self_tests \
  tests/test_nonseat_canary.py::test_busy_fixed_port_refuses_before_keychain_or_http \
  tests/test_nonseat_canary.py::test_loopback_origin_constructor_has_no_port_parameter
```

Expected: FAIL because the server binds port zero, lacks `self_test`, and is currently created after Keychain/client.

- [ ] **Step 3: Implement fixed bind and local self-test**

```python
class LoopbackBenignOrigin:
    def __init__(self, token: str = "mas115-loopback-token"):
        self.token = token
        self._seen_paths = set()
        self._cookie_seen = False
        self._lock = threading.Lock()
        self._server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", _port_policy.CANARY_PORT), _CanaryRequestHandler,
        )
        if self._server.server_address != ("127.0.0.1", _port_policy.CANARY_PORT):
            self._server.server_close()
            raise _core.CanaryRefusal("CANARY_PORT_UNAVAILABLE")
        self._server.canary_origin = self
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        return _port_policy.CANARY_ORIGIN
```

Implement `self_test()` with a stdlib loopback-only HTTP connection to `/auth`, require 401 plus the expected challenge, then remove the self-test observation under the lock. It returns only `True`/`False` and never accepts a host, port, path, URL, or timeout from the caller.

- [ ] **Step 4: Reorder helper admission and close failures**

In `vendors.main`, construct and self-test the origin immediately after v3 provision/vendor agreement and before `_open_keychain_credential_pipe` or `BoundedHttpClient`. Map any bind/self-test exception to `CANARY_PORT_UNAVAILABLE`, close any constructed origin, and ensure neither Keychain nor vendor HTTP is reached. Add `CANARY_PORT_UNAVAILABLE` to `RESULT_CODES` and `DETAILS` with one static non-dynamic sentence.

- [ ] **Step 5: Replace the old blanket mutation falsifier with structural laws**

Retain bans on `httpx.patch`, `httpx.delete`, generic `_request` exposure, pointer/keyboard/evaluate/cookie-read surfaces, public binds, and caller-shaped port values. The test must allow the literal `/profile/partial_update` only in the secret-owning vendor file and assert it occurs exactly once in source after Task 4.

- [ ] **Step 6: Run fixed-origin, refusal-order, and existing privacy suites**

Run:

```bash
/private/tmp/mastermind-fixed-port-repair.9Ju4RK/venv/bin/python -m pytest -q \
  tests/test_nonseat_canary.py -k \
  'loopback or keychain or bindings_unavailable or no_click or webdriver_endpoint or receipt_hygiene'
```

Expected: PASS.

- [ ] **Step 7: Commit fixed origin**

```bash
git add \
  integrations/chairman_surfaces/nonseat_canary.py \
  integrations/chairman_surfaces/nonseat_canary_vendors.py \
  tests/test_nonseat_canary.py
git commit -m "fix(mas115): bind canary origin before credential access"
```

---

### Task 4: Exact Multilogin configuration transaction and no-retry reconciliation

**Files:**

- Modify: `integrations/chairman_surfaces/nonseat_canary_vendors.py:88-170,344-652,1011-1112`
- Modify: `tests/test_nonseat_canary.py:1208-1320,1741-1924,1948-2212`
- Modify: `tests/test_mas115_multilogin_port_policy.py`

**Interfaces:**

- Consumes: `policy.classify_profile_metas`, `policy.build_partial_update_body`, `policy.configuration_receipt`, existing `_profile_inventory_item`, and existing `_profile_state`.
- Produces: fixed transport `_mlx_profile_metas(credential, profile_id)`, fixed transport `_mlx_configure_canary_port(credential, profile_id, snapshot)`, `MultiloginClient.port_policy_snapshot(profile_ref)`, and `MultiloginClient.configure_canary_port(profile_ref)`.

- [ ] **Step 1: Extend the synthetic exact transport and write failing success/idempotence tests**

```python
class _ExactMultiloginTransport:
    def __init__(self, browser_type="mimic"):
        self.calls = []
        self.state = "stopped"
        self.browser_type = browser_type
        self.ports = []
        self.auto_update = False
        self.partial_update_response = _success(None, "Profile successfully updated")

    def _mlx_profile_metas(self, credential, profile_id):
        self.calls.append(("metas", profile_id))
        return vendors._BoundedResponse(200, _metas_payload(
            profile_id=profile_id, folder_id="f1", ports=self.ports,
            auto=self.auto_update,
        ))

    def _mlx_configure_canary_port(self, credential, profile_id, snapshot):
        self.calls.append(("configure", profile_id, snapshot.auto_update_core))
        if self.partial_update_response is not None:
            self.ports = [policy.CANARY_PORT]
        return self.partial_update_response


def test_configure_canary_port_preserves_auto_update_and_reads_back():
    transport = _ExactMultiloginTransport()
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"), transport)
    receipt = client.configure_canary_port({"profile_id": "p1", "folder_id": "f1"})
    assert receipt["code"] == "CONFIGURED"
    assert transport.calls == [
        ("search", "f1", 0), ("status", "p1"), ("metas", "p1"),
        ("configure", "p1", False),
        ("search", "f1", 0), ("status", "p1"), ("metas", "p1"),
    ]


def test_configure_canary_port_is_idempotent_without_update():
    transport = _ExactMultiloginTransport()
    transport.ports = [policy.CANARY_PORT]
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"), transport)
    receipt = client.configure_canary_port({"profile_id": "p1", "folder_id": "f1"})
    assert receipt["code"] == "ALREADY_CONFIGURED"
    assert not any(call[0] == "configure" for call in transport.calls)
```

- [ ] **Step 2: Run the focused tests and verify missing transport/client APIs**

Run:

```bash
/private/tmp/mastermind-fixed-port-repair.9Ju4RK/venv/bin/python -m pytest -q \
  tests/test_nonseat_canary.py::test_configure_canary_port_preserves_auto_update_and_reads_back \
  tests/test_nonseat_canary.py::test_configure_canary_port_is_idempotent_without_update
```

Expected: FAIL because `configure_canary_port` does not exist.

- [ ] **Step 3: Implement the two fixed HTTP methods**

```python
def _mlx_profile_metas(self, credential, profile_id: str):
    return self._request(
        "POST", _MLX_CLOUD_ORIGIN, "/profile/metas",
        headers=self._bearer(credential), json_body={"ids": [profile_id]},
    )


def _mlx_configure_canary_port(self, credential, profile_id: str, snapshot):
    body = _port_policy.build_partial_update_body(profile_id, snapshot)
    if body != {
        "profile_id": profile_id,
        "auto_update_core": snapshot.auto_update_core,
        "parameters": {
            "flags": {"ports_masking": "mask"},
            "fingerprint": {"ports": [_port_policy.CANARY_PORT]},
        },
    }:
        return None
    return self._request(
        "POST", _MLX_CLOUD_ORIGIN, "/profile/partial_update",
        headers=self._bearer(credential), json_body=body,
    )
```

No generic profile configuration method or caller-provided body is added.

- [ ] **Step 4: Implement exact read-only policy preflight**

`port_policy_snapshot(profile_ref)` must, in this exact order, require credential, validate the exact ref, complete the cloud census, require one Mimic item with empty `in_use_by` and empty/missing `locked_by`, require exact launcher `stopped`, fetch Profile Metas, classify the exact record, and return a `PortPolicySnapshot`. Explicit 401/403 raises `AUTH_EXPIRED`; every other malformed/unknown result raises `VENDOR_ERROR` or `UNSUPPORTED_PORT_STATE` without calling the update method.

- [ ] **Step 5: Implement one update plus post-read and reconciliation**

```python
def configure_canary_port(self, profile_ref: dict) -> dict:
    before = self.port_policy_snapshot(profile_ref)
    if before.state == _port_policy.EXACT_CONFIGURED:
        return _port_policy.configuration_receipt(
            "ALREADY_CONFIGURED", updated=False, reconciled=False,
            preservation_unchanged=True, auto_update_unchanged=True,
            exact_profile_stopped=True,
        )
    if before.state != _port_policy.DEFAULT_MASKED:
        return _port_policy.configuration_receipt(
            "UNSUPPORTED_PORT_STATE", updated=False, reconciled=False,
            preservation_unchanged=False, auto_update_unchanged=False,
            exact_profile_stopped=True,
        )
    response = self._client._mlx_configure_canary_port(
        self._credential, profile_ref["profile_id"], before,
    )
    if response is not None and response.status_code in (401, 403):
        return _port_policy.configuration_receipt(
            "AUTH_EXPIRED_NO_PROOF", updated=False, reconciled=False,
            preservation_unchanged=False, auto_update_unchanged=False,
            exact_profile_stopped=True,
        )
    if _is_exact_partial_update_success(response):
        return self._post_configuration_receipt(
            before, profile_ref, response_was_ambiguous=False,
        )
    if _is_explicit_partial_update_rejection(response):
        return _port_policy.configuration_receipt(
            "REJECTED_NO_PROOF", updated=False, reconciled=False,
            preservation_unchanged=False, auto_update_unchanged=False,
            exact_profile_stopped=True,
        )
    return self._post_configuration_receipt(
        before, profile_ref, response_was_ambiguous=True,
    )
```

Add exactly one helper `_post_configuration_receipt(before, profile_ref, *, response_was_ambiguous)` that calls `port_policy_snapshot` exactly once. It returns success only when post-state is `EXACT_CONFIGURED`, auto-update equals `before.auto_update_core`, preservation digest equals `before.preservation_digest`, and stopped-state preflight succeeds. It returns `CONFIGURED_AFTER_RECONCILIATION` only for an ambiguous response with exact successful read-back. A post-state still `DEFAULT_MASKED` after an ambiguous response returns `EFFECT_UNKNOWN`, never a second update. Any preservation mismatch returns `PRESERVATION_DRIFT`.

- [ ] **Step 6: Add explicit rejection, ambiguity, drift, and no-retry tests**

```python
@pytest.mark.parametrize("response", (
    None,
    vendors._BoundedResponse(200, {"renamed": "response"}),
    vendors._BoundedResponse(500, None),
))
def test_ambiguous_update_never_retries_and_only_reconciles_read_only(response):
    transport = _ExactMultiloginTransport()
    transport.partial_update_response = response
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"), transport)
    receipt = client.configure_canary_port({"profile_id": "p1", "folder_id": "f1"})
    assert sum(call[0] == "configure" for call in transport.calls) == 1
    assert receipt["code"] in {"EFFECT_UNKNOWN", "CONFIGURED_AFTER_RECONCILIATION"}
    assert transport.calls[-3:][0][0] == "search"


def test_post_update_non_target_drift_vetoes_success():
    transport = _ExactMultiloginTransport()
    transport.mutate_storage_after_update = True
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"), transport)
    receipt = client.configure_canary_port({"profile_id": "p1", "folder_id": "f1"})
    assert receipt["code"] == "PRESERVATION_DRIFT"
    assert receipt["verdict"] == "HOLD"
```

Also cover 401/403, explicit 400 rejection, wrong success message, `natural`, extra ports, running/owned/locked state, wrong folder/profile/browser, and expired credential before configuration.

- [ ] **Step 7: Test exact serialized request and source-level mutation allowlist**

Use `httpx.MockTransport` to assert the only new vendor request is `POST https://api.multilogin.com/profile/partial_update`, the body equals the approved dictionary, `follow_redirects=False`, `trust_env=False`, and Authorization is present only inside the transport. Source tests must show exactly one literal `"/profile/partial_update"`, no `httpx.patch/delete`, no generic profile update endpoint, and no public method that accepts a body, URL, port, or profile field map.

- [ ] **Step 8: Run configuration and existing exact-vendor suites**

Run:

```bash
/private/tmp/mastermind-fixed-port-repair.9Ju4RK/venv/bin/python -m pytest -q \
  tests/test_mas115_multilogin_port_policy.py \
  tests/test_nonseat_canary.py -k \
  'configure_canary_port or multilogin or bounded_client or profile_config_mutation or receipt'
```

Expected: PASS.

- [ ] **Step 9: Commit configuration transaction**

```bash
git add \
  integrations/chairman_surfaces/nonseat_canary_vendors.py \
  tests/test_nonseat_canary.py \
  tests/test_mas115_multilogin_port_policy.py
git commit -m "feat(mas115): configure exact disposable canary port"
```

---

### Task 5: Operator command and unattended canary policy enforcement

**Files:**

- Modify: `scripts/mas115_setup.py:252-405`
- Modify: `integrations/chairman_surfaces/nonseat_canary_vendors.py:1011-1116`
- Modify: `tests/test_mas115_setup.py:337-390`
- Modify: `tests/test_nonseat_canary.py:1558-1734`
- Modify: `docs/CHAIRMAN_CONTROL_ROOM.md:93-168`

**Interfaces:**

- Consumes: setup migration from Task 2, fixed origin from Task 3, and `MultiloginClient.configure_canary_port`/`port_policy_snapshot` from Task 4.
- Produces: `python3 scripts/mas115_setup.py configure-canary-port --vendor multilogin`; ordinary `run-canary` refuses unless policy is already exact and never calls the update method.

- [ ] **Step 1: Write failing setup command-routing tests**

```python
def test_configure_command_migrates_then_routes_fixed_default_provision(monkeypatch):
    calls = []
    monkeypatch.setattr(setup, "_migrate_legacy_provision", lambda *a, **k: ({"ok": True}, None))
    monkeypatch.setattr(setup.vendors, "main", lambda argv: calls.append(argv) or 0)
    assert setup.main(["configure-canary-port", "--vendor", "multilogin"]) == 0
    assert calls == [[
        "configure-canary-port",
        "--vendor", "multilogin",
        "--provision-path", str(Path(canary.DEFAULT_PROVISION_PATH).expanduser()),
    ]]


def test_run_canary_routes_run_operation_without_update_authority(monkeypatch):
    calls = []
    monkeypatch.setattr(setup.vendors, "main", lambda argv: calls.append(argv) or 0)
    assert setup.main(["run-canary", "--vendor", "multilogin"]) == 0
    assert calls[0][0] == "run"
```

- [ ] **Step 2: Run setup-routing tests and verify the command is absent**

Run:

```bash
/private/tmp/mastermind-fixed-port-repair.9Ju4RK/venv/bin/python -m pytest -q \
  tests/test_mas115_setup.py -k 'configure_command or run_canary_routes'
```

Expected: FAIL because `configure-canary-port` and vendor operations do not exist.

- [ ] **Step 3: Add the setup subcommand and exact vendor operation**

Add `configure-canary-port` to `mas115_setup.py` with only `--vendor` choices. It must refuse GoLogin before migration, call the exact v2 migration against the default provision path, reload v3, then call the vendor helper with the literal operation. Do not accept `--port`, `--profile-id`, `--folder-id`, `--body`, `--endpoint`, `--origin`, or a caller-selected provision path.

Add optional positional `operation` to `nonseat_canary_vendors.main`:

```python
parser.add_argument(
    "operation", nargs="?", default="run",
    choices=("run", "configure-canary-port"),
)
```

The existing direct invocation without an operation remains equivalent to `run` for backward compatibility.

- [ ] **Step 4: Route configuration and enforce exact policy on run**

After v3 provision, fixed bind/self-test, Keychain, and client construction:

```python
profile_ref = {
    "profile_id": provision["profile_id"],
    "folder_id": provision["folder_id"],
}
if args.operation == "configure-canary-port":
    receipt = vendor_client.configure_canary_port(profile_ref)
    print(json.dumps(receipt, indent=2, sort_keys=True), file=out)
    return 0 if receipt["verdict"] == "PASS" else 3 if receipt["verdict"] == "HOLD" else 2

snapshot = vendor_client.port_policy_snapshot(profile_ref)
if snapshot.state != _port_policy.EXACT_CONFIGURED:
    return _emit_refusal(out, args.vendor, "UNSUPPORTED_PORT_STATE")
# Continue into the existing matrix; no configuration call is reachable here.
```

Add `UNSUPPORTED_PORT_STATE` as a fixed redacted canary result code. In ordinary-run tests, inject a transport whose `_mlx_configure_canary_port` raises if touched and prove the matrix reaches start only after exact Metas classification.

- [ ] **Step 5: Add post-matrix exact-policy verification**

After `run_matrix` cleanup, call `port_policy_snapshot(profile_ref)` once more and require `EXACT_CONFIGURED`; otherwise force the returned verdict to FAIL using a fixed redacted postflight code without rewriting C0-C10 evidence. Compare pre/post auto-update and preservation digest. Add top-level `port_policy` predicates only if the existing receipt allowlist is explicitly expanded and hygiene tests prove no private value; otherwise emit a fixed C10 failure code. Prefer the smaller C10 failure update to avoid a receipt schema bump.

- [ ] **Step 6: Update operator documentation**

Document the exact sequence:

```text
python3 scripts/mas115_setup.py status
python3 scripts/mas115_setup.py credential --vendor multilogin
python3 scripts/mas115_setup.py configure-canary-port --vendor multilogin
python3 scripts/mas115_setup.py run-canary --vendor multilogin
```

State that credential enrollment is native/hidden, configuration is one exact idempotent update on the stopped disposable profile, run-canary cannot update, fixed port is loopback-only, and live C0-C10 proves only the non-seat substrate.

- [ ] **Step 7: Run setup, helper-main, matrix, and docs contract tests**

Run:

```bash
/private/tmp/mastermind-fixed-port-repair.9Ju4RK/venv/bin/python -m pytest -q \
  tests/test_mas115_setup.py \
  tests/test_mas115_multilogin_port_policy.py \
  tests/test_nonseat_canary.py
```

Expected: PASS.

- [ ] **Step 8: Commit operator flow**

```bash
git add \
  scripts/mas115_setup.py \
  integrations/chairman_surfaces/nonseat_canary_vendors.py \
  tests/test_mas115_setup.py \
  tests/test_nonseat_canary.py \
  docs/CHAIRMAN_CONTROL_ROOM.md
git commit -m "feat(mas115): enforce configured port on unattended canary"
```

---

### Task 6: Full verification, adversarial review, and delivery carrier

**Files:**

- Verify: all files changed in Tasks 1-5
- Modify only if a verification failure proves a defect: the smallest owning file and its exact test

**Interfaces:**

- Consumes: all prior task outputs.
- Produces: clean authoritative gate, redaction proof, exact diff/commit evidence, and one reviewable GitHub carrier.

- [ ] **Step 1: Run source and shell validation**

```bash
/private/tmp/mastermind-fixed-port-repair.9Ju4RK/venv/bin/python -m compileall -q \
  app bot brain bridge common control_plane data_layer integrations loop portfolio scripts
find scripts ops/executive_os -type f -name '*.sh' -print0 | xargs -0 -n1 bash -n
```

Expected: exit 0.

- [ ] **Step 2: Run the authoritative discovery-first repository gate**

```bash
/private/tmp/mastermind-fixed-port-repair.9Ju4RK/venv/bin/python scripts/ci_pytest.py
```

Expected: `excluded=0`, every discovered `tests/**/test_*.py` module included, and pytest exit 0.

- [ ] **Step 3: Clean only known generated test artifacts and prove the worktree**

If the census tests regenerate `data/census/CENSUS.md` or `data/census/latest.json`, restore only those known tracked test artifacts to `HEAD`. Remove only a generated `mastermind.egg-info/` directory created by the isolated editable install. Then run:

```bash
git status --short
git diff --check
git log --oneline --decorate -8
```

Expected: only intentional MAS-115 files differ before the final commit; no unrelated dirt.

- [ ] **Step 4: Perform a fresh self-review against every spec section**

Check and record:

```text
1. Port is literal 65535 and bound only to 127.0.0.1.
2. No public parameter can choose port/origin/profile/body/endpoint.
3. v2 migration accepts only the exact historical origin and writes 0600 v3.
4. Keychain follows provision + seat census + fixed-port self-test.
5. Metas/search/status precede the sole update.
6. Exact update preserves auto-update and has no extra keys.
7. Ambiguous effects never call update twice.
8. Ordinary run cannot reach update.
9. Post-read and post-matrix checks enforce stopped/exact/preserved state.
10. Receipts contain no private or secret value.
11. Chairman profiles are absent from every vendor lifecycle/config call.
12. GoLogin remains unsupported.
```

Use `rg`/AST tests to falsify each structural claim; do not accept prose inspection alone.

- [ ] **Step 5: Run the verification-before-completion skill and record exact evidence**

Re-run focused MAS-115 suites after any review fix, then run `scripts/ci_pytest.py` again. Record the final `HEAD`, base, file list, test-module counts, and clean status. Do not describe live Multilogin behavior as repaired at this point.

- [ ] **Step 6: Push the single branch and open one pull request**

```bash
git push -u origin codex/mas115-fixed-port-20260824-9ju4rk
gh pr create \
  --base master \
  --head codex/mas115-fixed-port-20260824-9ju4rk \
  --title "MAS-115: repair disposable Multilogin canary with fixed loopback port" \
  --body-file /private/tmp/mas115-fixed-port-pr-body.md
```

Build `/private/tmp/mas115-fixed-port-pr-body.md` with a concise summary, authority/spec link, exact scope/non-goals, test evidence, privacy boundary, and explicit `BUILT_NOT_PROVEN` live status. Never include a token, profile/folder ID, private URL, response body, or memory citation.

- [ ] **Step 7: Inspect hosted CI and review the exact PR diff**

```bash
gh pr checks --watch <created-pr-number>
gh pr diff <created-pr-number> --name-only
gh pr view <created-pr-number> --json headRefOid,baseRefName,mergeStateStatus,statusCheckRollup
```

Expected: head SHA matches local final HEAD; authoritative CI green; only approved files changed. Resolve failures through the same carrier and rerun local gates before updating the PR.

---

### Task 7: One-shot live configuration and C0-C10 production-path proof

**Files:**

- No repository-file edits during the live operation.
- Durable Agent OS updates occur only after exact proof, in the normal Macro carrier, as a separate governed closeout change.

**Interfaces:**

- Consumes: exact merged Mastermind release, current native Multilogin credential, current v3 provision, fresh Chairman-seat bindings, stopped disposable profile, and free `127.0.0.1:65535`.
- Produces: redacted configuration receipt, redacted full C0-C10 receipt, exact cleanup proof, deployment/health evidence, and durable handoff facts.

- [ ] **Step 1: Merge only after hosted CI and exact-head review**

Re-pin protected master and PR head immediately before merge. Merge through the repository's normal protected workflow; record merge commit separately from the PR head. If master moved incompatibly, reconcile the same branch rather than creating a new carrier.

- [ ] **Step 2: Install/deploy the exact merged release before live proof**

Use the repository's accepted delivery workflow. Record exact merged SHA, install target, service state, and health output. If the existing dedicated-worker auth gate still blocks full service arming, report the host install as blocked separately; the non-seat helper may be run directly from the exact merged checkout only when repository policy permits it.

- [ ] **Step 3: Satisfy the native credential gate without exposing the token**

The current stored short-lived token is expired. Enroll one current token only through:

```text
python3 scripts/mas115_setup.py credential --vendor multilogin
```

The Chairman pastes into the echo-disabled native prompt. Do not request or capture the value in chat, argv, environment, shell variables, logs, or receipts. If a current automation credential already exists in the same fixed Keychain item and passes the read-only preflight, no paste is needed.

- [ ] **Step 4: Capture redacted before-state evidence**

Run sanitized `status`, record only environment counts and readiness booleans, confirm three enrolled Chairman seats, v3 provision ready, exact disposable stopped, and fixed port free. Record other-profile process count but no process arguments or identifiers.

- [ ] **Step 5: Run the one-shot exact configuration command**

```text
python3 scripts/mas115_setup.py configure-canary-port --vendor multilogin
```

Accept only `CONFIGURED`, `ALREADY_CONFIGURED`, or `CONFIGURED_AFTER_RECONCILIATION` with every predicate true. On `AUTH_EXPIRED_NO_PROOF` or `REJECTED_NO_PROOF`, stop. On `EFFECT_UNKNOWN` or `PRESERVATION_DRIFT`, do not rerun; retain the same carrier and perform only the command's read-only reconciliation/reporting path.

- [ ] **Step 6: Run the unattended canary exactly once**

```text
python3 scripts/mas115_setup.py run-canary --vendor multilogin
```

Require C0-C10 PASS, `benign_origin_observed=true`, navigated page membership, state persistence, exact-profile process evidence, exact cleanup stopped, other-profile process count unchanged, exact port policy after cleanup, and no configuration request during the matrix.

- [ ] **Step 7: Capture redacted post-state and capability ledger**

Re-run sanitized status and exact stopped/policy reads. Record distinct states: merge, deployment, configuration, C0-C10, cleanup, host service arming, and Chairman foreground proof. Only the disposable substrate may move to `PROVEN_LIVE`; MAS-115 P0B remains incomplete until the separately governed foreground-seat proof.

- [ ] **Step 8: Update durable Agent OS records through the normal Macro carrier**

Record that the old credential/search blockers are superseded by live evidence; record the fixed-port root cause and exact allowlist decision; attach redacted proof references; preserve any host auth/OAuth/foreground blockers; set the exact next action. Do not create a new lifecycle, queue, or memory store.

- [ ] **Step 9: Resume Executive OS host install and agent CLI/OAuth readiness**

Return to the existing G4 carrier/state. Reconcile the dedicated-worker auth gate, then verify the existing execution-profile/MCP/plugin capability registry and worker supervisor from the exact deployed release. Treat OAuth enrollment as a native credential/permission gate; do not expose or copy agent session stores. Keep Agent OS organizational state and Executive Runtime worker lifecycle separate.
