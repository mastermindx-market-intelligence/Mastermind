"""Native Linux wire/reader vertical; no collector or runtime admission."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import pytest
from control_plane import executive_host_capacity as hc
from ops.executive_os import linux_capacity_facts as lf
import test_linux_capacity_facts as fx


def binding():
    return {
        "host_ref": "host-" + "1" * 64,
        "boot_ref": "boot-" + "2" * 64,
        "capacity_pool_ref": "capacity-pool-" + "3" * 64,
        "source_generation_sha256": "4" * 64,
        "execution_scope_sha256": "5" * 64,
        "namespace_sha256": "6" * 64,
        "ancestry_sha256": "7" * 64,
    }


def snapshot(**kw):
    args = dict(scope=fx.scope(), window=fx.window(), disk=fx.disk())
    args.update(kw)
    facts = lf.observe(fx.inputs(), **args)
    d = args["disk"]
    facts["pool_total_bytes"] = lf.measured(lambda: (lf.disk_usable_bytes(d), lf.product(d.blocks, d.frsize))[1])
    metrics = {name: {"value": metric.value, "null_reason": metric.null_reason.value if metric.null_reason else None} for name, metric in facts.items()}
    window = args["window"]
    span = window.monotonic_end_ms - window.monotonic_start_ms
    return hc.build_native_host_capacity_snapshot(metrics, binding=binding(), observed_at_ms=window.observed_at_ms, sample_window_ms=span, total_observation_window_ms=span)


def project(value, **kw):
    args = dict(expected_binding=binding(), now_ms=100100, max_age_ms=5000)
    args.update(kw)
    return hc.project_native_host_capacity(value, **args)


def test_real_fact_builder_to_closed_wire_to_read_projection():
    value = snapshot()
    assert value["schema"] == "mastermind.host_capacity_snapshot/v2"
    assert value["platform"] == "linux"
    assert value["observation_profile"] == "linux-native-observation/v1"
    assert value["telemetry_status"] == "COMPLETE"
    result = project(value)
    assert result["host_ref"] == binding()["host_ref"]
    assert result["metrics"]["effective_cpu_capacity_millicores"]["value"] == 1500
    assert result["metrics"]["effective_cpu_capacity_millicores"]["unit"] == "millicores_ceiling"
    assert result["metrics"]["effective_memory_headroom_estimate_bytes"]["value"] == fx.G
    assert result["metrics"]["cpu_some_total"]["unit"] == "microseconds"
    assert result["metrics"]["pswpin_pages_delta"]["unit"] == "pages_delta"
    assert result["can_place_work"] is False
    assert result["admission_state"] == "NOT_EVALUATED"
    assert "available_cpu" not in result


@pytest.mark.parametrize("field", ["darwin_vm_counters", "darwin_fseventsd", "host_cpu_full_pressure"])
def test_inapplicable_native_fields_never_become_zero(field):
    value = snapshot()
    assert value["metrics"][field] == {"value": None, "null_reason": "NOT_APPLICABLE"}
    value["metrics"][field] = {"value": 0, "null_reason": None}
    with pytest.raises(hc.HostCapacityContractError):
        hc.validate_native_host_capacity_snapshot(value)


@pytest.mark.parametrize("field", list(binding()))
def test_reader_requires_every_owner_binding_component(field):
    expected = binding()
    expected[field] = expected[field][:-1] + "f"
    with pytest.raises(hc.HostCapacityContractError, match="NATIVE_BINDING_MISMATCH"):
        project(snapshot(), expected_binding=expected)


@pytest.mark.parametrize("now,age", [(98999,5000), (104001,5000), (100100,1000), (True,5000), (100100,0)])
def test_future_stale_oldest_window_and_invalid_clock_refuse(now, age):
    with pytest.raises(hc.HostCapacityContractError):
        project(snapshot(), now_ms=now, max_age_ms=age)


def test_oldest_window_boundary_is_inclusive():
    assert project(snapshot(), now_ms=104000, max_age_ms=5000)["can_place_work"] is False


@pytest.mark.parametrize("bad", [True, -1, 1.25, "100", 1 << 63])
def test_native_integer_metrics_are_strict(bad):
    value = snapshot()
    value["metrics"]["disk_usable_bytes"]["value"] = bad
    with pytest.raises(hc.HostCapacityContractError):
        hc.validate_native_host_capacity_snapshot(value)


@pytest.mark.parametrize("mutation", ["extra_top", "missing_metric", "extra_metric", "caller_unit", "platform", "profile", "unknown_status", "wrong_status", "unknown_list", "not_applicable_required", "reason_on_value", "null_without_reason", "wrong_scope"])
def test_closed_schema_and_completeness_refuse_misrepresentation(mutation):
    value = snapshot()
    if mutation == "extra_top": value["ready"] = True
    elif mutation == "missing_metric": value["metrics"].pop("disk_usable_bytes")
    elif mutation == "extra_metric": value["metrics"]["provider_quota"] = {"value": 10, "null_reason": None}
    elif mutation == "caller_unit": value["metrics"]["disk_usable_bytes"]["unit"] = "MB"
    elif mutation == "platform": value["platform"] = "darwin"
    elif mutation == "profile": value["observation_profile"] = "all-hosts-ready"
    elif mutation == "unknown_status": value["telemetry_status"] = "READY"
    elif mutation == "wrong_status": value["telemetry_status"] = "PARTIAL"
    elif mutation == "unknown_list": value["unknown_fields"] = ["disk_usable_bytes"]
    elif mutation == "not_applicable_required": value["metrics"]["disk_usable_bytes"] = {"value": None, "null_reason": "NOT_APPLICABLE"}
    elif mutation == "reason_on_value": value["metrics"]["disk_usable_bytes"]["null_reason"] = "MISSING"
    elif mutation == "null_without_reason": value["metrics"]["disk_usable_bytes"] = {"value": None, "null_reason": None}
    elif mutation == "wrong_scope": value["scope"]["kind"] = "observer-self"
    with pytest.raises(hc.HostCapacityContractError):
        hc.validate_native_host_capacity_snapshot(value)


@pytest.mark.parametrize("field,bad", [("host_available_memory_estimate_bytes",65*fx.G), ("effective_memory_headroom_estimate_bytes",33*fx.G), ("effective_cpu_capacity_millicores",25000), ("host_swap_used_bytes",9*fx.G), ("disk_usable_bytes",100000000), ("cpu_some_avg10",100001), ("host_logical_cpu_count",0)])
def test_cross_metric_bounds_do_not_create_supply(field,bad):
    value = snapshot()
    value["metrics"][field]["value"] = bad
    with pytest.raises(hc.HostCapacityContractError):
        hc.validate_native_host_capacity_snapshot(value)


def test_partial_observation_is_visible_but_not_admission():
    s = fx.scope()
    s = replace(s, levels=(replace(s.levels[0], cpu_max=lf.Read(None)), s.levels[1]))
    value = snapshot(scope=s)
    assert value["unknown_fields"] == ["effective_cpu_capacity_millicores"]
    assert value["telemetry_status"] == "PARTIAL"
    result = project(value)
    assert result["metrics"]["effective_cpu_capacity_millicores"]["value"] is None
    assert result["can_place_work"] is False


def test_known_zero_capacity_stays_distinct_from_unknown():
    s = fx.scope()
    s = replace(s, levels=(replace(s.levels[0], memory_current=fx.read(str(9*fx.G)+'\n')), s.levels[1]))
    result = project(snapshot(scope=s))
    assert result["metrics"]["effective_memory_headroom_estimate_bytes"]["value"] == 0
    assert result["metrics"]["effective_memory_headroom_estimate_bytes"]["null_reason"] is None


def test_v1_refusal_and_canonical_native_digest_remain_separate():
    value = snapshot()
    with pytest.raises(hc.HostCapacityContractError):
        hc.validate_host_capacity_snapshot(value)
    encoded = hc.canonical_native_host_capacity_json(value)
    assert encoded.endswith(b'\n')
    assert json.loads(encoded) == value
    assert project(value)["snapshot_sha256"] == hashlib.sha256(encoded).hexdigest()
    copy = hc.validate_native_host_capacity_snapshot(value)
    value["metrics"]["disk_usable_bytes"]["value"] = 0
    assert copy["metrics"]["disk_usable_bytes"]["value"] != 0
