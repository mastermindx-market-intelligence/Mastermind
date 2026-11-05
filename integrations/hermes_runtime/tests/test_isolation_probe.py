"""Unit tests for the credential-free final-role isolation qualification probe.

These tests exercise the probe's *source* behaviour: the guard reuse and
order, the witness rules, the honest classification vocabulary and the
attribution of a denial to the control that refused it.

They do NOT claim real final-role execution. Every boundary that would need
a real PID1 role cgroup, a real Landlock attachment, a real sibling account
or a real service is mocked, and a mocked observation is reported as a mocked
observation. The real Linux kernel enforcement is already covered by
``tests/test_tcp_sandbox_linux.py`` and must not be re-presented here.
"""
from __future__ import annotations

import argparse
import errno
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from integrations.hermes_runtime import isolation_probe as probe
from integrations.hermes_runtime import role_isolation, system_service, tcp_sandbox
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.profile import RuntimeProfile

REPO = Path(__file__).resolve().parents[3]
SOURCE = Path(probe.__file__).read_text(encoding="utf-8")


def make_profile(role: str = "mmsecretary", *, state_dir: Path | None = None,
                 secrets_file: Path | None = None,
                 gateway_port: int | None = None,
                 backend_port: int | None = None) -> RuntimeProfile:
    """A profile built directly, so the test never needs the harness package."""
    ports = probe.ROLE_FIXED_PORTS[role]
    state = state_dir or Path("/srv/hermes") / role / "state"
    secrets = secrets_file or Path("/srv/hermes") / role / "private" / "role.env"
    return RuntimeProfile(
        schema="mastermind.hermes_runtime_profile.v1",
        role=role,
        sha="1c0cd667746d3395fe9e1b6c74f8f85952486f18",
        repository="https://github.com/NousResearch/hermes-agent.git",
        tool_allowlist=frozenset({"clarify"}),
        secrets_file=secrets,
        gateway_host=probe.ROLE_PROXY_HOST[role],
        gateway_port=ports["gateway"] if gateway_port is None else gateway_port,
        backend_port=ports["backend"] if backend_port is None else backend_port,
        auth_required=True,
        state_dir=state,
        hermes_home=state / "current" / "hermes-home",
        restart="on-failure",
        restart_sec=2.0,
        start_limit_burst=5,
        start_limit_interval_sec=60,
        memory_sample_interval_sec=5.0,
        model_provider="zai",
        model_default="glm-5.3-flash",
        source_path=Path("/srv/hermes/profile.yaml"),
        service_name=f"hermes-runtime-{role}",
    )


def case_by_id(case_id: str, role: str = "mmsecretary") -> probe._Case:
    """A matrix case bound to the role's real ports, as the probe binds it."""
    ports = probe.ROLE_FIXED_PORTS[role]
    for case in probe._bind_cases(role, ports["gateway"], ports["backend"],
                                  probe.DEFAULT_DENIED_PORT[role]):
        if case.case_id == case_id:
            return case
    raise AssertionError(f"unknown case {case_id}")


class SourcePurityTests(unittest.TestCase):
    """The probe must not be able to provision, activate or read a secret."""

    def test_production_guards_are_reused_not_reimplemented(self):
        self.assertIs(probe.assert_root_service_cgroup,
                      system_service.assert_root_service_cgroup)
        self.assertIs(probe.assert_role_network_profile,
                      system_service.assert_role_network_profile)
        self.assertIs(probe.assert_role_credential_isolation,
                      role_isolation.assert_role_credential_isolation)
        self.assertIs(probe.enforce_role_tcp_ports, tcp_sandbox.enforce_role_tcp_ports)

    def test_probe_never_reaches_the_secret_reader_or_the_supervisor(self):
        self.assertFalse(hasattr(probe, "load_secrets"))
        self.assertFalse(hasattr(probe, "ServiceRuntime"))
        for forbidden in ("from .secrets import", "from .supervisor import",
                          "from .cli import", "import integrations.hermes_runtime.cli"):
            self.assertNotIn(forbidden, SOURCE)

    def test_probe_never_manages_a_unit_or_a_firewall(self):
        for forbidden in ("systemctl", "os.system", "os.killpg", "iptables",
                          "nft ", "ufw "):
            self.assertNotIn(forbidden, SOURCE)

    def test_importing_the_probe_starts_nothing(self):
        before = probe._listening_local_addresses(0)
        completed = subprocess.run(
            [sys.executable, "-c",
             "import integrations.hermes_runtime.isolation_probe as p; "
             "import sys; "
             "print('cli' if 'integrations.hermes_runtime.cli' in sys.modules else 'no-cli')"],
            cwd=REPO, env={"PATH": os.defpath, "PYTHONPATH": str(REPO),
                           "PYTHONDONTWRITEBYTECODE": "1"},
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30,
            close_fds=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "no-cli")
        self.assertEqual(probe._listening_local_addresses(0), before)


class GuardOrderTests(unittest.TestCase):
    def test_the_three_observation_guards_run_in_production_order(self):
        order: list[str] = []

        def recorder(name):
            def call(*args, **kwargs):
                order.append(name)
            return call

        with (
            mock.patch.object(probe, "assert_root_service_cgroup", recorder("cgroup")),
            mock.patch.object(probe, "assert_role_network_profile", recorder("network")),
            mock.patch.object(probe, "assert_role_credential_isolation", recorder("credential")),
        ):
            guards, ok = probe._run_guards(make_profile(), "mmsecretary")
        self.assertTrue(ok)
        self.assertEqual(order, ["cgroup", "network", "credential"])
        self.assertEqual([entry["name"] for entry in guards],
                         ["assert_root_service_cgroup", "assert_role_network_profile",
                          "assert_role_credential_isolation"])

    def test_a_refused_observation_guard_stops_the_sequence(self):
        order: list[str] = []

        def refuse(*args, **kwargs):
            order.append("network")
            raise RuntimeRefusal("ROOT_UNIT_SHARED_LOOPBACK_REFUSED")

        with (
            mock.patch.object(probe, "assert_root_service_cgroup",
                              side_effect=lambda *a, **k: order.append("cgroup")),
            mock.patch.object(probe, "assert_role_network_profile", refuse),
            mock.patch.object(probe, "assert_role_credential_isolation",
                              side_effect=lambda *a, **k: order.append("credential")),
        ):
            guards, ok = probe._run_guards(make_profile(), "mmsecretary")
        self.assertFalse(ok)
        self.assertEqual(order, ["cgroup", "network"])
        self.assertEqual(guards[-1]["status"], "REFUSED")
        self.assertEqual(guards[-1]["code"], "ROOT_UNIT_SHARED_LOOPBACK_REFUSED")

    def test_the_tcp_policy_is_never_applied_after_a_refused_guard(self):
        args = _args()
        with (
            mock.patch.object(probe, "load_profile", return_value=make_profile()),
            mock.patch.object(probe, "_identity_facts", return_value=_identity()),
            mock.patch.object(probe, "assert_root_service_cgroup",
                              side_effect=RuntimeRefusal("ROOT_UNIT_CGROUP_UNQUALIFIED")),
            mock.patch.object(probe, "enforce_role_tcp_ports") as enforce,
            mock.patch.object(probe, "_spawn_listener") as spawn,
        ):
            code = probe._run_probe(args)
        self.assertEqual(code, probe.CONFIG_EXIT)
        enforce.assert_not_called()
        spawn.assert_not_called()


class ClassificationTests(unittest.TestCase):
    def test_a_refusal_without_a_witness_is_never_a_pass(self):
        case = probe._Case("x", "tcp", "d", probe.OBSERVED_REFUSED)
        outcome = probe._Outcome(probe.OBSERVED_REFUSED, witness={"sufficient": False})
        self.assertEqual(probe._status_for(case, outcome), probe.STATUS_UNAVAILABLE)
        outcome = probe._Outcome(probe.OBSERVED_REFUSED, witness={"sufficient": True})
        self.assertEqual(probe._status_for(case, outcome), probe.STATUS_PASS)

    def test_an_expected_allow_that_is_refused_is_a_failure(self):
        case = probe._Case("x", "tcp", "d", probe.OBSERVED_ALLOWED)
        outcome = probe._Outcome(probe.OBSERVED_REFUSED, witness={"sufficient": True})
        self.assertEqual(probe._status_for(case, outcome), probe.STATUS_FAIL)

    def test_a_refused_connection_is_not_denial_proof(self):
        case = case_by_id("tcp.own_alias.denied_port")
        listeners = {"wildcard_denied": {"bound": True, "kernel_listening": True,
                                         "kernel_listen_entries": ["00000000"]}}
        unconfined = {"wildcard_denied": {"reached": True, "errno": None,
                                          "errno_name": None, "symptom": "connected"}}
        with mock.patch.object(probe, "_connect",
                               return_value=(errno.ECONNREFUSED, "refused_immediately")):
            outcome = probe._tcp_outcome(case, listeners, unconfined,
                                         frozenset({8765, 8766, 18651}), 1.0)
        self.assertEqual(outcome.observed, probe.OBSERVED_UNAVAILABLE)
        self.assertEqual(probe._status_for(case, outcome), probe.STATUS_UNAVAILABLE)
        self.assertFalse(outcome.witness["sufficient"])

    def test_a_missing_listener_is_unavailable_not_a_pass(self):
        case = case_by_id("tcp.own_alias.gateway_port")
        listeners = {"own_gateway": {"bound": False, "errno": errno.EADDRINUSE}}
        outcome = probe._tcp_outcome(case, listeners, {}, frozenset({8765}), 1.0)
        self.assertEqual(outcome.observed, probe.OBSERVED_UNAVAILABLE)
        self.assertEqual(probe._status_for(case, outcome), probe.STATUS_UNAVAILABLE)

    def test_a_landlock_denial_is_attributed_to_landlock(self):
        case = case_by_id("tcp.own_alias.denied_port")
        listeners = {"wildcard_denied": {"bound": True, "kernel_listening": True,
                                         "kernel_listen_entries": ["00000000"]}}
        unconfined = {"wildcard_denied": {"reached": True, "errno": None,
                                          "errno_name": None, "symptom": "connected"}}
        with mock.patch.object(probe, "_connect",
                               return_value=(errno.EACCES, "refused_immediately")):
            outcome = probe._tcp_outcome(case, listeners, unconfined,
                                         frozenset({8765, 8766, 18651}), 1.0)
        self.assertEqual(outcome.attribution, "LANDLOCK_TCP_PORT")
        self.assertEqual(probe._status_for(case, outcome), probe.STATUS_PASS)

    def test_an_address_denial_on_an_allowed_port_is_attributed_to_the_ip_policy(self):
        for case_id in ("tcp.sibling_alias.gateway_port", "tcp.shared_loopback.gateway_port"):
            with self.subTest(case=case_id):
                case = case_by_id(case_id)
                key = case.listener
                listeners = {key: {"bound": True, "kernel_listening": True,
                                   "kernel_listen_entries": ["0100007F"]}}
                unconfined = {key: {"reached": False, "errno": errno.EAGAIN,
                                    "errno_name": "EAGAIN", "symptom": "timed_out"}}
                with mock.patch.object(probe, "_connect",
                                       return_value=(errno.EAGAIN, "timed_out")):
                    outcome = probe._tcp_outcome(case, listeners, unconfined,
                                                 frozenset({8765, 8766, 18651}), 1.0)
                self.assertEqual(outcome.attribution, "CGROUP_IP_POLICY")
                self.assertEqual(outcome.symptom, "timed_out")
                self.assertEqual(probe._status_for(case, outcome), probe.STATUS_PASS)

    def test_a_timeout_is_kept_distinct_from_an_immediate_refusal(self):
        case = case_by_id("tcp.sibling_alias.gateway_port")
        listeners = {"sibling_gateway": {"bound": True, "kernel_listening": True,
                                         "kernel_listen_entries": ["0100007F"]}}
        unconfined = {"sibling_gateway": {"reached": False, "errno": errno.EAGAIN,
                                          "errno_name": "EAGAIN", "symptom": "timed_out"}}
        with mock.patch.object(probe, "_connect",
                               return_value=(errno.EAGAIN, "timed_out")):
            outcome = probe._tcp_outcome(case, listeners, unconfined,
                                         frozenset({8765, 8766, 18651}), 1.0)
        self.assertEqual(outcome.errno_name, "EAGAIN")
        self.assertEqual(outcome.symptom, "timed_out")
        self.assertNotEqual(outcome.symptom, "refused_immediately")

    def test_the_exec_descendant_must_inherit_the_denial(self):
        case = case_by_id("exec.own_alias.denied_port")
        with mock.patch.object(probe, "_exec_probe",
                               return_value=("refused_immediately", errno.EACCES)) as ex:
            outcome = probe._exec_outcome(case, ("connected", None), 1.0)
        self.assertEqual(outcome.observed, probe.OBSERVED_REFUSED)
        self.assertEqual(probe._status_for(case, outcome), probe.STATUS_PASS)
        self.assertEqual(outcome.attribution, "LANDLOCK_TCP_PORT")
        ex.assert_called()

    def test_an_exec_denial_without_a_pre_restriction_witness_is_unavailable(self):
        case = case_by_id("exec.own_alias.denied_port")
        with mock.patch.object(probe, "_exec_probe",
                               return_value=("refused_immediately", errno.EACCES)):
            outcome = probe._exec_outcome(case, ("timed_out", errno.EAGAIN), 1.0)
        self.assertEqual(outcome.observed, probe.OBSERVED_UNAVAILABLE)
        self.assertEqual(probe._status_for(case, outcome), probe.STATUS_UNAVAILABLE)

    def test_an_exec_descendant_that_escapes_the_denial_is_a_failure(self):
        case = case_by_id("exec.own_alias.denied_port")
        with mock.patch.object(probe, "_exec_probe", return_value=("connected", None)):
            outcome = probe._exec_outcome(case, ("connected", None), 1.0)
        self.assertEqual(outcome.observed, probe.OBSERVED_ALLOWED)
        self.assertEqual(probe._status_for(case, outcome), probe.STATUS_FAIL)


class FileIsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hermes-iso-probe-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write_marker(self, path: Path, mode: int = 0o600) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, mode)
        try:
            os.write(fd, probe.SYNTHETIC_MARKER)
        finally:
            os.close(fd)
        return path

    def test_the_own_marker_file_is_readable(self):
        state = self.root / "state"
        path = self.write_marker(state / "synthetic.txt")
        outcome = probe._file_outcome_own(path, state, os.getuid(), os.getgid())
        self.assertEqual(outcome.observed, probe.OBSERVED_ALLOWED)
        self.assertTrue(outcome.witness["sufficient"])
        self.assertEqual(outcome.witness["sha256"], probe.SYNTHETIC_MARKER_SHA256)

    def test_a_foreign_content_file_is_not_a_valid_fixture(self):
        state = self.root / "state"
        path = state / "synthetic.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not the marker")
        os.chmod(path, 0o600)
        outcome = probe._file_outcome_own(path, state, os.getuid(), os.getgid())
        self.assertEqual(outcome.observed, probe.OBSERVED_ERROR)

    def test_a_loose_mode_own_file_is_refused(self):
        state = self.root / "state"
        path = self.write_marker(state / "synthetic.txt", mode=0o644)
        os.chmod(path, 0o644)
        outcome = probe._file_outcome_own(path, state, os.getuid(), os.getgid())
        self.assertEqual(outcome.observed, probe.OBSERVED_ERROR)

    def test_an_own_file_outside_the_state_directory_is_refused(self):
        state = self.root / "state"
        state.mkdir(parents=True, exist_ok=True)
        path = self.write_marker(self.root / "elsewhere.txt")
        outcome = probe._file_outcome_own(path, state, os.getuid(), os.getgid())
        self.assertEqual(outcome.observed, probe.OBSERVED_ERROR)

    def test_a_readable_sibling_file_is_an_isolation_breach(self):
        path = self.write_marker(self.root / "sibling.txt")
        witness = {"kind": "peer_probe_report", "sufficient": True}
        outcome = probe._file_outcome_peer(path, witness)
        self.assertEqual(outcome.observed, probe.OBSERVED_ALLOWED)
        case = probe._Case("file.peer.read", "file", "d", probe.OBSERVED_REFUSED)
        self.assertEqual(probe._status_for(case, outcome), probe.STATUS_FAIL)

    def test_a_denied_sibling_file_without_a_witness_is_unavailable(self):
        witness = {"kind": "none", "sufficient": False}
        with (
            mock.patch.object(probe, "_try_stat",
                              return_value={"ok": False, "errno": errno.EACCES,
                                            "errno_name": "EACCES"}),
            mock.patch.object(probe, "_try_read",
                              return_value={"readable": False, "errno": errno.EACCES,
                                            "errno_name": "EACCES"}),
        ):
            outcome = probe._file_outcome_peer(Path("/srv/peer/synthetic.txt"), witness)
        self.assertEqual(outcome.observed, probe.OBSERVED_REFUSED)
        case = probe._Case("file.peer.read", "file", "d", probe.OBSERVED_REFUSED)
        self.assertEqual(probe._status_for(case, outcome), probe.STATUS_UNAVAILABLE)
        self.assertIn("no independent witness", outcome.detail)

    def test_a_denied_sibling_file_with_a_witness_passes(self):
        witness = {"kind": "peer_probe_report", "sufficient": True}
        with (
            mock.patch.object(probe, "_try_stat",
                              return_value={"ok": False, "errno": errno.EACCES,
                                            "errno_name": "EACCES"}),
            mock.patch.object(probe, "_try_read",
                              return_value={"readable": False, "errno": errno.EACCES,
                                            "errno_name": "EACCES"}),
        ):
            outcome = probe._file_outcome_peer(Path("/srv/peer/synthetic.txt"), witness)
        case = probe._Case("file.peer.read", "file", "d", probe.OBSERVED_REFUSED)
        self.assertEqual(probe._status_for(case, outcome), probe.STATUS_PASS)

    def test_a_missing_sibling_file_is_unavailable_not_a_breach(self):
        witness = {"kind": "peer_probe_report", "sufficient": True}
        outcome = probe._file_outcome_peer(Path("/srv/peer/absent.txt"), witness)
        self.assertEqual(outcome.observed, probe.OBSERVED_UNAVAILABLE)
        case = probe._Case("file.peer.read", "file", "d", probe.OBSERVED_REFUSED)
        self.assertEqual(probe._status_for(case, outcome), probe.STATUS_UNAVAILABLE)


class ListenerWitnessTests(unittest.TestCase):
    def test_the_kernel_address_is_decoded_from_the_proc_table(self):
        self.assertEqual(probe._hex_to_ipv4("0100007F"), "127.0.0.1")
        self.assertEqual(probe._hex_to_ipv4("0200007F"), "127.0.0.2")
        self.assertEqual(probe._hex_to_ipv4("00000000"), "0.0.0.0")
        self.assertIsNone(probe._hex_to_ipv4("nothex"))

    def test_a_witness_must_cover_the_address_under_test(self):
        entries = ["127.0.0.1", "127.0.0.2", "127.0.0.3"]
        self.assertEqual(probe._matching_listen_entries(entries, "127.0.0.3"), ["127.0.0.3"])
        self.assertEqual(probe._matching_listen_entries(entries, "0.0.0.0"), entries)
        self.assertEqual(probe._matching_listen_entries(entries, "127.0.0.9"), [])

    def test_a_sibling_listener_is_not_a_witness_for_this_target(self):
        case = case_by_id("tcp.own_alias.gateway_port")
        listeners = {"own_gateway": {"bound": True, "kernel_listening": False,
                                     "kernel_matching_entries": [],
                                     "kernel_listen_entries": ["127.0.0.3"]}}
        with mock.patch.object(probe, "_connect",
                               return_value=(errno.EACCES, "refused_immediately")):
            outcome = probe._tcp_outcome(case, listeners, {}, frozenset({8765}), 1.0)
        self.assertFalse(outcome.witness["sufficient"])

    def test_a_refused_own_allowed_port_is_not_attributed_to_either_control(self):
        case = case_by_id("tcp.own_alias.gateway_port")
        listeners = {"own_gateway": {"bound": True, "kernel_listening": True,
                                     "kernel_matching_entries": ["127.0.0.2"]}}
        with mock.patch.object(probe, "_connect",
                               return_value=(errno.EACCES, "refused_immediately")):
            outcome = probe._tcp_outcome(case, listeners, {}, frozenset({8765}), 1.0)
        self.assertEqual(outcome.attribution, "UNDETERMINED")
        self.assertEqual(probe._status_for(case, outcome), probe.STATUS_FAIL)


class ListenerLifetimeTests(unittest.TestCase):
    def test_the_synthetic_listeners_are_still_running_when_the_matrix_runs(self):
        order: list[str] = []

        def fake_tcp_outcome(*args, **kwargs):
            order.append("matrix")
            return probe._Outcome(probe.OBSERVED_REFUSED, witness={"sufficient": False})

        with (
            mock.patch.object(probe, "load_profile", return_value=make_profile()),
            mock.patch.object(probe, "_identity_facts", return_value=_identity()),
            mock.patch.object(probe, "assert_root_service_cgroup"),
            mock.patch.object(probe, "assert_role_credential_isolation"),
            mock.patch.object(probe, "enforce_role_tcp_ports"),
            mock.patch.object(probe, "_spawn_listener",
                              return_value=(1, {"bound": True})),
            mock.patch.object(probe, "_terminate_children",
                              side_effect=lambda pids: order.append("terminate")),
            mock.patch.object(probe, "_connect",
                              return_value=(None, "connected")),
            mock.patch.object(probe, "_exec_probe",
                              return_value=("connected", None)),
            mock.patch.object(probe, "_tcp_outcome", side_effect=fake_tcp_outcome),
        ):
            probe._run_probe(_args())
        self.assertIn("matrix", order)
        self.assertIn("terminate", order)
        self.assertLess(order.index("matrix"), order.index("terminate"))


class PeerReportWitnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hermes-iso-peer-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def peer_report(self, role: str = "mmmeta", path: str = "/srv/mmmeta/synthetic.txt",
                    digest: str | None = None, status: str = probe.STATUS_PASS,
                    schema: str = probe.SCHEMA) -> Path:
        target = self.root / f"{role}.json"
        target.write_text(json.dumps({
            "schema": schema, "role": role, "status": "PASS",
            "own_file": {"path": path,
                         "sha256": digest or probe.SYNTHETIC_MARKER_SHA256,
                         "status": status},
        }), encoding="utf-8")
        return target

    def test_a_valid_peer_report_is_accepted(self):
        target = self.peer_report()
        report, reason = probe._load_peer_report(target, "mmmeta")
        self.assertIsNotNone(report)
        self.assertEqual(reason, "peer probe report accepted")

    def test_a_peer_report_for_the_wrong_role_is_rejected(self):
        target = self.peer_report(role="mmsecretary")
        report, reason = probe._load_peer_report(target, "mmmeta")
        self.assertIsNone(report)
        self.assertIn("different role", reason)

    def test_a_peer_report_with_a_foreign_digest_is_rejected(self):
        target = self.peer_report(digest="0" * 64)
        report, reason = probe._load_peer_report(target, "mmmeta")
        self.assertIsNone(report)
        self.assertIn("digest", reason)

    def test_a_peer_report_that_did_not_prove_its_own_file_is_rejected(self):
        target = self.peer_report(status=probe.STATUS_UNAVAILABLE)
        report, reason = probe._load_peer_report(target, "mmmeta")
        self.assertIsNone(report)
        self.assertIn("readable", reason)

    def test_a_foreign_schema_is_rejected(self):
        target = self.peer_report(schema="something.else.v1")
        report, reason = probe._load_peer_report(target, "mmmeta")
        self.assertIsNone(report)
        self.assertIn("schema", reason)

    def test_the_witness_requires_the_matching_sibling_path(self):
        target = self.peer_report(path="/srv/mmmeta/synthetic.txt")
        report, _ = probe._load_peer_report(target, "mmmeta")
        witness = probe._peer_witness(report, Path("/srv/mmmeta/other.txt"))
        self.assertFalse(witness["sufficient"])
        witness = probe._peer_witness(report, Path("/srv/mmmeta/synthetic.txt"))
        self.assertTrue(witness["sufficient"])

    def test_no_peer_report_means_no_witness(self):
        witness = probe._peer_witness(None, Path("/srv/mmmeta/synthetic.txt"))
        self.assertFalse(witness["sufficient"])


class ReportTests(unittest.TestCase):
    def _report(self, statuses: dict[str, str]) -> dict:
        records = {}
        for case in probe._case_catalog():
            status = statuses.get(case.case_id, probe.STATUS_PASS)
            records[case.case_id] = {
                "case_id": case.case_id, "dimension": case.dimension,
                "description": case.description, "selected": True,
                "expected": case.expected, "observed": probe.OBSERVED_ALLOWED,
                "status": status, "errno": None, "errno_name": None, "symptom": None,
                "attribution": "", "attribution_basis": "", "witness": {},
                "detail": "", "target": {},
            }
        return probe._build_report(
            make_profile(), "mmsecretary", "mmmeta", _identity(), [], records,
            set(records), frozenset({8765, 8766}), frozenset({8765, 8766, 18651}),
            45151, _args(), witnesses={}, listeners={},
        )

    def test_an_unavailable_case_makes_the_whole_result_incomplete(self):
        report = self._report({"tcp.own_alias.gateway_port": probe.STATUS_UNAVAILABLE})
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertFalse(report["qualified"])

    def test_a_not_run_case_makes_the_whole_result_incomplete(self):
        report = self._report({"file.peer.read": probe.STATUS_NOT_RUN})
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertFalse(report["qualified"])

    def test_a_failed_case_makes_the_whole_result_fail(self):
        report = self._report({"file.peer.read": probe.STATUS_FAIL})
        self.assertEqual(report["status"], "FAIL")
        self.assertFalse(report["qualified"])

    def test_all_passing_cases_produce_a_qualified_result(self):
        report = self._report({})
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["qualified"])
        self.assertTrue(report["context_fingerprint"])

    def test_the_fingerprint_binds_the_selected_matrix(self):
        first = self._report({})
        records = {key: dict(value) for key, value in first["matrix"] and
                   {r["case_id"]: r for r in first["matrix"]}.items()}
        records["file.peer.read"]["selected"] = False
        records["file.peer.read"]["status"] = probe.STATUS_NOT_RUN
        second = probe._build_report(
            make_profile(), "mmsecretary", "mmmeta", _identity(), [], records,
            {key for key, value in records.items() if value["selected"]},
            frozenset({8765, 8766}), frozenset({8765, 8766, 18651}),
            45151, _args(), witnesses={}, listeners={},
        )
        self.assertNotEqual(first["context_fingerprint"], second["context_fingerprint"])

    def test_the_report_declares_the_fixture_scope(self):
        report = self._report({})
        self.assertTrue(report["scope"]["prepared_fixture"])
        self.assertFalse(report["scope"]["final_production_configuration"])
        self.assertIn("hermes-egress.service", " ".join(report["limitations"]))

    def test_the_report_records_the_effective_cgroup_and_nss_identity(self):
        report = self._report({})
        identity = report["context"]["identity"]
        self.assertEqual(identity["expected_cgroup"] if "expected_cgroup" in identity
                         else identity["effective_cgroup_expected"],
                         "/system.slice/hermes-runtime-mmsecretary.service")
        self.assertIn("nss_uid", identity)

    def test_the_private_path_facts_are_recorded(self):
        report = self._report({})
        self.assertIn("ancestors", report["private_paths"]["state_dir"])
        self.assertIn("ancestors", report["private_paths"]["secrets_parent"])

    def test_the_exit_code_reflects_the_result(self):
        self.assertEqual(probe._exit_code(self._report({})), 0)
        self.assertEqual(probe._exit_code(
            self._report({"file.peer.read": probe.STATUS_FAIL})), probe.POLICY_EXIT)
        self.assertEqual(probe._exit_code(
            self._report({"file.peer.read": probe.STATUS_NOT_RUN})), probe.CONFIG_EXIT)


class SelectionTests(unittest.TestCase):
    def test_the_default_selection_is_the_whole_matrix(self):
        self.assertEqual(probe._selected_cases(""),
                         {case.case_id for case in probe._case_catalog()})

    def test_an_explicit_subset_is_honoured(self):
        self.assertEqual(probe._selected_cases("file.own.read,file.peer.read"),
                         {"file.own.read", "file.peer.read"})

    def test_an_unknown_case_id_is_refused(self):
        with self.assertRaises(ValueError):
            probe._selected_cases("not.a.case")

    def test_the_denied_port_must_not_be_inside_the_allowed_set(self):
        args = _args()
        args.denied_port = 8765
        with (
            mock.patch.object(probe, "load_profile", return_value=make_profile()),
            mock.patch.object(probe, "_identity_facts", return_value=_identity()),
        ):
            self.assertEqual(probe._run_probe(args), probe.CONFIG_EXIT)

    def test_the_denied_port_must_not_collide_with_the_sibling_role(self):
        args = _args()
        args.denied_port = 8865
        with (
            mock.patch.object(probe, "load_profile", return_value=make_profile()),
            mock.patch.object(probe, "_identity_facts", return_value=_identity()),
        ):
            self.assertEqual(probe._run_probe(args), probe.CONFIG_EXIT)

    def test_a_profile_role_mismatch_is_refused(self):
        args = _args()
        with mock.patch.object(probe, "load_profile", return_value=make_profile("mmmeta")):
            self.assertEqual(probe._run_probe(args), probe.CONFIG_EXIT)

    def test_a_drifted_port_profile_is_reported_as_a_failure(self):
        outcome = probe._profile_ports_outcome(
            make_profile(gateway_port=9999), "mmsecretary")
        self.assertEqual(outcome.observed, probe.OBSERVED_ERROR)

    def test_the_matching_port_profile_is_reported_as_observed(self):
        outcome = probe._profile_ports_outcome(make_profile(), "mmsecretary")
        self.assertEqual(outcome.observed, probe.OBSERVED_ALLOWED)


class CliTests(unittest.TestCase):
    def test_listing_the_cases_is_side_effect_free(self):
        completed = subprocess.run(
            [sys.executable, "-P", "-m", "integrations.hermes_runtime.isolation_probe",
             "--list-cases"],
            cwd=REPO, env={"PATH": os.defpath, "PYTHONPATH": str(REPO),
                           "PYTHONDONTWRITEBYTECODE": "1"},
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30,
            close_fds=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["schema"], probe.SCHEMA)
        self.assertIn("tcp.own_alias.denied_port", payload["cases"])

    def test_a_missing_profile_argument_is_refused(self):
        with self.assertRaises(SystemExit):
            probe._parse_args(["--role", "mmsecretary"])

    def test_an_unknown_case_id_is_refused_at_the_cli(self):
        args = _args()
        args.only = "not.a.case"
        self.assertEqual(probe._run_probe(args), probe.CONFIG_EXIT)


def _identity() -> dict:
    return {
        "role": "mmsecretary", "nss_user": "mmsecretary", "nss_uid": 60001,
        "nss_primary_gid": 60001, "nss_gid": 60001,
        "nss_home": "/home/mmsecretary", "process_uid": 60001, "process_euid": 60001,
        "process_gid": 60001, "process_egid": 60001, "process_groups": [60001],
        "uid_is_nss_uid": True, "gid_is_nss_gid": True,
        "no_extra_supplementary_groups": True,
        "effective_cgroup_expected": "/system.slice/hermes-runtime-mmsecretary.service",
        "effective_cgroup_observed": "/system.slice/hermes-runtime-mmsecretary.service",
        "effective_cgroup_raw": ["0::/system.slice/hermes-runtime-mmsecretary.service"],
    }


def _args() -> argparse.Namespace:
    return argparse.Namespace(
        profile=Path("/srv/hermes/profile.yaml"), role="mmsecretary",
        own_file=Path("/srv/hermes/mmsecretary/state/synthetic.txt"),
        peer_file=Path("/srv/hermes/mmmeta/state/synthetic.txt"),
        peer_report=None, denied_port=None, report=None,
        connect_timeout=1.0, only="", list_cases=False,
    )


if __name__ == "__main__":
    unittest.main()
