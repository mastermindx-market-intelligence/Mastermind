"""Run the hash-bound patch against a disposable copy of the existing broker.

No native path, credential, live lease database or provider is used. This is
source proof of a proposed patch, not proof that the patch is installed.
"""
import ast
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "ops/native_fabric/patches/lease_broker_model_planning.patch"
BASE = ROOT / "tests/fixtures/native_fabric/lease_broker.before.py.txt"
MANIFEST = PATCH.with_suffix(".json")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def native(tmp_path, monkeypatch):
    manifest = json.loads(MANIFEST.read_text())
    before = BASE.read_bytes()
    assert _sha(before) == manifest["before_sha256"]
    assert _sha(PATCH.read_bytes()) == manifest["patch_sha256"]
    module_path = tmp_path / "lease_broker.py"
    module_path.write_bytes(before)
    subprocess.run(["patch", "-s", "-p1", "-i", str(PATCH)], cwd=tmp_path,
                   check=True, capture_output=True, text=True)
    assert _sha(module_path.read_bytes()) == manifest["after_sha256"]
    name = "native_broker_fixture_" + _sha(str(tmp_path).encode())[:16]
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    accounts = {
        "providers": {
            "glm": {"enabled": True, "accounts": [
                {"name": f"fixture-{i}", "per_account_cap": 10,
                 "per_model_caps": {"glm-5.3": 5, "glm-5.3-flash": 20}}
                for i in range(3)
            ]},
            "minimax": {"enabled": True, "accounts": [
                {"name": "fixture-mm", "per_account_cap": 7}
            ]},
        },
    }
    config = tmp_path / "accounts.yaml"
    config.write_text(json.dumps(accounts))
    broker = module.Broker(
        db_path=str(tmp_path / "leases.sqlite"), lock_path=str(tmp_path / "leases.lock"),
        accounts_path=str(config), now_fn=lambda: 1700000000.0,
        check_pid=False, external_gates=False,
        grok_marker=str(tmp_path / "NO_GROK_MARKER"),
        status_json=str(tmp_path / "status.json"),
    )
    monkeypatch.setattr(broker, "_window_remaining", lambda _: "UNKNOWN_TEST_ONLY")
    return module, broker, accounts, config, module_path


def _hold(broker, model, account, count):
    for _ in range(count):
        result = broker.acquire(orchestrator_id="fixture-owner", pool="glm",
            account=account, task_class="build", model=model, pid=1, wait=0)
        assert result.ok, result.reason


def _plan(broker, model, need=30):
    rows = broker.plan("build", need, "fixture-owner", pool="glm", model=model)
    assert len(rows) == 1
    return rows[0]


def test_full_glm_is_fifteen_not_thirty_across_three_idle_accounts(native):
    _, br, _, _, _ = native
    row = _plan(br, "glm-5.3")
    assert row["grant_now"] == 15
    assert row["model_limit_state"] == "APPLIED"
    assert row["model_capacity_checked"] is True
    assert row["quota_capacity_checked"] is False


def test_flash_model_cap_does_not_override_total_account_cap(native):
    _, br, _, _, _ = native
    assert _plan(br, "glm-5.3-flash")["grant_now"] == 30  # Not 3 * 20.


def test_full_and_flash_cannot_double_count_shared_account_capacity(native):
    _, br, _, _, _ = native
    for i in range(3):
        _hold(br, "glm-5.3", f"fixture-{i}", 5)
    assert _plan(br, "glm-5.3")["grant_now"] == 0
    assert _plan(br, "glm-5.3-flash")["grant_now"] == 15
    for i in range(3):
        _hold(br, "glm-5.3-flash", f"fixture-{i}", 5)
    assert _plan(br, "glm-5.3-flash")["grant_now"] == 0


def test_model_headroom_is_intersected_with_each_accounts_actual_free_slots(native):
    _, br, _, _, _ = native
    _hold(br, "glm-5.3-flash", "fixture-0", 9)
    assert _plan(br, "glm-5.3")["grant_now"] == 11  # 1 + 5 + 5, not 15 or 21.


def test_legacy_untagged_leases_still_count_against_full_glm(native):
    _, br, _, _, _ = native
    _hold(br, "", "fixture-0", 1)
    assert _plan(br, "glm-5.3")["grant_now"] == 14
    assert _plan(br, "glm-5.3-flash")["grant_now"] == 29


def test_unknown_glm_model_is_not_unlimited(native):
    _, br, _, _, _ = native
    row = _plan(br, "glm-not-enrolled")
    assert row["grant_now"] == 0
    assert row["model_limit_state"] == "UNKNOWN"
    assert row["model_capacity_checked"] is False


def test_pool_only_legacy_calls_are_honestly_nonbinding(native):
    _, br, _, _, _ = native
    rows = br.plan("build", 30, "fixture-owner")
    assert {r["pool"]: r["grant_now"] for r in rows} == {"glm": 30, "minimax": 7}
    for row in rows:
        assert row["model"] is None
        assert row["model_limit_state"] == "NOT_REQUESTED"
        assert row["selection_is_commitment"] is False
        assert row["claim_time_revalidation_required"] is True
        assert row["future_capacity_guaranteed"] is False
        assert row["wait_est_basis"] == "lease_ttl_hint_not_completion_or_quota_reset"


def test_non_glm_account_only_plan_does_not_claim_model_or_quota_proof(native):
    _, br, _, _, _ = native
    row = br.plan("build", 100, "fixture-owner", pool="minimax", model="MiniMax-M3")[0]
    assert row["grant_now"] == 7
    assert row["model_limit_state"] == "ACCOUNT_ONLY"
    assert row["model_capacity_checked"] is False
    assert row["quota_capacity_checked"] is False


def test_model_planning_never_creates_new_leases_or_demand(native):
    _, br, _, _, _ = native
    _hold(br, "glm-5.3", "fixture-0", 2)
    def counts():
        with br._conn() as conn:
            return tuple(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                         for table in ("leases", "waiters"))
    before = counts()
    _plan(br, "glm-5.3")
    _plan(br, "glm-5.3-flash")
    assert counts() == before


@pytest.mark.parametrize("need", [-1, True, 1.5, "2"])
def test_invalid_demand_is_rejected(native, need):
    _, br, _, _, _ = native
    with pytest.raises(ValueError):
        br.plan("build", need, "fixture-owner")


def test_model_specific_api_requires_a_known_pool(native):
    _, br, _, _, _ = native
    with pytest.raises(ValueError):
        br.plan("build", 1, "fixture-owner", model="glm-5.3")
    with pytest.raises(ValueError):
        br.plan("build", 1, "fixture-owner", pool="missing", model="glm-5.3")
    assert _plan(br, "GLM-5.3", need=0)["grant_now"] == 0


def test_real_json_cli_forwards_model_and_pool(native, monkeypatch, capsys):
    module, br, _, _, _ = native
    monkeypatch.setattr(module, "default_broker", lambda: br)
    assert module.main(["plan", "--need", "30", "--pool", "glm", "--model", "glm-5.3",
                        "--orchestrator-id", "fixture-owner", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data[0]["grant_now"] == 15
    assert data[0]["model"] == "glm-5.3"


@pytest.mark.parametrize("flags", [["--need", "-1"], ["--need", "1", "--model", "glm-5.3"]])
def test_invalid_cli_refuses_before_constructing_a_live_broker(native, monkeypatch, flags):
    module, _, _, _, _ = native
    def forbidden():
        raise AssertionError("must not open or mutate a lease store")
    monkeypatch.setattr(module, "default_broker", forbidden)
    with pytest.raises(SystemExit) as exc:
        module.main(["plan", *flags])
    assert exc.value.code == 2


def test_admission_and_lifecycle_function_bodies_are_unchanged(native):
    _, _, _, _, patched = native
    def bodies(text):
        return {n.name: ast.dump(n, include_attributes=False) for n in ast.walk(ast.parse(text))
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    old, new = bodies(BASE.read_text()), bodies(patched.read_text())
    assert old.keys() == new.keys()
    for name in old.keys() - {"plan", "_plan_pool", "_print_plan", "main"}:
        assert old[name] == new[name], name
