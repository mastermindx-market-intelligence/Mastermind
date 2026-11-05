"""Pinned official initialize grammar, using a private fake App Server only."""
import dataclasses
from contextlib import contextmanager

import pytest

from control_plane.executive_runtime import StateConflict, _normalise_constraints

from control_plane import codex_operator_adapter as adapter_module
from tests.test_codex_operator_adapter import _make_harness, _start


PIN = "16593cc2f422d5f398a8e40f550ebbaf1245392528957be342c295920a300704"
SEMANTIC_VERSION = "0.159.2"
# Synthetic values formatted by official ff6aec get_codex_user_agent grammar;
# this is source qualification, never a captured native response.
OFFICIAL_UA = (
    "mastermind-ohf/0.159.2 (Mac OS 26.1; arm64) "
    "Apple_Terminal/455 (mastermind-ohf; p1b)"
)


@contextmanager
def _evidence_fixture(tmp_path, prompt):
    harness = _make_harness(tmp_path.resolve(), turn_input=prompt)
    try:
        _, _, launch = _start(harness)
        yield harness, launch
    finally:
        for state in harness.adapter._generations.values():
            state.client.close()


def test_real_initializer_normalizes_official_producer_position(tmp_path, monkeypatch):
    with _evidence_fixture(tmp_path, "source-only version qualification") as (harness, _):
        state = next(iter(harness.adapter._generations.values()))
        original = state.client.request
        def request(method, params=None, **kwargs):
            if method == "initialize":
                return {"userAgent": OFFICIAL_UA}
            return original(method, params, **kwargs)
        monkeypatch.setattr(state.client, "request", request)
        requested = dataclasses.replace(harness.requested,
            harness_version=SEMANTIC_VERSION, harness_binary_digest=PIN)
        observed = harness.adapter._initialize_and_attest(state.client, requested, PIN)
        assert observed.harness_version == SEMANTIC_VERSION
        assert observed.harness_binary_digest == PIN



def test_semantic_pin_is_legal_in_existing_runtime_grammar():
    assert _normalise_constraints({"harness_binary_digest": PIN,
        "harness_version": SEMANTIC_VERSION})["harness_version"] == SEMANTIC_VERSION
    with pytest.raises(StateConflict):
        _normalise_constraints({"harness_binary_digest": PIN,
                               "harness_version": "codex-cli 0.159.2"})


def test_raw_observation_and_semantic_identity_stay_distinct():
    value = adapter_module._initialize_version_observation(
        OFFICIAL_UA, PIN, client_context=("mastermind-ohf", "p1b"))
    assert value.raw_user_agent == OFFICIAL_UA
    assert value.harness_version == SEMANTIC_VERSION
    assert OFFICIAL_UA not in repr(value)


@pytest.mark.parametrize("raw", [
    None, 1592, {}, b"mastermind-ohf/0.159.2", "", "0.159.2", "codex-cli 0.159.2",
    "foreign/0.159.2 (Mac OS 26.1; arm64) terminal (mastermind-ohf; p1b)",
    "mastermind-ohf/0.163.0 (0.159.2; arm64) terminal (mastermind-ohf; p1b)",
    "mastermind-ohf/0.163.0 (Mac OS; arm64) terminal (mastermind-ohf; 0.159.2)",
    "mastermind-ohf/0.159.2 (Mac OS; arm64) terminal (foreign; p1b)",
    "mastermind-ohf/0.159.2 (Mac OS; arm64) terminal (mastermind-ohf; p2)",
    "mastermind-ohf/0.159.2 Mac OS; arm64 terminal (mastermind-ohf; p1b)",
    OFFICIAL_UA + " injected", " " + OFFICIAL_UA, OFFICIAL_UA + "\n",
    OFFICIAL_UA.replace("Mac OS", "Mac\x00OS"),
    OFFICIAL_UA.replace("Mac OS", "Mac中文OS"),
    OFFICIAL_UA.replace("Apple_Terminal/455", "x" * 513),
])
def test_pinned_binary_refuses_nonproducer_or_foreign_identity(raw):
    with pytest.raises(adapter_module.CodexAdapterError):
        adapter_module._initialize_version_observation(
            raw, PIN, client_context=("mastermind-ohf", "p1b"))


def test_version_elsewhere_has_no_authority_and_known_context_is_required():
    for context in [("foreign", "p1b"), ("mastermind-ohf", "p2")]:
        with pytest.raises(adapter_module.CodexAdapterError):
            adapter_module._initialize_version_observation(OFFICIAL_UA, PIN,
                                                           client_context=context)
    # Non-authoritative terminal/platform values cannot change the first build.
    raw = OFFICIAL_UA.replace("Apple_Terminal/455", "Terminal/0.163.0")
    assert adapter_module._initialize_version_observation(raw, PIN,
        client_context=("mastermind-ohf", "p1b")).harness_version == SEMANTIC_VERSION


def test_unknown_binary_preserves_existing_raw_comparison():
    raw = "  legacy-user-agent/0.147  "
    value = adapter_module._initialize_version_observation(raw, "f" * 64,
        client_context=("legacy", "old"))
    assert value.harness_version == "legacy-user-agent/0.147"
    value = adapter_module._initialize_version_observation(OFFICIAL_UA, "f" * 64,
        client_context=("mastermind-ohf", "p1b"))
    assert value.harness_version == OFFICIAL_UA
    assert value.harness_version != SEMANTIC_VERSION


@pytest.mark.parametrize("initial,later,allowed", [
    (OFFICIAL_UA, OFFICIAL_UA.replace("/0.159.2", "/0.163.0", 1), True),
    (OFFICIAL_UA.replace("/0.159.2", "/0.163.0", 1), OFFICIAL_UA, False),
])
def test_initializer_freezes_response_before_later_rpc_mutation(
        tmp_path, monkeypatch, initial, later, allowed):
    with _evidence_fixture(tmp_path, "source-only drift qualification") as (harness, _):
        state = next(iter(harness.adapter._generations.values()))
        original = state.client.request
        response = {"userAgent": initial}
        def request(method, params=None, **kwargs):
            if method == "initialize":
                return response
            if method == "config/read":
                response["userAgent"] = later
            return original(method, params, **kwargs)
        monkeypatch.setattr(state.client, "request", request)
        requested = dataclasses.replace(harness.requested,
            harness_version=SEMANTIC_VERSION, harness_binary_digest=PIN)
        if allowed:
            observed = harness.adapter._initialize_and_attest(state.client, requested, PIN)
            assert observed.harness_version == SEMANTIC_VERSION
        else:
            with pytest.raises(adapter_module.CodexAdapterError):
                harness.adapter._initialize_and_attest(state.client, requested, PIN)
        assert response["userAgent"] == later


def test_initializer_refuses_sealed_version_drift(tmp_path, monkeypatch):
    with _evidence_fixture(tmp_path, "source-only sealed-version qualification") as (harness, _):
        state = next(iter(harness.adapter._generations.values()))
        original = state.client.request
        def request(method, params=None, **kwargs):
            return {"userAgent": OFFICIAL_UA} if method == "initialize" else original(method, params, **kwargs)
        monkeypatch.setattr(state.client, "request", request)
        requested = dataclasses.replace(harness.requested,
            harness_version="0.163.0", harness_binary_digest=PIN)
        with pytest.raises(adapter_module.CodexAdapterError, match="sealed version"):
            harness.adapter._initialize_and_attest(state.client, requested, PIN)


@pytest.mark.parametrize("sealed_raw,allowed", [
    (OFFICIAL_UA, True),
    (OFFICIAL_UA.replace("Apple_Terminal/455", "Terminal/old"), False),
])
def test_existing_raw_bound_direct_probe_keeps_exact_equality(
        tmp_path, monkeypatch, sealed_raw, allowed):
    with _evidence_fixture(tmp_path, "source-only raw caller qualification") as (harness, _):
        state = next(iter(harness.adapter._generations.values()))
        original = state.client.request
        def request(method, params=None, **kwargs):
            return {"userAgent": OFFICIAL_UA} if method == "initialize" else original(method, params, **kwargs)
        monkeypatch.setattr(state.client, "request", request)
        requested = dataclasses.replace(harness.requested,
            harness_version=sealed_raw, harness_binary_digest=PIN)
        if allowed:
            observed = harness.adapter._initialize_and_attest(state.client, requested, PIN)
            assert observed.harness_version == sealed_raw
        else:
            with pytest.raises(adapter_module.CodexAdapterError, match="sealed version"):
                harness.adapter._initialize_and_attest(state.client, requested, PIN)
