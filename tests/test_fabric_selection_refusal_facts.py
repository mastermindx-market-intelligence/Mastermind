"""Same-invocation router diagnostics; all capacity/provider dependencies are inert."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "ops/native_fabric/quota_continuity"


@pytest.fixture
def route_modules(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(NATIVE / "source"))
    monkeypatch.syspath_prepend(str(NATIVE / "candidate"))
    def load(name, file):
        spec = importlib.util.spec_from_file_location(name, NATIVE / "candidate" / file)
        mod = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, mod)
        spec.loader.exec_module(mod)
        return mod
    pick = load("pick", "pick.py")
    task = load("selection_task_under_test", "fabric_task.py")
    monkeypatch.setattr(task, "HERE", tmp_path / "owner")
    doc = {"routing": {"judgment_order": ["glm-5.3"], "reviewer_not_author": True},
           "pools": {"glm": {"models": {"reviewer": "glm-5.3", "operator": "glm-5.3"}}}}
    policy = tmp_path / "policy.yaml"
    policy.write_text(json.dumps(doc))
    monkeypatch.setattr(pick, "POOLS_YAML", str(policy))
    pick.reset_pools_cache()
    monkeypatch.setattr(pick, "_promo_balance_glm", lambda order, *a, **k: order)
    monkeypatch.setattr(pick, "_promote_urgent", lambda order, *a, **k: order)
    monkeypatch.setattr(pick, "_grok_priority_active", lambda *a, **k: False)
    monkeypatch.setattr(pick, "burn_down_urgent", lambda *a, **k: False)
    routes = pick._HostRoutes({"glm": ("ubuntu3", "glm")})
    calls = []
    def hosts(*a, **k):
        calls.append("hosts")
        return routes
    monkeypatch.setattr(pick, "_eligible_host_routes", hosts)
    monkeypatch.setattr(pick, "_selection_model", lambda *a, **k: ("glm-5.3", ""))
    for attr, label in [("policy_allows", "policy"), ("_needs_ok", "needs"),
                        ("_subject_ok", "subject"), ("hard_filter", "hard_filter")]:
        def gate(*a, _label=label, **k):
            calls.append(_label)
            return True, "ok"
        monkeypatch.setattr(pick, attr, gate)
    def meter():
        calls.append("meter")
        return "NORMAL"
    monkeypatch.setattr(pick, "_glm_meter_state", meter)
    monkeypatch.setattr(pick, "next_escalate", lambda *a, **k: None)
    monkeypatch.setattr(pick, "launch_policy", lambda *a, **k: {"allowed": True})
    launch = Mock(return_value=type("Completed", (), {"returncode": 0})())
    monkeypatch.setattr(task.subprocess, "run", launch)
    return task, pick, calls, policy, launch


def request(task, rid="future-review"):
    return task.request(rid, "review", cwd="~/lanes/repos/macro", packet=None,
        stdin_bytes=b"PRIVATE_PROMPT https://user:SECRET@invalid/?key=SECRET",
        root_id="original-root", parent_run_id="actual-parent",
        task_complexity="C2_COMPLEX_BOUNDED", subject_pool="openai",
        new_macro_worktree="b" * 40, cpu_scope_percent=200)


def receipt(task, rid="future-review"):
    return json.loads((task.HERE / "state/remote_sub" / (rid + ".request-refused.json")).read_bytes())


@pytest.mark.parametrize("stage,reason,expected", [
    ("policy", "role does not allow SECRET", "policy_refused"),
    ("needs", "SECRET https://u:p@host", "capability_refused"),
    ("subject", "SECRET", "independence_refused"),
    ("hard_filter", "provider quota cooldown", "quota_cooldown"),
    ("hard_filter", "glm model at broker cap (SECRET)", "model_cap"),
    ("hard_filter", "provider quota state unavailable", "quota_state_unavailable"),
    ("hard_filter", "SECRET ENV_TOKEN=https://u:p@host", "hard_filter_refused"),
])
def test_adapter_retains_distinct_same_evaluation_causes(route_modules, monkeypatch, stage, reason, expected):
    task, pick, calls, policy, launch = route_modules
    attr = {"policy": "policy_allows", "needs": "_needs_ok", "subject": "_subject_ok", "hard_filter": "hard_filter"}[stage]
    def fail(*a, **k):
        calls.append(stage)
        return False, reason
    monkeypatch.setattr(pick, attr, fail)
    with pytest.raises(task.FabricTaskError, match="^NONE reason=no_operator_available$"):
        request(task)
    row = receipt(task)
    assert row["refusal_code"] == "NO_OPERATOR_AVAILABLE"
    facts = row["selection_diagnostics"]
    assert facts["schema"] == "mastermind.fabric_selection_diagnostics.v1"
    assert facts["coverage"] == "judgment_rejection_branches"
    assert facts["request_sha256"] == row["request_sha256"]
    assert facts["policy_sha256"] == hashlib.sha256(policy.read_bytes()).hexdigest()
    assert facts["sources"]["pick.py"] == hashlib.sha256((NATIVE / "candidate/pick.py").read_bytes()).hexdigest()
    assert facts["sources"]["fabric_task.py"] == hashlib.sha256((NATIVE / "candidate/fabric_task.py").read_bytes()).hexdigest()
    assert facts["decisions"][-1]["reason"] == expected
    assert facts["decisions"][-1]["pool"] == "glm"
    assert facts["decisions"][-1]["host"] == "ubuntu3"
    assert facts["decisions"][-1]["mode"] == "glm"
    assert facts["decisions"][-1]["stage"] == stage
    assert calls == ["hosts"] + ["policy", "needs", "subject", "hard_filter"][:["policy", "needs", "subject", "hard_filter"].index(stage) + 1]
    assert not launch.called
    assert "SECRET" not in json.dumps(facts) and "PRIVATE_PROMPT" not in json.dumps(facts)
    assert set(p.name for p in (task.HERE / "state/remote_sub").iterdir()) == {"future-review.request.packet", "future-review.request.json", "future-review.request-refused.json"}


def test_positive_keeps_route_launch_and_no_diagnostic_artifact(route_modules):
    task, pick, calls, policy, launch = route_modules
    assert request(task) == 0
    assert calls == ["hosts", "policy", "needs", "subject", "hard_filter", "meter"]
    assert launch.call_count == 1
    argv = launch.call_args.args[0]
    assert argv[2:4] == ["ubuntu3", "glm"]
    assert "--cpu-scope-quota" in argv
    assert not (task.HERE / "state/remote_sub/future-review.request-refused.json").exists()


@pytest.mark.parametrize("mode", ["meter", "emission", "host_mode"])
def test_other_refusal_stages_keep_original_output(route_modules, monkeypatch, mode):
    task, pick, calls, policy, launch = route_modules
    if mode == "meter":
        monkeypatch.setattr(pick, "_glm_meter_state", lambda: "PARKED")
        expected = "meter_parked"
    elif mode == "emission":
        monkeypatch.setattr(pick, "launch_policy", lambda *a, **k: {"allowed": False, "reason": "SECRET https://u:p@host"})
        expected = "economic_refused"
    else:
        monkeypatch.setattr(pick, "_eligible_host_routes", lambda *a, **k: pick._HostRoutes({"minimax": ("ubuntu3", "minimax")}))
        expected = "host_mode_absent"
    with pytest.raises(task.FabricTaskError, match="^NONE reason=no_operator_available$"):
        request(task)
    facts = receipt(task)["selection_diagnostics"]
    assert facts["decisions"][-1]["reason"] == expected
    assert "SECRET" not in json.dumps(facts)
    assert not launch.called


@pytest.mark.parametrize("change", ["request", "key", "line", "mutation", "policy", "source", "replay", "unbound"])
def test_observation_rejects_wrong_or_mutated_binding(route_modules, monkeypatch, change, tmp_path):
    task, pick, calls, policy, launch = route_modules
    monkeypatch.setattr(pick, "policy_allows", lambda *a, **k: (False, "secret"))
    key = object()
    line, facts = pick.observed_format_pick("review", observation_key=key,
        request_sha256="a" * 64, host="auto", subject_pool="openai")
    request_sha = "a" * 64
    if change == "request": request_sha = "b" * 64
    if change == "key": key = object()
    if change == "line": line += " changed"
    if change == "mutation": object.__setattr__(facts, "raw", facts.raw.replace(b"policy_refused", b"secret_refused"))
    if change == "policy": policy.write_text("changed")
    if change == "source": monkeypatch.setattr(pick, "_selection_source_hashes", lambda: {"pick.py": "b" * 64, "fabric_task.py": "c" * 64})
    if change == "unbound": facts = {"schema": "mastermind.fabric_selection_diagnostics.v1"}
    if change == "replay":
        assert pick.consume_selection_refusal(facts, key, request_sha, line)
    assert pick.consume_selection_refusal(facts, key, request_sha, line) is None


def test_optional_capture_failure_keeps_original_refusal(route_modules, monkeypatch):
    task, pick, calls, policy, launch = route_modules
    monkeypatch.setattr(pick, "_selection_source_hashes", lambda: (_ for _ in ()).throw(OSError("SECRET")))
    monkeypatch.setattr(pick, "policy_allows", lambda *a, **k: (False, "SECRET"))
    with pytest.raises(task.FabricTaskError, match="^NONE reason=no_operator_available$"):
        request(task)
    assert "selection_diagnostics" not in receipt(task)
    assert not launch.called


@pytest.mark.parametrize('outcome', ['policy', 'subject', 'cap', 'meter', 'economic', 'positive'])
def test_observer_preserves_all_selection_predicate_counts_and_order(route_modules, monkeypatch, outcome):
    task, pick, calls, policy, launch = route_modules
    if outcome == 'policy': monkeypatch.setattr(pick, 'policy_allows', lambda *a, **k: (False, 'unmapped'))
    if outcome == 'subject': monkeypatch.setattr(pick, '_subject_ok', lambda *a, **k: (False, 'unmapped'))
    if outcome == 'cap': monkeypatch.setattr(pick, 'hard_filter', lambda *a, **k: (False, 'glm model at broker cap (glm-5.3)'))
    if outcome == 'meter': monkeypatch.setattr(pick, '_glm_meter_state', lambda: 'SPILL')
    if outcome == 'economic': monkeypatch.setattr(pick, 'launch_policy', lambda *a, **k: {'allowed': False, 'reason': 'unmapped'})
    trace = []
    for name in ['load_pools', '_selection_model', '_eligible_host_routes', '_promo_balance_glm',
                 '_promote_urgent', '_grok_priority_active', 'policy_allows', '_needs_ok',
                 '_subject_ok', 'hard_filter', '_glm_meter_state', 'burn_down_urgent', '_emit', 'launch_policy']:
        original = getattr(pick, name)
        def watched(*a, _name=name, _fn=original, **k):
            trace.append(_name)
            return _fn(*a, **k)
        monkeypatch.setattr(pick, name, watched)
    options = dict(host='auto', subject_pool='openai', task_complexity='C2_COMPLEX_BOUNDED',
        required_modes=['glm', 'glm-codex', 'minimax', 'qwen'], required_platforms=['linux'])
    baseline = pick.format_pick('review', **options)
    expected_trace = list(trace)
    trace.clear()
    actual, _ = pick.observed_format_pick('review', observation_key=object(), request_sha256='a'*64, **options)
    assert actual == baseline
    assert trace == expected_trace


def test_cached_policy_change_is_not_relabelled_as_evaluated_policy(route_modules, monkeypatch):
    task, pick, calls, policy, launch = route_modules
    evaluated = pick.load_pools()
    policy.write_text('{"routing":{"judgment_order":["grok"]}}')
    monkeypatch.setattr(pick, 'policy_allows', lambda *a, **k: (False, 'unmapped'))
    with pytest.raises(task.FabricTaskError, match='^NONE reason=no_operator_available$'):
        request(task)
    assert pick.load_pools() is evaluated
    assert 'selection_diagnostics' not in receipt(task)
    assert not launch.called


def test_parsed_policy_mutation_during_same_selection_omits_facts(route_modules, monkeypatch):
    task, pick, calls, policy, launch = route_modules
    def mutate(pool, tc, doc):
        doc['SECRET_ENV'] = 'https://user:password@invalid'
        return False, 'unmapped'
    monkeypatch.setattr(pick, 'policy_allows', mutate)
    with pytest.raises(task.FabricTaskError, match='^NONE reason=no_operator_available$'):
        request(task)
    assert 'selection_diagnostics' not in receipt(task)


def test_request_mutation_does_not_accept_old_observation(route_modules, monkeypatch):
    task, pick, calls, policy, launch = route_modules
    monkeypatch.setattr(pick, 'policy_allows', lambda *a, **k: (False, 'unmapped'))
    parse = task._parse_route
    def mutate_request(line):
        path = task.HERE / 'state/remote_sub/future-review.request.json'
        value = json.loads(path.read_bytes()); value['cwd'] = 'changed'
        path.write_text(json.dumps(value))
        return parse(line)
    monkeypatch.setattr(task, '_parse_route', mutate_request)
    with pytest.raises(task.FabricTaskError, match='^NONE reason=no_operator_available$'):
        request(task)
    assert 'selection_diagnostics' not in receipt(task)


def test_later_cpu_guard_failure_never_uses_successful_selection_as_refusal(route_modules, monkeypatch):
    task, pick, calls, policy, launch = route_modules
    monkeypatch.setattr(pick, '_eligible_host_routes', lambda *a, **k: pick._HostRoutes({'glm': ('ubuntu1', 'glm')}))
    with pytest.raises(task.FabricTaskError, match='^CPU_SCOPE_HOST_NOT_QUALIFIED$'):
        request(task)
    assert 'selection_diagnostics' not in receipt(task)
    assert not launch.called


def test_broken_optional_consumer_does_not_mask_existing_refusal_receipt(route_modules, monkeypatch):
    task, pick, calls, policy, launch = route_modules
    monkeypatch.setattr(pick, 'policy_allows', lambda *a, **k: (False, 'unmapped'))
    monkeypatch.setattr(pick, 'consume_selection_refusal', lambda *a: (_ for _ in ()).throw(RuntimeError('SECRET')))
    with pytest.raises(task.FabricTaskError, match='^NONE reason=no_operator_available$'):
        request(task)
    assert receipt(task)['launch_attempted'] is False
    assert 'selection_diagnostics' not in receipt(task)


@pytest.mark.parametrize('tamper', ['unknown_key', 'unknown_reason', 'unknown_host', 'unknown_model'])
def test_closed_schema_rejects_tampering_even_if_serialization_seal_is_recomputed(route_modules, monkeypatch, tamper):
    task, pick, calls, policy, launch = route_modules
    monkeypatch.setattr(pick, 'policy_allows', lambda *a, **k: (False, 'unmapped'))
    key = object()
    line, facts = pick.observed_format_pick('review', observation_key=key, request_sha256='a'*64, host='auto')
    value = json.loads(facts.raw)
    if tamper == 'unknown_key': value['raw_error'] = 'SECRET'
    else: value['decisions'][0][tamper.removeprefix('unknown_')] = 'SECRET https://user:password@invalid'
    raw = json.dumps(value).encode()
    object.__setattr__(facts, 'raw', raw)
    object.__setattr__(facts, 'seal', hashlib.sha256(raw).hexdigest())
    assert pick.consume_selection_refusal(facts, key, 'a'*64, line) is None


def test_default_multi_candidate_judgment_order_preserves_rejection_rows(route_modules, monkeypatch):
    task, pick, calls, policy, launch = route_modules
    doc = json.loads(policy.read_bytes())
    doc['routing']['judgment_order'] = ['glm-5.3', 'grok', 'cursor', 'codex-native', 'claude-native', 'fable']
    policy.write_text(json.dumps(doc))
    monkeypatch.setattr(pick, 'policy_allows', lambda *a, **k: (False, 'unmapped'))
    monkeypatch.setattr(pick, '_cursor_grok_after_quota', lambda *a, **k: 'NONE reason=synthetic')
    with pytest.raises(task.FabricTaskError, match='^NONE reason=no_operator_available$'):
        request(task)
    facts = receipt(task)['selection_diagnostics']
    assert [(r['pool'], r['stage']) for r in facts['decisions']] == [
        ('glm', 'policy'), ('grok', 'host_mode'), ('cursor', 'host_mode'),
        ('codex-native', 'host_mode'), ('claude-native', 'host_mode'), ('fable', 'host_mode')]
    assert not facts['truncated'] and not launch.called


@pytest.mark.parametrize('replacement', ['fifo', 'symlink', 'changed_inode'])
def test_policy_recheck_rejects_nonregular_or_replaced_file_without_changing_outcome(route_modules, monkeypatch, replacement, tmp_path):
    import os
    task, pick, calls, policy, launch = route_modules
    pick.load_pools()  # Existing evaluated cache, without another parse later.
    original = pick._selection_regular_bytes
    if replacement == 'changed_inode':
        original_read = pick.os.read
        changed = False
        def replace_during_read(fd, limit):
            nonlocal changed
            raw = original_read(fd, limit)
            if not changed and raw.startswith(b'{"routing"'):
                changed = True
                sibling = policy.with_suffix('.replacement')
                sibling.write_bytes(policy.read_bytes())
                os.replace(sibling, policy)
            return raw
        monkeypatch.setattr(pick.os, 'read', replace_during_read)
    else:
        policy.unlink()
        if replacement == 'fifo': os.mkfifo(policy)
        else:
            target = tmp_path / 'private-target'
            target.write_text('SECRET')
            policy.symlink_to(target)
    monkeypatch.setattr(pick, 'policy_allows', lambda *a, **k: (False, 'unmapped'))
    with pytest.raises(task.FabricTaskError, match='^NONE reason=no_operator_available$'):
        request(task)
    assert 'selection_diagnostics' not in receipt(task)
    assert not launch.called


def test_optional_capture_failure_also_preserves_positive_request(route_modules, monkeypatch):
    task, pick, calls, policy, launch = route_modules
    monkeypatch.setattr(pick, '_selection_source_hashes', lambda: (_ for _ in ()).throw(OSError('SECRET')))
    assert request(task) == 0
    assert launch.call_count == 1
    assert not (task.HERE / 'state/remote_sub/future-review.request-refused.json').exists()


def test_rejection_rows_are_bounded_without_skipping_original_predicates(route_modules, monkeypatch):
    task, pick, calls, policy, launch = route_modules
    doc = json.loads(policy.read_bytes())
    doc['routing']['judgment_order'] = ['glm-5.3'] * 100
    policy.write_text(json.dumps(doc))
    def refuse(*a, **k):
        calls.append('policy')
        return False, 'unmapped'
    monkeypatch.setattr(pick, 'policy_allows', refuse)
    with pytest.raises(task.FabricTaskError, match='^NONE reason=no_operator_available$'):
        request(task)
    facts = receipt(task)['selection_diagnostics']
    assert len(facts['decisions']) == 64 and facts['truncated'] is True
    assert calls == ['hosts'] + ['policy'] * 100
    assert len(json.dumps(facts).encode()) < 16384
    assert not launch.called


def test_later_outer_model_binding_failure_cannot_relabel_prior_rejection_rows(route_modules, monkeypatch):
    task, pick, calls, policy, launch = route_modules
    doc = json.loads(policy.read_bytes())
    doc['routing']['judgment_order'] = ['cursor', 'glm-5.3']
    policy.write_text(json.dumps(doc))
    models = iter(['glm-5.3', 'glm-5.3', 'glm-5.3-flash'])
    monkeypatch.setattr(pick, '_selection_model', lambda *a, **k: (next(models), ''))
    with pytest.raises(task.FabricTaskError, match='^NONE reason=glm model changed after host account observation$'):
        request(task)
    assert 'selection_diagnostics' not in receipt(task)
    assert not launch.called
