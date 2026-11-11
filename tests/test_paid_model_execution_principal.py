"""Tests for the closed pure-DATA paid model-only principal validators.

The tests exercise strict normalization, closed shapes, derived-field
cross-checks, detached outputs and inert behavior.  They import the new
module normally and run against the actual contract and placement sources.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import socket
import subprocess
import sys
import unittest
from collections.abc import Mapping
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _candidate in (_ROOT, os.path.join(_ROOT, "control_plane"), _HERE):
    if os.path.isdir(_candidate) and _candidate not in sys.path:
        sys.path.insert(0, _candidate)

try:
    from control_plane import paid_model_execution_contract as contract
    from control_plane import paid_model_execution_principal as module
except ImportError:  # flat layout fallback
    import paid_model_execution_contract as contract
    import paid_model_execution_principal as module


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


D_GRANT = _sha("effective-grant")
D_COMMISSION = _sha("commission")
D_PYTHON = _sha("python")
D_SOURCE = _sha("source-manifest")
D_PROMPT = _sha("prompt")
D_REQUEST = _sha("request-body")
D_SCHEMA = _sha("result-schema")
D_CAPSULE = _sha("capsule")
D_PHYSICAL = _sha("physical-binding")
D_PIN = _sha("pin-identity")
D_CAPTURE = _sha("capture-contract")
D_ISOLATION = _sha("control-input-isolation")
OTHER_DIGEST = _sha("other-digest")
POLICY_DIGEST = contract.digest(contract.POLICY)

_PLACEMENT_SCHEMA = "mastermind.executive_placement_snapshot/v1"
_LONG_TEXT = "x" * 513


def _binding(**changes):
    value = {
        "root_id": "root-job-1",
        "job_id": "root-job-1",
        "attempt_id": "attempt-11",
        "effective_grant_digest": D_GRANT,
        "commission_sha256": D_COMMISSION,
    }
    value.update(changes)
    return value


def _route(**changes):
    value = {
        "provider": "glm",
        "host_ref": "glm-host-7",
        "model": "glm-5.3",
        "parent_job_id": None,
    }
    value.update(changes)
    return value


def _process(**changes):
    value = {
        "pid": 4102,
        "pgid": 4102,
        "session_id": 950,
        "start_identity": "18446744009512345678",
        "boot_id": "b18d0f2a6c6f4e7d8a91c2b3d4e5f607",
        "observed_user": "paid-runner",
        "effective_uid": 1002,
        "effective_gid": 1002,
        "real_uid": 1002,
        "real_gid": 1002,
        "launch_nonce": "launch-nonce-7f3a",
    }
    value.update(changes)
    return value


def _controller(**changes):
    value = {
        "pid": 512,
        "start_identity": "9988776655443322",
        "boot_id": "b18d0f2a6c6f4e7d8a91c2b3d4e5f607",
    }
    value.update(changes)
    return value


def _lease(**changes):
    value = {
        "lease_id": "lease-0007",
        "orchestrator_id": "fabric-broker-1",
        "pool": "glm-frontier",
        "account": "glm-account-2",
        "host_ref": "glm-host-7",
        "model": "glm-5.3",
        "controller_process": _controller(),
        "runtime_fence_generation": 11,
        "runtime_pin_version": 3,
    }
    value.update(changes)
    return value


def _evidence(**changes):
    value = {
        "python_sha256": D_PYTHON,
        "source_manifest_sha256": D_SOURCE,
        "policy_sha256": POLICY_DIGEST,
        "prompt_sha256": D_PROMPT,
        "request_body_sha256": D_REQUEST,
        "result_schema_sha256": D_SCHEMA,
        "capsule_binding_sha256": D_CAPSULE,
        "physical_binding_sha256": D_PHYSICAL,
        "pin_identity_sha256": D_PIN,
        "capture_contract_sha256": D_CAPTURE,
        "control_input_isolation_manifest_sha256": D_ISOLATION,
    }
    value.update(changes)
    return value


def _attestation(**changes):
    value = {
        "schema_version": contract.ATTESTATION_SCHEMA,
        "profile_id": contract.PROFILE_ID,
        "adapter_id": contract.ADAPTER_ID,
        "execution_surface": contract.EXECUTION_SURFACE,
        "binding": _binding(),
        "paid_route": _route(),
        "worker_id": "worker-22",
        "quota_class": "glm-frontier",
        "process_identity": _process(),
        "lease_binding": _lease(),
        "evidence": _evidence(),
    }
    value.update(changes)
    return value


def _placement(**changes):
    value = {
        "schema_version": _PLACEMENT_SCHEMA,
        "worker_id": "worker-22",
        "quota_class": "glm-frontier",
        "provider": "glm",
        "account_label": "glm-account-2",
        "observed_at_ms": 1769000000000,
    }
    value.update(changes)
    return value


def _expectations(**changes):
    value = {
        "expected_binding": _binding(),
        "expected_route": _route(),
        "expected_worker_id": "worker-22",
        "expected_quota_class": "glm-frontier",
        "expected_process": _process(),
        "expected_lease_binding": _lease(),
        "expected_evidence": _evidence(),
    }
    value.update(changes)
    return value


def _validate_attestation(value, **overrides):
    """Structural-test wrapper; expectations here are synthetic test DATA only."""
    expected = _expectations()
    if type(value) is dict:
        for field, argument in (
            ("binding", "expected_binding"), ("paid_route", "expected_route"),
            ("worker_id", "expected_worker_id"), ("quota_class", "expected_quota_class"),
            ("process_identity", "expected_process"), ("lease_binding", "expected_lease_binding"),
            ("evidence", "expected_evidence"),
        ):
            if field in value:
                expected[argument] = value[field]
    expected.update(overrides)
    return module.validate_paid_model_attestation(value, **expected)


def _group(base_fixture, **changes):
    value = base_fixture()
    value.update(changes)
    return value


class _DictSubclass(dict):
    pass


class _CustomMapping(Mapping):
    def __init__(self, data):
        self._data = data

    def __getitem__(self, key):
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)


def _assert_plain_data(testcase, value):
    if value is None or type(value) in (str, int):
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                testcase.fail("non-string key in validated DATA")
            _assert_plain_data(testcase, item)
        return
    testcase.fail(f"non plain value of type {type(value).__name__}")


class PaidModelPrincipalTestCase(unittest.TestCase):
    def refuse(self, function, *args, **kwargs):
        with self.assertRaises(module.PaidModelPrincipalRefused):
            function(*args, **kwargs)

    def assert_plain(self, value):
        _assert_plain_data(self, value)
        json.dumps(value, allow_nan=False)


class AttestationConstantsTests(PaidModelPrincipalTestCase):
    def test_alias_constants(self):
        self.assertEqual(
            module.PRINCIPAL_SCHEMA, "mastermind.paid_model_execution_principal/v1"
        )
        self.assertEqual(module.PRINCIPAL_KIND, "PAID_MODEL_ONLY")


class AttestationValidTests(PaidModelPrincipalTestCase):
    def test_valid_with_exact_expectations_roundtrips(self):
        attestation = _attestation()
        result = _validate_attestation(attestation, **_expectations())
        self.assertEqual(result, attestation)
        self.assertIsNot(result, attestation)
        self.assert_plain(result)

    def test_public_api_requires_all_expectations(self):
        with self.assertRaises(TypeError):
            module.validate_paid_model_attestation(_attestation())
        for key in _expectations():
            expected = _expectations()
            del expected[key]
            with self.assertRaises(TypeError):
                module.validate_paid_model_attestation(_attestation(), **expected)
            expected[key] = None
            self.refuse(module.validate_paid_model_attestation, _attestation(), **expected)

    def test_valid_non_root_parent(self):
        attestation = _attestation(
            binding=_binding(root_id="root-job-1", job_id="job-2"),
            paid_route=_route(parent_job_id="root-job-1"),
        )
        result = _validate_attestation(attestation)
        self.assertEqual(result["paid_route"]["parent_job_id"], "root-job-1")

    def test_valid_observed_user_alternate_shape(self):
        result = _validate_attestation(
            _attestation(process_identity=_process(observed_user="_svc_runner"))
        )
        self.assertEqual(result["process_identity"]["observed_user"], "_svc_runner")

    def test_result_detached_from_input(self):
        attestation = _attestation()
        snapshot = copy.deepcopy(attestation)
        result = _validate_attestation(attestation)
        attestation["binding"]["job_id"] = "mutated-job"
        attestation["evidence"]["policy_sha256"] = OTHER_DIGEST
        attestation["lease_binding"]["controller_process"]["pid"] = 1
        self.assertEqual(result, snapshot)

    def test_input_detached_from_result(self):
        attestation = _attestation()
        snapshot = copy.deepcopy(attestation)
        result = _validate_attestation(attestation)
        result["binding"]["job_id"] = "mutated-job"
        result["lease_binding"]["controller_process"]["pid"] = 1
        self.assertEqual(attestation, snapshot)


class AttestationExpectationTests(PaidModelPrincipalTestCase):
    def test_binding_expectation_mismatch(self):
        self.refuse(
            _validate_attestation,
            _attestation(),
            **_expectations(expected_binding=_binding(commission_sha256=OTHER_DIGEST)),
        )

    def test_route_expectation_mismatch(self):
        self.refuse(
            _validate_attestation,
            _attestation(),
            **_expectations(expected_route=_route(model="glm-5.3-flash")),
        )

    def test_worker_expectation_mismatch(self):
        self.refuse(
            _validate_attestation,
            _attestation(),
            **_expectations(expected_worker_id="worker-23"),
        )

    def test_quota_expectation_mismatch(self):
        self.refuse(
            _validate_attestation,
            _attestation(),
            **_expectations(expected_quota_class="glm-batch"),
        )

    def test_process_expectation_mismatch(self):
        self.refuse(
            _validate_attestation,
            _attestation(),
            **_expectations(expected_process=_process(pid=4103)),
        )

    def test_lease_expectation_mismatch(self):
        self.refuse(
            _validate_attestation,
            _attestation(),
            **_expectations(expected_lease_binding=_lease(account="glm-account-9")),
        )

    def test_evidence_expectation_mismatch(self):
        self.refuse(
            _validate_attestation,
            _attestation(),
            **_expectations(expected_evidence=_evidence(prompt_sha256=OTHER_DIGEST)),
        )

    def test_evidence_expectation_subset_refused(self):
        for evidence in ({}, {"pin_identity_sha256": D_PIN}):
            self.refuse(module.validate_paid_model_attestation, _attestation(),
                        **_expectations(expected_evidence=evidence))

    def test_expected_binding_malformed_is_refused(self):
        self.refuse(
            _validate_attestation,
            _attestation(),
            **_expectations(expected_binding=_binding(attempt_id=True)),
        )

    def test_expected_worker_id_malformed_is_refused(self):
        self.refuse(
            _validate_attestation,
            _attestation(),
            **_expectations(expected_worker_id=" worker-22"),
        )

    def test_expected_process_malformed_is_refused(self):
        self.refuse(
            _validate_attestation,
            _attestation(),
            **_expectations(expected_process=_process(pid=True)),
        )

    def test_expected_lease_malformed_is_refused(self):
        self.refuse(
            _validate_attestation,
            _attestation(),
            **_expectations(expected_lease_binding=_lease(runtime_fence_generation=0)),
        )

    def test_expected_evidence_unknown_field_is_refused(self):
        self.refuse(
            _validate_attestation,
            _attestation(),
            **_expectations(expected_evidence={"home_sha256": OTHER_DIGEST}),
        )

    def test_policy_hash_wrong_even_when_expected_matches(self):
        attestation = _attestation(evidence=_evidence(policy_sha256=OTHER_DIGEST))
        self.refuse(
            _validate_attestation,
            attestation,
            **_expectations(expected_evidence=_evidence(policy_sha256=OTHER_DIGEST)),
        )


class AttestationHeaderTests(PaidModelPrincipalTestCase):
    def test_wrong_schema_version(self):
        self.refuse(
            _validate_attestation,
            _attestation(schema_version="mastermind.executive_paid_model_launch_attestation/v2"),
        )

    def test_old_v1_principal_schema_is_refused(self):
        self.refuse(
            _validate_attestation,
            _attestation(schema_version="mastermind.execution_principal_snapshot/v1"),
        )

    def test_wrong_profile(self):
        self.refuse(
            _validate_attestation,
            _attestation(profile_id="fabric.paid.glm.sealed-input.v2"),
        )

    def test_wrong_adapter(self):
        self.refuse(
            _validate_attestation,
            _attestation(adapter_id="canonical-paid-other"),
        )

    def test_wrong_surface(self):
        self.refuse(
            _validate_attestation,
            _attestation(execution_surface="glm-model-and-tools"),
        )

    def test_worker_and_quota_forms(self):
        self.refuse(_validate_attestation, _attestation(worker_id=""))
        self.refuse(_validate_attestation, _attestation(worker_id=True))
        self.refuse(_validate_attestation, _attestation(quota_class="bad class"))


class AttestationNestedShapeTests(PaidModelPrincipalTestCase):
    def test_top_level_unknown_missing_renamed(self):
        self.refuse(_validate_attestation, _attestation(verified=True))
        self.refuse(
            _validate_attestation, _attestation(provider_home_identity={})
        )
        self.refuse(
            _validate_attestation, _attestation(provider_session_id="s")
        )
        self.refuse(
            _validate_attestation, _attestation(secret_canary="c")
        )
        broken = _attestation()
        del broken["worker_id"]
        self.refuse(_validate_attestation, broken)
        renamed = _attestation()
        renamed["proofs"] = renamed.pop("evidence")
        self.refuse(_validate_attestation, renamed)

    def test_binding_group_keys(self):
        self.refuse(
            _validate_attestation,
            _attestation(binding=_group(_binding, extra=1)),
        )
        broken = _binding()
        del broken["root_id"]
        self.refuse(_validate_attestation, _attestation(binding=broken))
        self.refuse(
            _validate_attestation,
            _attestation(binding=_group(_binding, attempt=None)),
        )

    def test_route_group_keys(self):
        self.refuse(
            _validate_attestation,
            _attestation(paid_route=_group(_route, provider_session_id="s")),
        )
        broken = _route()
        del broken["model"]
        self.refuse(_validate_attestation, _attestation(paid_route=broken))
        self.refuse(
            _validate_attestation,
            _attestation(paid_route=_group(_route, host="glm-host-7")),
        )

    def test_process_group_keys(self):
        self.refuse(
            _validate_attestation,
            _attestation(process_identity=_group(_process, provider_session_id="s")),
        )
        self.refuse(
            _validate_attestation,
            _attestation(process_identity=_group(_process, provider_home_identity={})),
        )
        broken = _process()
        del broken["boot_id"]
        self.refuse(
            _validate_attestation, _attestation(process_identity=broken)
        )
        self.refuse(
            _validate_attestation,
            _attestation(process_identity=_group(_process, process_id=7)),
        )

    def test_lease_group_keys(self):
        self.refuse(
            _validate_attestation,
            _attestation(lease_binding=_group(_lease, lease_expiry_ms=1)),
        )
        self.refuse(
            _validate_attestation,
            _attestation(lease_binding=_group(_lease, start_grant="grant")),
        )
        broken = _lease()
        del broken["pool"]
        self.refuse(
            _validate_attestation, _attestation(lease_binding=broken)
        )
        self.refuse(
            _validate_attestation,
            _attestation(lease_binding=_group(_lease, id="lease-0007")),
        )

    def test_controller_group_keys(self):
        self.refuse(
            _validate_attestation,
            _attestation(
                lease_binding=_lease(controller_process=_group(_controller, session_id=5))
            ),
        )
        broken = _controller()
        del broken["boot_id"]
        self.refuse(
            _validate_attestation,
            _attestation(lease_binding=_lease(controller_process=broken)),
        )
        self.refuse(
            _validate_attestation,
            _attestation(
                lease_binding=_lease(controller_process=_group(_controller, controller_pid=5))
            ),
        )

    def test_evidence_group_keys(self):
        broken = _evidence()
        del broken["policy_sha256"]
        self.refuse(_validate_attestation, _attestation(evidence=broken))
        self.refuse(
            _validate_attestation,
            _attestation(evidence=_group(_evidence, python=D_PYTHON)),
        )
        self.refuse(
            _validate_attestation,
            _attestation(evidence=_group(_evidence, home_sha256=OTHER_DIGEST)),
        )

    def test_non_dict_inputs_are_refused(self):
        for value in (None, [], "attestation", 7, _DictSubclass(_attestation()),
                      _CustomMapping(_attestation())):
            self.refuse(_validate_attestation, value)


class AttestationNumericTests(PaidModelPrincipalTestCase):
    def test_pid_pgid_session_bounds(self):
        for change in (
            {"pid": True},
            {"pid": 0},
            {"pid": -4102},
            {"pid": 2 ** 63},
            {"pid": 4102.0},
            {"pid": float("nan")},
            {"pid": float("inf")},
            {"pgid": True},
            {"pgid": 0},
            {"session_id": True},
            {"session_id": 0},
        ):
            with self.subTest(change=change):
                self.refuse(
                    _validate_attestation,
                    _attestation(process_identity=_process(**change)),
                )

    def test_uid_gid_bounds(self):
        for change in (
            {"effective_uid": True},
            {"effective_uid": -1},
            {"effective_gid": True},
            {"real_uid": -1},
            {"real_gid": True},
            {"real_uid": 2 ** 63},
        ):
            with self.subTest(change=change):
                self.refuse(
                    _validate_attestation,
                    _attestation(process_identity=_process(**change)),
                )

    def test_elevated_runner_is_refused(self):
        self.refuse(
            _validate_attestation,
            _attestation(process_identity=_process(real_uid=0)),
        )
        self.refuse(
            _validate_attestation,
            _attestation(process_identity=_process(real_gid=0)),
        )

    def test_runtime_fence_and_pin_bounds(self):
        for change in (
            {"runtime_fence_generation": 0},
            {"runtime_fence_generation": True},
            {"runtime_fence_generation": -3},
            {"runtime_pin_version": 0},
            {"runtime_pin_version": True},
            {"runtime_pin_version": 2.0},
        ):
            with self.subTest(change=change):
                self.refuse(
                    _validate_attestation,
                    _attestation(lease_binding=_lease(**change)),
                )

    def test_controller_pid_bounds(self):
        self.refuse(
            _validate_attestation,
            _attestation(lease_binding=_lease(controller_process=_controller(pid=0))),
        )
        self.refuse(
            _validate_attestation,
            _attestation(
                lease_binding=_lease(controller_process=_controller(pid=True))
            ),
        )


class AttestationDigestTextTests(PaidModelPrincipalTestCase):
    def test_invalid_digest_forms(self):
        for change in (
            {"commission_sha256": OTHER_DIGEST.upper()},
            {"commission_sha256": "a" * 63},
            {"commission_sha256": "g" * 64},
            {"commission_sha256": 123},
        ):
            with self.subTest(change=change):
                self.refuse(
                    _validate_attestation,
                    _attestation(binding=_binding(**change)),
                )
        for change in (
            {"python_sha256": "A" * 64},
            {"python_sha256": D_PYTHON + "0"},
        ):
            with self.subTest(change=change):
                self.refuse(
                    _validate_attestation,
                    _attestation(evidence=_evidence(**change)),
                )

    def test_invalid_text_forms(self):
        for change in (
            {"start_identity": " 18446744009512345678"},
            {"start_identity": ""},
            {"start_identity": _LONG_TEXT},
            {"boot_id": "b18d0f2a6c6f4e7d8a91c2b3d4e5f607 "},
            {"boot_id": "boot\x00id"},
            {"observed_user": "paid runner"},
            {"observed_user": "paid!runner"},
            {"launch_nonce": "n" * 129},
            {"launch_nonce": ""},
        ):
            with self.subTest(change=change):
                self.refuse(
                    _validate_attestation,
                    _attestation(process_identity=_process(**change)),
                )

    def test_worker_and_route_identifiers(self):
        self.refuse(
            _validate_attestation,
            _attestation(paid_route=_route(provider="openai")),
        )
        self.refuse(
            _validate_attestation,
            _attestation(paid_route=_route(model="glm-4")),
        )
        self.refuse(
            _validate_attestation,
            _attestation(paid_route=_route(host_ref="")),
        )
        self.refuse(
            _validate_attestation,
            _attestation(paid_route=_route(parent_job_id="../job-1")),
        )
        self.refuse(
            _validate_attestation,
            _attestation(lease_binding=_lease(pool="openai")),
        )
        self.refuse(
            _validate_attestation,
            _attestation(lease_binding=_lease(pool=True)),
        )


class AttestationRouteCrossTests(PaidModelPrincipalTestCase):
    def test_parent_none_on_non_root_is_refused(self):
        self.refuse(
            _validate_attestation,
            _attestation(binding=_binding(root_id="root-job-1", job_id="job-2")),
        )

    def test_parent_self_is_refused(self):
        self.refuse(
            _validate_attestation,
            _attestation(
                binding=_binding(root_id="root-job-1", job_id="job-2"),
                paid_route=_route(parent_job_id="job-2"),
            ),
        )

    def test_lease_host_and_model_must_agree_with_route(self):
        self.refuse(
            _validate_attestation,
            _attestation(lease_binding=_lease(host_ref="glm-host-8")),
        )
        self.refuse(
            _validate_attestation,
            _attestation(lease_binding=_lease(model="glm-5.3-flash")),
        )


class BuildPrincipalTests(PaidModelPrincipalTestCase):
    def build(self, **attestation_changes):
        attestation = _attestation(**attestation_changes)
        principal = module.build_paid_model_principal(
            attestation, _placement(), "attempt-11"
        )
        return attestation, principal

    def test_build_valid_principal(self):
        attestation, principal = self.build()
        self.assertEqual(principal["schema_version"], module.PRINCIPAL_SCHEMA)
        self.assertEqual(principal["principal_kind"], module.PRINCIPAL_KIND)
        self.assertEqual(principal["attempt_id"], "attempt-11")
        self.assertEqual(principal["worker_id"], "worker-22")
        self.assertEqual(principal["quota_class"], "glm-frontier")
        self.assertEqual(principal["provider"], "glm")
        self.assertEqual(principal["account_label"], "glm-account-2")
        self.assertEqual(principal["host_ref"], "glm-host-7")
        self.assertEqual(principal["model"], "glm-5.3")
        self.assertEqual(principal["os_principal_name"], "paid-runner")
        self.assertEqual(principal["os_principal_uid"], 1002)
        self.assertEqual(principal["binding"], _binding())
        self.assertEqual(principal["paid_route"], _route())
        self.assertEqual(
            principal["attestation_sha256"], contract.digest(attestation)
        )
        self.assertEqual(
            principal["placement_snapshot_digest"], contract.digest(_placement())
        )
        self.assert_plain(principal)
        self.assertEqual(
            module.validate_paid_model_principal(principal), principal
        )

    def test_build_validates_attestation_without_expectations(self):
        self.refuse(
            module.build_paid_model_principal,
            _attestation(lease_binding=_lease(runtime_pin_version=0)),
            _placement(),
            "attempt-11",
        )
        self.refuse(
            module.build_paid_model_principal,
            _attestation(evidence=_evidence(policy_sha256=OTHER_DIGEST)),
            _placement(),
            "attempt-11",
        )

    def test_build_placement_mismatches(self):
        for placement in (
            _placement(worker_id="worker-23"),
            _placement(quota_class="glm-batch"),
            _placement(provider="openai"),
            _placement(account_label="glm-account-9"),
        ):
            with self.subTest(placement=placement["worker_id"]):
                self.refuse(
                    module.build_paid_model_principal,
                    _attestation(),
                    placement,
                    "attempt-11",
                )

    def test_build_attempt_mismatch(self):
        self.refuse(
            module.build_paid_model_principal, _attestation(), _placement(), "attempt-12"
        )
        self.refuse(
            module.build_paid_model_principal, _attestation(), _placement(), "attempt 11"
        )

    def test_build_placement_invalid_is_refused(self):
        self.refuse(
            module.build_paid_model_principal,
            _attestation(),
            _placement(schema_version="mastermind.executive_placement_snapshot/v2"),
            "attempt-11",
        )
        self.refuse(
            module.build_paid_model_principal,
            _attestation(),
            _placement(provider="Glm"),
            "attempt-11",
        )

    def test_build_inputs_and_output_do_not_alias(self):
        attestation = _attestation()
        placement = _placement()
        principal = module.build_paid_model_principal(
            attestation, placement, "attempt-11"
        )
        snapshot = copy.deepcopy(principal)
        attestation["binding"]["job_id"] = "mutated-job"
        placement["worker_id"] = "mutated-worker"
        self.assertEqual(principal, snapshot)
        principal["binding"]["job_id"] = "changed-again"
        principal["evidence"]["policy_sha256"] = OTHER_DIGEST
        self.assertEqual(attestation["binding"]["job_id"], "mutated-job")
        self.assertEqual(
            attestation["evidence"]["policy_sha256"], POLICY_DIGEST
        )

    def test_principal_carries_no_forbidden_authority_fields(self):
        _, principal = self.build()
        for field in (
            "provider_home_identity",
            "provider_session_id",
            "secret_canary",
            "verified",
        ):
            self.assertNotIn(field, principal)


class PrincipalValidTests(PaidModelPrincipalTestCase):
    def principal(self, **changes):
        value = module.build_paid_model_principal(
            _attestation(), _placement(), "attempt-11"
        )
        value.update(changes)
        return value

    def test_valid_roundtrip(self):
        principal = module.validate_paid_model_principal(self.principal())
        self.assertEqual(principal["principal_kind"], "PAID_MODEL_ONLY")
        self.assert_plain(principal)

    def test_shape_only_digests_do_not_claim_origin(self):
        principal = self.principal(
            attestation_sha256="0" * 64, placement_snapshot_digest="f" * 64
        )
        self.assertEqual(
            module.validate_paid_model_principal(principal)["attestation_sha256"],
            "0" * 64,
        )

    def test_input_and_output_do_not_alias(self):
        source = self.principal()
        snapshot = copy.deepcopy(source)
        result = module.validate_paid_model_principal(source)
        source["binding"]["attempt_id"] = "mutated"
        source["os_principal_uid"] = 0
        self.assertEqual(result, snapshot)
        result["process_identity"]["pid"] = 1
        self.assertEqual(source["process_identity"]["pid"], 4102)


class PrincipalRefusalTests(PaidModelPrincipalTestCase):
    def setUp(self):
        self.base = module.build_paid_model_principal(
            _attestation(), _placement(), "attempt-11"
        )

    def patched(self, **changes):
        value = copy.deepcopy(self.base)
        value.update(changes)
        return value

    def test_wrong_schema_and_kind(self):
        self.refuse(
            module.validate_paid_model_principal,
            self.patched(schema_version="mastermind.paid_model_execution_principal/v2"),
        )
        self.refuse(
            module.validate_paid_model_principal,
            self.patched(schema_version="mastermind.execution_principal_snapshot/v1"),
        )
        self.refuse(
            module.validate_paid_model_principal, self.patched(principal_kind="EXECUTION")
        )
        self.refuse(
            module.validate_paid_model_principal,
            self.patched(principal_kind="paid_model_only"),
        )

    def test_wrong_header_fields(self):
        self.refuse(
            module.validate_paid_model_principal, self.patched(profile_id="other-profile")
        )
        self.refuse(
            module.validate_paid_model_principal, self.patched(adapter_id="other-adapter")
        )
        self.refuse(
            module.validate_paid_model_principal,
            self.patched(execution_surface="glm-model-and-tools"),
        )

    def test_derived_field_mismatches(self):
        for change in (
            {"attempt_id": "attempt-12"},
            {"worker_id": "worker 23"},
            {"provider": "openai"},
            {"account_label": "glm-account-9"},
            {"host_ref": "glm-host-8"},
            {"model": "glm-5.3-flash"},
            {"os_principal_name": "other-user"},
            {"os_principal_uid": 0},
        ):
            with self.subTest(change=change):
                self.refuse(module.validate_paid_model_principal, self.patched(**change))

    def test_nested_groups_revalidated(self):
        for change in (
            {"binding": _binding(attempt_id="attempt-12")},
            {"paid_route": _route(parent_job_id="root-job-1", model="glm-5.3-flash")},
            {"process_identity": _process(real_uid=0)},
            {"lease_binding": _lease(pool="openai")},
            {"evidence": _evidence(policy_sha256=OTHER_DIGEST)},
            {"lease_binding": _lease(host_ref="glm-host-8")},
        ):
            with self.subTest(change=sorted(change)):
                self.refuse(module.validate_paid_model_principal, self.patched(**change))

    def test_unknown_authority_and_legacy_fields(self):
        for change in (
            {"provider_home_identity": {"path": "/home/x"}},
            {"provider_session_id": "session-1"},
            {"secret_canary": "canary"},
            {"verified": True},
            {"placement_snapshot": {}},
        ):
            with self.subTest(change=sorted(change)):
                self.refuse(module.validate_paid_model_principal, self.patched(**change))

    def test_missing_and_renamed_top_keys(self):
        broken = copy.deepcopy(self.base)
        del broken["quota_class"]
        self.refuse(module.validate_paid_model_principal, broken)
        renamed = copy.deepcopy(self.base)
        renamed["route"] = renamed.pop("paid_route")
        self.refuse(module.validate_paid_model_principal, renamed)

    def test_digest_shape_only(self):
        self.refuse(
            module.validate_paid_model_principal,
            self.patched(placement_snapshot_digest="ABCDEF"),
        )
        self.refuse(
            module.validate_paid_model_principal,
            self.patched(attestation_sha256="a" * 63),
        )

    def test_non_dict_inputs_are_refused(self):
        for value in (None, [], "principal", 7, _DictSubclass(self.base),
                      _CustomMapping(self.base)):
            self.refuse(module.validate_paid_model_principal, value)


class PurityTests(PaidModelPrincipalTestCase):
    def test_no_io_during_validation(self):
        attestation = _attestation()
        principal = module.build_paid_model_principal(
            attestation, _placement(), "attempt-11"
        )
        failures = []

        def bomb(name):
            def _raise(*args, **kwargs):
                failures.append(name)
                raise AssertionError(f"unexpected {name} use during validation")

            return _raise

        with mock.patch("builtins.open", bomb("open")), mock.patch.object(
            io, "open", bomb("io.open")
        ), mock.patch.object(socket, "socket", bomb("socket")), mock.patch.object(
            subprocess, "Popen", bomb("Popen")
        ), mock.patch.object(
            os, "remove", bomb("os.remove")
        ), mock.patch.object(
            os, "system", bomb("os.system")
        ):
            _validate_attestation(attestation, **_expectations())
            module.build_paid_model_principal(attestation, _placement(), "attempt-11")
            module.validate_paid_model_principal(principal)
        self.assertEqual(failures, [])

    def test_results_are_detached_plain_json_data(self):
        attestation = _attestation()
        results = (
            _validate_attestation(attestation, **_expectations()),
            module.build_paid_model_principal(attestation, _placement(), "attempt-11"),
            module.validate_paid_model_principal(
                module.build_paid_model_principal(
                    attestation, _placement(), "attempt-11"
                )
            ),
        )
        for result in results:
            self.assert_plain(result)
            self.assertNotIn("verified", result)
            self.assertIsInstance(result, dict)




class ParentStrictDataBoundaryTests(PaidModelPrincipalTestCase):
    def test_header_scalar_callback_is_never_called(self):
        class Trap:
            def __eq__(self, other):
                raise AssertionError("untrusted equality invoked")
        for field in ("schema_version", "profile_id", "adapter_id", "execution_surface"):
            value = _attestation()
            value[field] = Trap()
            self.refuse(module.validate_paid_model_attestation, value, **_expectations())
        for field in ("schema_version", "principal_kind", "profile_id", "adapter_id", "execution_surface"):
            value = module.build_paid_model_principal(_attestation(), _placement(), "attempt-11")
            value[field] = Trap()
            self.refuse(module.validate_paid_model_principal, value)

    def test_nonplain_key_is_refused_before_equality(self):
        class Key(str):
            def __eq__(self, other):
                raise AssertionError("untrusted key equality invoked")
            __hash__ = str.__hash__
        value = _attestation()
        del value["schema_version"]
        value[Key("schema_version")] = contract.ATTESTATION_SCHEMA
        self.refuse(module.validate_paid_model_attestation, value, **_expectations())

    def test_placement_custom_data_refused_before_v1_validator(self):
        for placement in (_DictSubclass(_placement()), _CustomMapping(_placement())):
            self.refuse(module.build_paid_model_principal, _attestation(), placement, "attempt-11")
        class Scalar(str):
            def strip(self):
                raise AssertionError("untrusted placement callback invoked")
        for field in ("schema_version", "worker_id", "quota_class", "provider", "account_label"):
            value = _placement()
            value[field] = Scalar(value[field])
            self.refuse(module.build_paid_model_principal, _attestation(), value, "attempt-11")
        for value in (True, -1, 2**63, float("inf")):
            self.refuse(module.build_paid_model_principal, _attestation(),
                        _placement(observed_at_ms=value), "attempt-11")


class FullOwnerExpectationTests(PaidModelPrincipalTestCase):
    def test_every_binding_route_process_lease_evidence_expectation_is_compared(self):
        for group, argument in (
            ("binding", "expected_binding"), ("paid_route", "expected_route"),
            ("process_identity", "expected_process"), ("lease_binding", "expected_lease_binding"),
            ("evidence", "expected_evidence"),
        ):
            original = _attestation()[group]
            for key, value in original.items():
                if key == "policy_sha256":
                    continue  # Matching wrong-policy refusal is covered separately.
                changed = copy.deepcopy(original)
                if type(value) is dict:
                    changed[key]["pid"] += 1
                elif type(value) is int:
                    changed[key] += 1
                    if key in ("effective_uid", "real_uid"):
                        changed["effective_uid"] = changed["real_uid"] = value + 1
                    if key in ("effective_gid", "real_gid"):
                        changed["effective_gid"] = changed["real_gid"] = value + 1
                elif value is None:
                    changed[key] = "another-parent"
                elif key == "model":
                    changed[key] = "glm-5.3" if value == "glm-5.3-flash" else "glm-5.3-flash"
                elif key == "pool":
                    changed[key] = "glm" if value == "glm-frontier" else "glm-frontier"
                elif len(value) == 64 and all(c in "0123456789abcdef" for c in value):
                    changed[key] = OTHER_DIGEST
                else:
                    changed[key] = "different-value"
                with self.subTest(group=group, key=key):
                    self.refuse(module.validate_paid_model_attestation, _attestation(),
                                **_expectations(**{argument: changed}))


if __name__ == "__main__":
    unittest.main()
