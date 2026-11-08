"""Inert public-source assembly. No selected runtime/DB/provider/grant is read."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import sys

import pytest
from ops.native_fabric.provider_plans import compose
from tests.test_current116_maintenance_guard_composition import current_source

PROFILE = "current116-protected-memory"
MEMORY_FUNCTIONS = {"_connect", "__init__", "_lock", "_conn", "_try_acquire_in_transaction"}
EXACT_REPLACEMENTS = {"ext/" + name + ".py" for name in (
    "artifact_delivery", "fabric_operator_contract", "fabric_operator_owner", "fabric_task",
    "lease_broker", "provider_outcome", "run_observation_delivery")}
ADDITIONS = {"ext/fabric_memory_view.py", "ext/protected_memory_economic.py"}
ROOT = Path(__file__).resolve().parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def dump(node):
    return ast.dump(node, include_attributes=False)


@pytest.fixture(scope="module")
def memory_parent(current_source,tmp_path_factory):
    # Explicit UNSELECTED public postimage descriptor; never an installed receipt.
    parent=tmp_path_factory.mktemp("memory-expected40")/'source'
    compose.compose(current_source,parent,profile_name="current116-maintenance-guard")
    profile=json.loads((compose.HERE/'memory118/profile.json').read_text())
    assert json.loads((parent/'FILES.json').read_text())==profile['base_files']
    assert profile['expected_predecessor']['state']=='UNSELECTED_SOURCE_DESCRIPTOR_ONLY'
    assert profile['expected_predecessor']['actual_selection_observed'] is False
    (parent/'RELEASE.json').write_text(json.dumps({'digest':profile['base_selection']['generation'],
        'files':profile['base_files'],'fixture_premise':'UNSELECTED public expected predecessor only'}))
    return parent


@pytest.fixture(scope="module")
def joined(memory_parent, tmp_path_factory):
    output = tmp_path_factory.mktemp("memory118-parent") / "source"
    result = compose.compose(memory_parent, output, profile_name=PROFILE)
    assert result["files"] == 118
    assert result["publication_performed"] is result["selection_performed"] is False
    return output


def test_exact116_to118_retains_every_incumbent_member(memory_parent, joined):
    profile = json.loads((compose.HERE / "memory118/profile.json").read_text())
    base, final = profile["base_files"], profile["files"]
    assert len(base) == 116 and len(final) == 118
    assert set(final) - set(base) == ADDITIONS and set(base) <= set(final)
    assert {name for name in base if base[name] != final[name]} == EXACT_REPLACEMENTS
    assert base == json.loads((memory_parent / "FILES.json").read_text())
    for name, expected in final.items():
        assert sha((joined / name).read_bytes()) == expected
    assert set(profile["patches"]) == {"ext/fabric_task.py", "ext/lease_broker.py"}
    assert set(profile["source_map"]) == (EXACT_REPLACEMENTS | ADDITIONS) - set(profile["patches"])
    assert not (joined / "CURRENT.json").exists() and not (joined / "ext/broker").exists()


def broker_projection(raw):
    module = ast.parse(raw)
    changed = {}
    module.body = [node for node in module.body if not (
        isinstance(node, ast.Import) and len(node.names) == 1 and node.names[0].name == "stat"
        or isinstance(node, ast.ImportFrom) and node.module == "pathlib")]
    for parent in [module] + [n for n in module.body if isinstance(n, ast.ClassDef) and n.name == "Broker"]:
        kept = []
        for node in parent.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in MEMORY_FUNCTIONS:
                changed[node.name] = node
            else:
                kept.append(node)
        parent.body = kept
    return dump(module), changed


def test_only_five_memory_functions_change_after_exact_guard_parent(current_source, joined, tmp_path):
    guard = tmp_path / "guard"
    compose.compose(current_source, guard, profile_name="current116-maintenance-guard")
    actual = (guard / "ext/lease_broker.py").read_bytes()
    assert sha(actual) == "4072c76fd5d28729e4c62d44f9b700a2ac503ccb4acd1e572fc4a6c291fe23d3"
    before, old = broker_projection(actual)
    after, new = broker_projection((joined / "ext/lease_broker.py").read_bytes())
    assert before == after  # Includes both guards, all native schema/triggers, main and application methods.
    assert set(old) == set(new) == MEMORY_FUNCTIONS
    assert all(dump(old[k]) != dump(new[k]) for k in MEMORY_FUNCTIONS)
    assert sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in ast.walk(ast.parse(actual))) == 131


def task_inverse(raw):
    module = ast.parse(raw)
    wrapper = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == "inspect_run")
    assert len(wrapper.body) == 3
    assert isinstance(wrapper.body[0], ast.ImportFrom) and wrapper.body[0].module == "fabric_memory_view"
    assert dump(wrapper.body[1].value.func) == "Name(id='require_generic_channel', ctx=Load())"
    assert isinstance(wrapper.body[2], ast.Return) and wrapper.body[2].value.func.id == "_inspect_run"
    module.body.remove(wrapper)
    inner = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == "_inspect_run")
    inner.name = "inspect_run"
    for name, count in (("read_result", 2), ("main", 3)):
        node = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == name)
        index = next(i for i, n in enumerate(node.body) if isinstance(n, ast.ImportFrom) and n.module == "fabric_memory_view")
        del node.body[index:index+count]
    return dump(module)


def test_current_task_all_other_semantics_ast_exact(current_source, joined):
    original = (current_source / "ext/fabric_task.py").read_bytes()
    assert sha(original) == "5c46ef84cd3c97d74d296f5c12369a178e5f0641a7b9f80a002ebae6b8767b28"
    assert task_inverse((joined / "ext/fabric_task.py").read_bytes()) == dump(ast.parse(original))


def load(path, name, monkeypatch):
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("channel", ["inspect", "result", "cli"])
def test_actual_current_task_privacy_guard_runs_before_original_channel(joined, monkeypatch, channel):
    task = load(joined / "ext/fabric_task.py", "preserving118_task", monkeypatch)
    import fabric_memory_view
    # Actual closed privacy classifier, real inert packet; no injected authority.
    here = joined.parent / ("private-" + channel)
    state = here / "state/remote_sub"
    state.mkdir(parents=True)
    (state / "inert-private-run.request.packet").write_bytes(fabric_memory_view.PACKET_PREFIX + b'"inert":true}')
    monkeypatch.setattr(task, "HERE", here)
    def forbidden(*args, **kwargs):
        raise AssertionError("original channel must not run")
    monkeypatch.setattr(task, "_inspect_run", forbidden)
    monkeypatch.setattr(task, "_result_snapshot", forbidden)
    if channel == "cli":
        assert task.main(["status", "inert-private-run"]) == 75
    else:
        with pytest.raises(ValueError, match="participant_view_required"):
            (task.inspect_run if channel == "inspect" else task.read_result)("inert-private-run")
    assert not (here / "broker").exists()


def test_actual_current_task_ordinary_inspection_still_uses_owned_reader(joined, monkeypatch):
    task = load(joined / "ext/fabric_task.py", "preserving118_task", monkeypatch)
    import fabric_memory_view
    monkeypatch.setattr(fabric_memory_view, "require_generic_channel", lambda *a: None)
    sentinel = object()
    monkeypatch.setattr(task, "_inspect_run", lambda rid, **kw: sentinel)
    assert task.inspect_run("inert-ordinary") is sentinel


def test_real_joined_broker_existing_only_reopens_without_creation_or_schema_change(joined, tmp_path, monkeypatch):
    module = load(joined / "ext/lease_broker.py", "preserving118_broker", monkeypatch)
    database, lock = tmp_path / "leases.sqlite", tmp_path / "leases.lock"
    with sqlite3.connect(database) as con:
        con.execute("CREATE TABLE inert_marker(value TEXT)")
        con.execute("INSERT INTO inert_marker VALUES ('preserve')")
    database.chmod(0o600); lock.touch(mode=0o600)
    before = database.read_bytes()
    def forbidden(self):
        raise AssertionError("existing-only must not initialize/migrate schema")
    monkeypatch.setattr(module.Broker, "_init_db", forbidden)
    broker = module.Broker(db_path=str(database), lock_path=str(lock), existing_only=True,
                           host_state_dir="inert-state", host_validator_path="inert-validator", this_host="inert-host")
    with broker._conn() as con:
        assert con.execute("SELECT value FROM inert_marker").fetchone()[0] == "preserve"
    fh = broker._lock(); fh.close()
    assert database.read_bytes() == before
    assert broker.host_state_dir == "inert-state" and broker.host_validator_path == "inert-validator"
    missing = tmp_path / "missing"
    with pytest.raises(FileNotFoundError):
        module.Broker(db_path=str(missing / "db"), lock_path=str(missing / "lock"), existing_only=True, this_host="inert-host")
    assert not missing.exists()
    with pytest.raises(sqlite3.OperationalError):
        module._connect(str(tmp_path / "never-created"), existing_only=True)
    assert not (tmp_path / "never-created").exists()


@pytest.mark.parametrize("defect", ["symlink", "writable", "nonboolean"])
def test_joined_existing_store_refuses_unqualified_custody(joined, tmp_path, monkeypatch, defect):
    module = load(joined / "ext/lease_broker.py", "preserving118_broker", monkeypatch)
    db, lock = tmp_path / "db", tmp_path / "lock"
    db.touch(mode=0o600); lock.touch(mode=0o600)
    if defect == "symlink":
        real = tmp_path / "real"; db.rename(real); db.symlink_to(real)
    elif defect == "writable":
        lock.chmod(0o666)
    with pytest.raises(ValueError):
        module.Broker(db_path=str(db), lock_path=str(lock), existing_only=1 if defect == "nonboolean" else True, this_host="inert-host")


@pytest.mark.parametrize("defect", ["foreign_generation", "missing_member", "injected_member", "wrong_preimage"])
def test118_exact_source_preconditions_fail_closed(memory_parent, tmp_path, defect):
    base = tmp_path / "base"; shutil.copytree(memory_parent, base)
    descriptor = base / "RELEASE.json"; value = json.loads(descriptor.read_text())
    if defect == "foreign_generation": value["digest"] = "0" * 64
    elif defect == "missing_member": value["files"].pop("ext/native_plan_worker.py")
    elif defect == "injected_member": value["files"]["ext/foreign.py"] = "1" * 64
    else: (base / "ext/fabric_task.py").write_bytes(b"foreign")
    descriptor.write_text(json.dumps(value))
    output = tmp_path / "output"
    with pytest.raises(ValueError): compose.compose(base, output, profile_name=PROFILE)
    assert not output.exists()


def test_changed_profile_helper_source_refuses_before_any_output(memory_parent, tmp_path, monkeypatch):
    profile = json.loads((compose.HERE / "memory118/profile.json").read_text())
    repo = tmp_path / "public-source"
    for source in profile["source_map"].values():
        path = repo / source; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / source).read_bytes())
    helper = repo / profile["source_map"]["ext/fabric_memory_view.py"]
    helper.write_bytes(helper.read_bytes() + b"\n# unreviewed delta\n")
    monkeypatch.setattr(compose, "REPO", repo)
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="canonical dependency changed"):
        compose.compose(memory_parent, output, profile_name=PROFILE)
    assert not output.exists()


def test_profile_privacy_delta_preserves_all_native_participant_and_pair_helpers():
    canonical = ast.parse((ROOT / "ops/native_fabric/provider_plans/memory118/native_owner/fabric_memory_view.py").read_bytes())
    variant = ast.parse((compose.HERE / "memory118/fabric_memory_view.py").read_bytes())
    old = {n.name: dump(n) for n in canonical.body if isinstance(n, ast.FunctionDef)}
    new = {n.name: dump(n) for n in variant.body if isinstance(n, ast.FunctionDef)}
    assert set(new) - set(old) == {"_current_authorization_row"}
    assert {n for n in old if old[n] != new[n]} == {"require_generic_channel"}
    assert sha((ROOT / "ops/native_fabric/provider_plans/memory118/native_owner/fabric_memory_view.py").read_bytes()) == "a7bfc2567c8abc6c27e3fe2277d8b21669420d90e547aafc42e1186ea0740081"


def test_fixed_control_owner_uses_the_same_full_broker_and_task_as_profile(joined):
    # This exact join prevents a preserving runtime patch paired with a stale helper.
    namespace=compose.HERE/'memory118/native_owner'
    for name in ('lease_broker.py','fabric_task.py'):
        assert (namespace/name).read_bytes()==(joined/'ext'/name).read_bytes()
    profile=json.loads((compose.HERE/'memory118/profile.json').read_text())
    assert profile['base_selection']['sequence']==40
    assert profile['base_selection']['generation']=='ef30408e91cd2d29df5b7f92fa0ad0873e06ed91a8d9ce3fbc90050b4752c879'
    for name in ('experiential_bridge.py','experiential_host_context.py','experiential_plan_policy.py',
                 'experiential_transport.py','native_plan_worker.py','pick.py'):
        assert profile['files']['ext/'+name]==profile['base_files']['ext/'+name]


@pytest.mark.parametrize('relabel',[False,True])
def test_stale39_cannot_become_the_expected40_source(current_source,tmp_path,relabel):
    base=tmp_path/'stale39';shutil.copytree(current_source,base)
    if relabel:
        value=json.loads((base/'RELEASE.json').read_text())
        value['digest']='ef30408e91cd2d29df5b7f92fa0ad0873e06ed91a8d9ce3fbc90050b4752c879'
        (base/'RELEASE.json').write_text(json.dumps(value))
    output=tmp_path/'must-not-exist'
    with pytest.raises(ValueError,match='selected native base changed'):
        compose.compose(base,output,profile_name=PROFILE)
    assert not output.exists()
