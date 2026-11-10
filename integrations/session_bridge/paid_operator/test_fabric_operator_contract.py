"""Independent fixture-driven unittest suite for fabric_operator_contract.

Every fixture dict is built fresh per call; nothing is shared or mutated
across tests. These tests prove validator behavior only; they are not and
do not claim any runtime or installation proof.
"""

import copy
import math
import unittest

import fabric_operator_contract as foc

NOW = 1_760_000_000.0
ISSUED = NOW - 600.0
EXPIRES = NOW + 3000.0
ROOT = "root.ctrl.7"
OPERATOR_RUN = "run.fabric.operator.0001"
LEASE_ID = "lease.9001"
ACCOUNT = "acct.paid.a1"
HOST = "worker_01"
SUPPORT_SHA = "00ffe1954329f3bd6e3796ae131730159fb21a20a76487aec53171e91a4264ea"
PACKET_SHA = "0888a12e130bd211288337cfc7e8d46557a7afb146319686afd667778113dfca"
OTHER_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
POOL_MODEL = {"glm": "glm-5.3", "grok": "grok-4.6"}
_UNSET = object()


def grant(pool="glm", **over):
    record = {
        "schema": foc.GRANT_SCHEMA,
        "root": ROOT,
        "operator_run": OPERATOR_RUN,
        "lease_id": LEASE_ID,
        "pool": pool,
        "model": POOL_MODEL[pool],
        "account": ACCOUNT,
        "host": HOST,
        "support_sha256": SUPPORT_SHA,
        "packet_sha256": PACKET_SHA,
        "issued_at": ISSUED,
        "expires_at": EXPIRES,
        "child_budget": 8,
        "allowed_classes": ["mechanical", "extract", "census"],
    }
    record.update(over)
    return record


def lease(pool="glm", **over):
    record = {
        "id": LEASE_ID,
        "orchestrator_id": ROOT,
        "pool": pool,
        "account": ACCOUNT,
        "task_class": "remote-" + pool,
        "model": POOL_MODEL[pool],
        "host": HOST,
        "pid": 4821,
        "granted_at": NOW - 900.0,
        "ttl": 120,
        "last_heartbeat": NOW - 15.0,
        "state": "rented",
        "renewable": 1,
    }
    record.update(over)
    return record


def launch(pool="glm", **over):
    record = {
        "root": ROOT,
        "run_id": OPERATOR_RUN,
        "lease_id": LEASE_ID,
        "pool": pool,
        "model": POOL_MODEL[pool],
        "account": ACCOUNT,
        "host": HOST,
        "support_sha256": SUPPORT_SHA,
        "packet_sha256": PACKET_SHA,
        "task_class": foc.OPERATOR_TASK_CLASS,
    }
    record.update(over)
    return record


def request(**over):
    record = {
        "schema": foc.REQUEST_SCHEMA,
        "root": ROOT,
        "parent": OPERATOR_RUN,
        "run_id": "child.run.0007",
        "task_class": "extract",
        "task_complexity": "C1_ROUTINE_BOUNDED",
        "packet": "summarize the failing build-log excerpt for the operator",
    }
    record.update(over)
    return record


class ValidPaths(unittest.TestCase):
    def test_valid_glm_child_is_normalized(self):
        child = foc.validate_launch(
            grant(), lease(), launch(), request(),
            now=NOW, used_children=3, root_children_remaining=5,
        )
        self.assertEqual(child["root"], ROOT)
        self.assertEqual(child["parent"], OPERATOR_RUN)
        self.assertEqual(child["child_run_id"], "child.run.0007")
        self.assertEqual(child["task_class"], "extract")
        self.assertEqual(child["task_complexity"], "C1_ROUTINE_BOUNDED")
        self.assertEqual(
            child["packet"], "summarize the failing build-log excerpt for the operator"
        )
        self.assertIs(child["needs_new_lease"], True)
        self.assertEqual(set(child), set(foc.CHILD_RECORD_KEYS))

    def test_valid_grok_child_is_normalized(self):
        child = foc.validate_launch(
            grant(pool="grok"), lease(pool="grok"), launch(pool="grok"),
            request(task_class="mechanical", task_complexity="C0_MECHANICAL"),
            now=NOW, used_children=0, root_children_remaining=64,
        )
        self.assertEqual(child["task_class"], "mechanical")
        self.assertEqual(child["task_complexity"], "C0_MECHANICAL")

    def test_child_claims_no_resources_and_no_lease_reuse(self):
        child = foc.validate_launch(
            grant(), lease(), launch(), request(),
            now=NOW, used_children=7, root_children_remaining=1,
        )
        for absent in ("lease_id", "pool", "model", "account", "host",
                       "pid", "ttl", "child_budget"):
            self.assertNotIn(absent, child)
        self.assertTrue(child["needs_new_lease"])

    def test_now_exactly_at_issued_boundary_is_accepted(self):
        child = foc.validate_launch(
            grant(issued_at=NOW), lease(), launch(), request(),
            now=NOW, used_children=0, root_children_remaining=2,
        )
        self.assertEqual(child["root"], ROOT)

    def test_grant_duration_exactly_7200_is_accepted(self):
        foc.validate_launch(
            grant(issued_at=NOW - 3600.0, expires_at=NOW - 3600.0 + 7200.0),
            lease(), launch(), request(),
            now=NOW, used_children=0, root_children_remaining=2,
        )

    def test_used_children_one_below_budget_is_accepted(self):
        foc.validate_launch(
            grant(child_budget=8), lease(), launch(), request(),
            now=NOW, used_children=7, root_children_remaining=1,
        )

    def test_packet_exactly_65536_bytes_is_accepted(self):
        child = foc.validate_launch(
            grant(), lease(), launch(), request(packet="a" * 65536),
            now=NOW, used_children=0, root_children_remaining=1,
        )
        self.assertEqual(len(child["packet"]), 65536)

    def test_multibyte_utf8_bytes_packet_is_normalized_to_text(self):
        child = foc.validate_launch(
            grant(), lease(), launch(), request(packet=b"build \xe2\x80\x94 log"),
            now=NOW, used_children=0, root_children_remaining=1,
        )
        self.assertEqual(child["packet"], "build \u2014 log")

    def test_extra_canonical_broker_fields_on_lease_are_tolerated(self):
        child = foc.validate_launch(
            grant(), lease(broker_epoch=42, queue="fabric-fast"), launch(),
            request(), now=NOW, used_children=0, root_children_remaining=1,
        )
        self.assertEqual(child["needs_new_lease"], True)


class Refusals(unittest.TestCase):
    def refused(self, code, g=_UNSET, l=_UNSET, la=_UNSET, r=_UNSET, now=NOW,
                used=0, remaining=4):
        with self.assertRaises(foc.DelegationRefused) as ctx:
            foc.validate_launch(
                grant() if g is _UNSET else g,
                lease() if l is _UNSET else l,
                launch() if la is _UNSET else la,
                request() if r is _UNSET else r,
                now=now, used_children=used, root_children_remaining=remaining,
            )
        message = str(ctx.exception)
        self.assertEqual(message, code)
        self.assertIn(message, foc.REASON_CODES)
        self.assertIsInstance(ctx.exception, ValueError)

    def test_wrong_root_in_request(self):
        self.refused("request_root_mismatch", r=request(root="root.other.9"))

    def test_wrong_parent_in_request(self):
        self.refused("request_parent_mismatch",
                     r=request(parent="run.fabric.operator.0002"))

    def test_leaf_self_delegation_role_is_refused(self):
        # A leaf naming itself (or the root) as parent is not the operator.
        self.refused("request_parent_mismatch", r=request(parent="child.run.0007"))
        self.refused("request_parent_mismatch", r=request(parent=ROOT))

    def test_child_run_id_must_be_distinct(self):
        self.refused("request_run_id_not_distinct", r=request(run_id=ROOT))
        self.refused("request_run_id_not_distinct",
                     r=request(run_id=OPERATOR_RUN))

    def test_unsupported_pool_model_pair_in_grant(self):
        self.refused("grant_pool_model_pair",
                     g=grant(pool="glm", model="grok-4.6"))
        self.refused("grant_pool_model_pair", g=grant(model="glm-4.5"))

    def test_lease_cross_pool_binding(self):
        self.refused("lease_binding_mismatch",
                     l=lease(pool="grok", task_class="remote-grok"))

    def test_lease_identity_binding(self):
        self.refused("lease_binding_mismatch", l=lease(id="lease.9002"))
        self.refused("lease_binding_mismatch",
                     l=lease(orchestrator_id="root.ctrl.8"))

    def test_lease_task_class_must_be_remote_mode(self):
        self.refused("lease_task_class_mode", l=lease(task_class="local-glm"))
        self.refused("lease_task_class_mode",
                     l=lease(task_class="domain_orchestration"))

    def test_operator_class_in_request_is_not_a_leaf_class(self):
        self.refused("request_task_class_not_leaf",
                     r=request(task_class="domain_orchestration"))
        self.refused("request_task_class_not_leaf",
                     r=request(task_class="remote-glm"))

    def test_class_outside_closed_leafset_is_refused(self):
        self.refused("request_task_class_not_leaf",
                     r=request(task_class="launch_child"))

    def test_class_not_granted_by_allowlist(self):
        self.refused("request_task_class_not_granted", r=request(task_class="census"),
                     g=grant(allowed_classes=["mechanical", "extract"]))

    def test_unsupported_complexity(self):
        self.refused("request_complexity_invalid",
                     r=request(task_complexity="C2_OPEN_ENDED"))
        self.refused("request_complexity_invalid",
                     r=request(task_complexity="c0_mechanical"))

    def test_caller_override_fields_are_unknown_fields(self):
        for key, value in (("pool", "grok"), ("model", "grok-4.6"),
                           ("host", "worker_02"), ("lease_id", "lease.9999"),
                           ("env", {"POOL": "grok"})):
            with self.subTest(key=key):
                self.refused("request_unknown_field",
                             r=request(**{key: value}))

    def test_altered_launch_digests_are_refused(self):
        self.refused("launch_binding_mismatch", la=launch(packet_sha256=OTHER_SHA))
        self.refused("launch_binding_mismatch", la=launch(support_sha256=OTHER_SHA))

    def test_altered_launch_identity_is_refused(self):
        self.refused("launch_binding_mismatch", la=launch(run_id="run.other.1"))
        self.refused("launch_binding_mismatch", la=launch(pool="grok", model="grok-4.6"))

    def test_launch_task_class_must_be_operator_orchestration(self):
        self.refused("launch_task_class_invalid",
                     la=launch(task_class="remote-glm"))

    def test_released_lease_is_refused(self):
        self.refused("lease_state_invalid", l=lease(state="released"))
        self.refused("lease_state_invalid", l=lease(state="held "))

    def test_expired_lease_at_boundary_is_refused(self):
        # now == last_heartbeat + ttl is expired, not grace.
        self.refused("lease_ttl_expired",
                     l=lease(last_heartbeat=NOW - 120.0, ttl=120))

    def test_heartbeat_in_future_or_before_grant(self):
        self.refused("lease_sequence_invalid", l=lease(last_heartbeat=NOW + 60.0))
        self.refused("lease_sequence_invalid",
                     l=lease(granted_at=NOW - 1.0, last_heartbeat=NOW - 15.0))

    def test_nonrenewable_hard_ttl_expiry(self):
        # Fresh heartbeat but now >= granted_at + ttl and renewable == 0.
        self.refused("lease_hard_ttl_expired",
                     l=lease(renewable=0, granted_at=NOW - 400.0, ttl=300,
                             last_heartbeat=NOW - 15.0))

    def test_lease_clock_and_int_domains(self):
        self.refused("lease_clock_invalid", l=lease(granted_at=float("nan")))
        self.refused("lease_clock_invalid", l=lease(last_heartbeat=math.inf))
        self.refused("lease_pid_invalid", l=lease(pid=0))
        self.refused("lease_pid_invalid", l=lease(pid=True))
        self.refused("lease_ttl_invalid", l=lease(ttl=0))
        self.refused("lease_renewable_invalid", l=lease(renewable=True))
        self.refused("lease_renewable_invalid", l=lease(renewable=2))
        self.refused("lease_renewable_invalid", l=lease(renewable="1"))

    def test_lease_missing_required_field(self):
        broken = lease()
        del broken["renewable"]
        self.refused("lease_missing_field", l=broken)

    def test_bad_grant_deadlines(self):
        self.refused("grant_duration_limit", g=grant(expires_at=ISSUED + 7201.0))
        self.refused("grant_deadline_order",
                     g=grant(issued_at=NOW, expires_at=NOW))
        self.refused("grant_clock_invalid", g=grant(issued_at=math.inf))
        self.refused("grant_clock_invalid", g=grant(expires_at=float("nan")))

    def test_grant_window_boundaries(self):
        self.refused("grant_window_expired", g=grant(expires_at=NOW), now=NOW)
        self.refused("grant_window_expired",
                     g=grant(issued_at=NOW + 10.0, expires_at=NOW + 600.0))

    def test_boolean_and_out_of_range_counts(self):
        self.refused("grant_budget_domain", g=grant(child_budget=True))
        self.refused("grant_budget_domain", g=grant(child_budget=0))
        self.refused("grant_budget_domain", g=grant(child_budget=65))
        self.refused("used_children_invalid", used=True)
        self.refused("used_children_invalid", used=-1)
        self.refused("root_children_remaining_invalid", remaining=True)
        self.refused("root_children_remaining_invalid", remaining=-3)

    def test_exhausted_budgets(self):
        self.refused("grant_budget_exhausted", used=8)
        self.refused("root_budget_exhausted", remaining=0)

    def test_packet_rejections(self):
        self.refused("request_packet_size", r=request(packet=""))
        self.refused("request_packet_size", r=request(packet="a" * 65537))
        self.refused("request_packet_encoding", r=request(packet="\ud800abc"))
        self.refused("request_packet_nul", r=request(packet="ok\x00bad"))
        self.refused("request_packet_encoding", r=request(packet=b"\xff\xfebad"))
        self.refused("request_packet_type", r=request(packet=123))

    def test_invalid_now(self):
        self.refused("now_invalid", now=float("nan"))
        self.refused("now_invalid", now=math.inf)
        self.refused("now_invalid", now=True)

    def test_record_shape_and_schema(self):
        self.refused("grant_not_mapping", g="grant")
        self.refused("lease_not_mapping", l=[])
        self.refused("launch_not_mapping", la=None)
        self.refused("request_not_mapping", r="request")
        self.refused("grant_schema", g=grant(schema="mastermind.fabric_operator_grant.v2"))
        self.refused("request_schema", r=request(schema="mastermind.fabric_operator_child_request.v0"))
        broken_grant = grant()
        del broken_grant["root"]
        self.refused("grant_missing_field", g=broken_grant)
        self.refused("grant_unknown_field", g=grant(broker_note="x"))
        broken_launch = launch()
        del broken_launch["host"]
        self.refused("launch_missing_field", la=broken_launch)
        self.refused("launch_unknown_field", la=launch(env="prod"))
        broken_request = request()
        del broken_request["packet"]
        self.refused("request_missing_field", r=broken_request)

    def test_grant_field_domains(self):
        self.refused("grant_id_invalid", g=grant(host="-worker_01"))
        self.refused("grant_id_invalid", g=grant(root="root." + "x" * 129))
        self.refused("grant_hash_invalid", g=grant(packet_sha256="ABC"))
        self.refused("grant_hash_invalid",
                     g=grant(support_sha256=SUPPORT_SHA.upper()))
        self.refused("grant_classes_invalid", g=grant(allowed_classes=[]))
        self.refused("grant_classes_invalid", g=grant(allowed_classes=["extract", "extract"]))
        self.refused("grant_classes_invalid",
                     g=grant(allowed_classes=["mechanical", "domain_orchestration"]))
        self.refused("grant_classes_invalid", g=grant(allowed_classes="extract"))
        self.refused("request_run_id_invalid", r=request(run_id=".child.9"))

    def test_all_reason_codes_are_closed(self):
        self.assertIsInstance(foc.REASON_CODES, frozenset)
        self.assertTrue(all(isinstance(code, str) and code for code in foc.REASON_CODES))


class NoMutation(unittest.TestCase):
    def test_inputs_not_mutated_on_success(self):
        g, l, la, r = (grant(), lease(), launch(),
                       request(packet="build \u00e9 log \u2014 tail"))
        snapshot = (copy.deepcopy(g), copy.deepcopy(l),
                    copy.deepcopy(la), copy.deepcopy(r))
        child = foc.validate_launch(g, l, la, r, now=NOW,
                                    used_children=2, root_children_remaining=9)
        self.assertEqual((g, l, la, r), snapshot)
        child["packet"] = "tampered"
        child["needs_new_lease"] = False
        self.assertEqual((g, l, la, r), snapshot)

    def test_inputs_not_mutated_on_refusal(self):
        g, l, la, r = grant(), lease(), launch(), request(packet="x" * 65537)
        snapshot = (copy.deepcopy(g), copy.deepcopy(l),
                    copy.deepcopy(la), copy.deepcopy(r))
        with self.assertRaises(foc.DelegationRefused):
            foc.validate_launch(g, l, la, r, now=NOW,
                                used_children=0, root_children_remaining=1)
        self.assertEqual((g, l, la, r), snapshot)


if __name__ == "__main__":
    unittest.main()
