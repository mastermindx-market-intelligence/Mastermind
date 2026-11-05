"""Offline regression tests for the candidate observation diagnostic overlay."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "ops/native_fabric/quota_continuity"


def load(name, path):
    delivery = types.ModuleType("artifact_delivery")
    reader = types.ModuleType("artifact_reader")
    reader.canonical = lambda value: json.dumps(value, sort_keys=True,
                                                 separators=(",", ":")).encode()
    reader.strict_json = json.loads
    prior = {key: sys.modules.get(key) for key in ("artifact_delivery", "artifact_reader")}
    sys.modules["artifact_delivery"] = delivery
    sys.modules["artifact_reader"] = reader
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        for key, value in prior.items():
            if value is None:
                del sys.modules[key]
            else:
                sys.modules[key] = value


candidate = load("candidate_run_observation_delivery", NATIVE / "candidate/run_observation_delivery.py")
source = load("source_run_observation_delivery", NATIVE / "source/run_observation_delivery.py")


class Chain:
    fd = 1
    def __init__(self): self.closed = 0
    def verify(self): pass
    def close(self): self.closed += 1


class Diagnostics(unittest.TestCase):
    def configure(self, module, *, transport=None, validate=None, publish=None,
                  qualify=None, reserve=None):
        chain = Chain()
        evidence = {"ssh_alias": "fixture", "evidence_sha256": {"observer": "a" * 64}}
        patches = [
            mock.patch.object(module, "qualify", side_effect=qualify or (lambda *_a, **_k: evidence)),
            mock.patch.object(module.delivery, "reserve_destination", side_effect=reserve or (lambda _d: chain), create=True),
            mock.patch.object(module.delivery, "write_exclusive", create=True),
            mock.patch.object(module.delivery, "transport", side_effect=transport or (lambda *_a, **_k: b"response"), create=True),
            mock.patch.object(module, "validate_response", side_effect=validate or (lambda *_a: {"status": "observed"})),
            mock.patch.object(module.delivery, "publish_receipt", side_effect=publish or (lambda *_a, **_k: None), create=True),
            mock.patch.object(module.time, "time", return_value=1.0),
        ]
        return chain, patches

    def run_observe(self, module, **kwargs):
        chain, patches = self.configure(module, **kwargs)
        with contextlib.ExitStack() as stack:
            for patch in patches: stack.enter_context(patch)
            receipt = module.observe({"run_id": "fixture"}, "destination")
        return receipt, chain

    def main_result(self, module, request_error=None, observe_error=None):
        out, err = io.StringIO(), io.StringIO()
        request = {"run_id": "fixture"}
        with mock.patch.object(module, "request_for", side_effect=request_error or (lambda *_a, **_k: request)), \
             mock.patch.object(module, "observe", side_effect=observe_error or (lambda *_a: {"state": "OBSERVED"})), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = module.main(["fixture", "--root", "root", "--destination", "dest"])
        return rc, out.getvalue(), err.getvalue()

    def boundary_main(self, module, fault="normal"):
        """Run actual main -> observe against inert incumbent boundaries."""
        calls, out, err = [], io.StringIO(), io.StringIO()
        evidence = {"ssh_alias": "fixture", "evidence_sha256": {"observer": "a" * 64}}
        chain = Chain()
        request = {"run_id": "fixture"}
        def qualify(*_a, **_k):
            calls.append("qualify")
            if fault == "qualification" and len(calls) == 1: raise ValueError("secret")
            if fault == "pretransportrevalidation" and calls.count("qualify") == 2: raise ValueError("secret")
            if fault == "postresponserevalidation" and calls.count("qualify") == 3: raise ValueError("secret")
            if fault == "publicationcallback" and calls.count("qualify") == 4: raise ValueError("secret")
            return evidence
        def reserve(_destination):
            calls.append("reserve")
            if fault == "destinationreservation": raise ValueError("secret")
            return chain
        def write(*_a):
            calls.append("write")
            if fault == "intentwrite": raise ValueError("secret")
        def transport(*_a, **_k):
            calls.append("transport")
            if fault == "transport": raise ValueError("secret")
            return b"response"
        def validate(*_a):
            calls.append("validate")
            if fault == "responsevalidation": raise ValueError("secret")
            return {"status": "unavailable" if fault == "unavailable" else "observed"}
        def publish(_chain, _receipt, _files, *, verify_source):
            calls.append("publish")
            if fault == "publicationcallback": verify_source()
            if fault == "publication": raise ValueError("secret")
        if fault == "cleanup":
            def close():
                chain.closed += 1
                raise ValueError("secret")
            chain.close = close
        with mock.patch.object(module, "request_for", return_value=request), \
             mock.patch.object(module, "qualify", side_effect=qualify), \
             mock.patch.object(module.delivery, "reserve_destination", side_effect=reserve, create=True), \
             mock.patch.object(module.delivery, "write_exclusive", side_effect=write, create=True), \
             mock.patch.object(module.delivery, "transport", side_effect=transport, create=True), \
             mock.patch.object(module, "validate_response", side_effect=validate), \
             mock.patch.object(module.delivery, "publish_receipt", side_effect=publish, create=True), \
             mock.patch.object(module.time, "time", return_value=1.0), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = module.main(["fixture", "--root", "root", "--destination", "dest"])
        return rc, out.getvalue(), err.getvalue(), calls

    def diagnostic(self, text):
        line = text.splitlines()[-1]
        self.assertRegex(line, r"^run_observation_delivery\.py: diagnostic phase=[a-z_]+ category=[a-z_]+ last_phase=[a-z_]+ last_category=[a-z_]+ transport=(not_attempted|attempted_unconfirmed|response_received)$")
        return dict(field.split("=", 1) for field in line.split()[2:])

    def test_candidate_is_an_overlay_and_source_preimage_is_unchanged(self):
        self.assertEqual(__import__("hashlib").sha256((NATIVE / "source/run_observation_delivery.py").read_bytes()).hexdigest(),
                         "db54aa15630e29535980e0fccb406c3904cc7df92c66d17ec520f40d4fd5447b")
        self.assertNotEqual((NATIVE / "candidate/run_observation_delivery.py").read_bytes(),
                            (NATIVE / "source/run_observation_delivery.py").read_bytes())

    def test_success_preserves_stdout_rc_and_strict_json(self):
        candidate_result = self.main_result(candidate)
        source_result = self.main_result(source)
        self.assertEqual(candidate_result[:2], source_result[:2])
        self.assertEqual(candidate_result[0], 0)
        self.assertEqual(json.loads(candidate_result[1])["state"], "OBSERVED")
        fields = self.diagnostic(candidate_result[2])
        self.assertEqual(fields["transport"], "not_attempted")

    def test_refusal_and_state_reset_do_not_leak(self):
        refused = self.main_result(candidate, request_error=candidate.ObservationScopeNotAdmitted())
        self.assertEqual((refused[0], refused[1]), (75, '{"state":"REFUSED","reason":"observation_scope_not_admitted"}\n'))
        self.assertEqual(self.diagnostic(refused[2])["category"], "scope_refusal")
        clean = self.main_result(candidate)
        self.assertEqual(self.diagnostic(clean[2])["category"], "none")

    def test_transport_states_and_inner_failure_survive_publication_failure(self):
        chain, patches = self.configure(candidate, transport=ValueError("secret\n" + "x" * 10000),
                                        publish=OSError("late"))
        token = candidate._diagnostic_start()
        try:
            with contextlib.ExitStack() as stack:
                for patch in patches: stack.enter_context(patch)
                with self.assertRaises(OSError):
                    candidate.observe({"run_id": "fixture"}, "destination")
            state = candidate._DIAGNOSTIC.get()
            self.assertEqual((state["phase"], state["category"]), ("transport", "value_error"))
            self.assertEqual((state["last_phase"], state["last_category"]), ("publication", "os_error"))
        finally:
            candidate._DIAGNOSTIC.reset(token)
        self.assertEqual(chain.closed, 1)

        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(candidate, "request_for", return_value={"run_id": "fixture"}), \
             mock.patch.object(candidate, "observe", side_effect=ValueError("top-secret")), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(candidate.main(["fixture", "--root", "root", "--destination", "dest"]), 75)
        self.assertNotIn("top-secret", err.getvalue())
        self.assertEqual(self.diagnostic(err.getvalue())["phase"], "request")

    def test_observe_records_transport_and_response_without_extra_calls(self):
        calls = []
        def transport(*_a, **_k):
            calls.append("transport")
            return b"response"
        receipt, chain = self.run_observe(candidate, transport=transport)
        self.assertEqual(receipt["state"], "OBSERVED")
        self.assertEqual(calls, ["transport"])
        self.assertEqual(chain.closed, 1)

    def test_diagnostic_sink_failures_do_not_change_result(self):
        for write_error, flush_error in ((OSError(), None), (None, OSError())):
            with self.subTest(write_error=write_error is not None):
                stderr = types.SimpleNamespace(
                    write=mock.Mock(side_effect=write_error),
                    flush=mock.Mock(side_effect=flush_error),
                )
                out = io.StringIO()
                with mock.patch.object(candidate, "request_for", return_value={"run_id": "fixture"}), \
                     mock.patch.object(candidate, "observe", return_value={"state": "OBSERVED"}), \
                     mock.patch.object(sys, "stderr", stderr), contextlib.redirect_stdout(out):
                    self.assertEqual(candidate.main(["fixture", "--root", "root", "--destination", "dest"]), 0)
                self.assertEqual(out.getvalue(), '{"state":"OBSERVED"}\n')

        out = io.StringIO()
        with mock.patch.object(candidate, "request_for", side_effect=candidate.ObservationScopeNotAdmitted()), \
             mock.patch.object(sys, "stderr", stderr), contextlib.redirect_stdout(out):
            self.assertEqual(candidate.main(["fixture", "--root", "root", "--destination", "dest"]), 75)
        self.assertEqual(out.getvalue(), '{"state":"REFUSED","reason":"observation_scope_not_admitted"}\n')

        with mock.patch.object(candidate, "request_for", return_value={"run_id": "fixture"}), \
             mock.patch.object(candidate, "observe", side_effect=KeyboardInterrupt()), \
             mock.patch.object(sys, "stderr", stderr):
            with self.assertRaises(KeyboardInterrupt):
                candidate.main(["fixture", "--root", "root", "--destination", "dest"])

    def test_deduplication_retains_exception_identity_not_reusable_ids(self):
        token = candidate._diagnostic_start()
        try:
            first = ValueError("first")
            second = ValueError("second")
            candidate._diagnostic_phase("transport")
            candidate._diagnostic_failure(first)
            candidate._diagnostic_phase("publication")
            candidate._diagnostic_failure(second)
            state = candidate._DIAGNOSTIC.get()
            self.assertIs(state["seen"][0], first)
            self.assertIs(state["seen"][1], second)
            self.assertEqual((state["last_phase"], state["last_category"]),
                             ("publication", "value_error"))
        finally:
            candidate._DIAGNOSTIC.reset(token)

    def test_real_main_candidate_matches_preimage_boundary_matrix(self):
        faults = ("normal", "qualification", "destinationreservation", "intentwrite",
                  "pretransportrevalidation", "transport", "responsevalidation",
                  "postresponserevalidation", "publication", "publicationcallback",
                  "cleanup", "unavailable")
        for fault in faults:
            with self.subTest(fault=fault):
                expected = self.boundary_main(source, fault)
                actual = self.boundary_main(candidate, fault)
                self.assertEqual(actual[0:2], expected[0:2])
                self.assertEqual(actual[3], expected[3])
                diagnostic = self.diagnostic(actual[2])
                if fault in {"qualification", "destinationreservation"}:
                    self.assertEqual(diagnostic["phase"], fault)
                self.assertNotIn("secret", actual[2])

    def test_closed_categories_and_malicious_values_are_bounded(self):
        expected = {
            candidate.ObservationScopeNotAdmitted(): "scope_refusal", OSError(): "os_error",
            ValueError(): "value_error", TypeError(): "type_error", KeyError(): "key_error",
            RecursionError(): "recursion_error", candidate.subprocess.SubprocessError(): "subprocess_error",
            candidate.sqlite3.Error(): "sqlite_error", KeyboardInterrupt(): "other_error",
        }
        self.assertEqual({candidate._diagnostic_category(exc) for exc in expected}, set(expected.values()))
        dangerous = "SECRET\\n/path/run-id=" + "x" * 20000
        rc, stdout, stderr = self.main_result(candidate, observe_error=ValueError(dangerous))
        self.assertEqual((rc, stdout), (75, '{"state":"REFUSED","reason":"original_run_observation_unconfirmed"}\n'))
        self.assertLessEqual(len(stderr), 220)
        self.assertNotIn("SECRET", stderr)
        self.assertNotIn("/path", stderr)

    def test_phase_fault_seams_preserve_existing_exception_and_cleanup(self):
        evidence = {"ssh_alias": "fixture", "evidence_sha256": {"observer": "a" * 64}}
        cases = {
            "qualification": {"qualify": ValueError("secret")},
            "destinationreservation": {"reserve": ValueError("secret")},
            "intentwrite": {"write": ValueError("secret")},
            "transport": {"transport": ValueError("secret")},
            "responsevalidation": {"validate": ValueError("secret")},
            "publication": {"publish": ValueError("secret")},
        }
        for phase, fault in cases.items():
            with self.subTest(phase=phase):
                chain = Chain()
                qualify = fault.get("qualify", lambda *_a, **_k: evidence)
                reserve = fault.get("reserve", lambda _d: chain)
                token = candidate._diagnostic_start()
                try:
                    with mock.patch.object(candidate, "qualify", side_effect=qualify), \
                         mock.patch.object(candidate.delivery, "reserve_destination", side_effect=reserve, create=True), \
                         mock.patch.object(candidate.delivery, "write_exclusive", side_effect=fault.get("write"), create=True), \
                         mock.patch.object(candidate.delivery, "transport", side_effect=fault.get("transport", lambda *_a, **_k: b"response"), create=True), \
                         mock.patch.object(candidate, "validate_response", side_effect=fault.get("validate", lambda *_a: {"status": "observed"})), \
                         mock.patch.object(candidate.delivery, "publish_receipt", side_effect=fault.get("publish", lambda *_a, **_k: None), create=True), \
                         mock.patch.object(candidate.time, "time", return_value=1.0):
                        if phase in {"qualification", "destinationreservation", "intentwrite", "publication"}:
                            with self.assertRaises(ValueError):
                                candidate.observe({"run_id": "fixture"}, "destination")
                        else:
                            self.assertEqual(candidate.observe({"run_id": "fixture"}, "destination")["state"], "UNAVAILABLE")
                    state = candidate._DIAGNOSTIC.get()
                    if phase not in {"qualification", "destinationreservation"}:
                        self.assertEqual(state["phase"], phase)
                finally:
                    candidate._DIAGNOSTIC.reset(token)
                if phase not in {"qualification", "destinationreservation"}:
                    self.assertEqual(chain.closed, 1)

    def test_pre_and_post_revalidation_and_cleanup_fault_phases(self):
        evidence = {"ssh_alias": "fixture", "evidence_sha256": {"observer": "a" * 64}}
        for target, values in (("pretransportrevalidation", [evidence, ValueError("x")]),
                               ("postresponserevalidation", [evidence, evidence, ValueError("x")])):
            with self.subTest(target=target):
                chain = Chain()
                token = candidate._diagnostic_start()
                try:
                    with mock.patch.object(candidate, "qualify", side_effect=values), \
                         mock.patch.object(candidate.delivery, "reserve_destination", return_value=chain, create=True), \
                         mock.patch.object(candidate.delivery, "write_exclusive", create=True), \
                         mock.patch.object(candidate.delivery, "transport", return_value=b"response", create=True), \
                         mock.patch.object(candidate, "validate_response", return_value={"status": "observed"}), \
                         mock.patch.object(candidate.delivery, "publish_receipt", create=True), \
                         mock.patch.object(candidate.time, "time", return_value=1.0):
                        receipt = candidate.observe({"run_id": "fixture"}, "destination")
                    self.assertEqual(receipt["state"], "UNAVAILABLE")
                    self.assertEqual(candidate._DIAGNOSTIC.get()["phase"], target)
                finally:
                    candidate._DIAGNOSTIC.reset(token)
                self.assertEqual(chain.closed, 1)

        class BrokenChain(Chain):
            def close(self):
                super().close()
                raise ValueError("secret")
        chain = BrokenChain()
        token = candidate._diagnostic_start()
        try:
            with mock.patch.object(candidate, "qualify", return_value=evidence), \
                 mock.patch.object(candidate.delivery, "reserve_destination", return_value=chain, create=True), \
                 mock.patch.object(candidate.delivery, "write_exclusive", create=True), \
                 mock.patch.object(candidate.delivery, "transport", return_value=b"response", create=True), \
                 mock.patch.object(candidate, "validate_response", return_value={"status": "observed"}), \
                 mock.patch.object(candidate.delivery, "publish_receipt", create=True), \
                 mock.patch.object(candidate.time, "time", return_value=1.0):
                with self.assertRaises(ValueError):
                    candidate.observe({"run_id": "fixture"}, "destination")
            self.assertEqual(candidate._DIAGNOSTIC.get()["phase"], "cleanup")
        finally:
            candidate._DIAGNOSTIC.reset(token)

    def test_publication_callback_failure_precedes_publisher_wrapper(self):
        evidence = {"ssh_alias": "fixture", "evidence_sha256": {"observer": "a" * 64}}
        chain = Chain()
        calls = [0]
        def qualify(*_a, **_k):
            calls[0] += 1
            if calls[0] == 4:
                raise OSError("secret callback path")
            return evidence
        def publisher(_chain, _receipt, _files, *, verify_source):
            try:
                verify_source()
            except Exception:
                raise ValueError("publisher wrapper")
        token = candidate._diagnostic_start()
        try:
            with mock.patch.object(candidate, "qualify", side_effect=qualify), \
                 mock.patch.object(candidate.delivery, "reserve_destination", return_value=chain, create=True), \
                 mock.patch.object(candidate.delivery, "write_exclusive", create=True), \
                 mock.patch.object(candidate.delivery, "transport", return_value=b"response", create=True), \
                 mock.patch.object(candidate, "validate_response", return_value={"status": "observed"}), \
                 mock.patch.object(candidate.delivery, "publish_receipt", side_effect=publisher, create=True), \
                 mock.patch.object(candidate.time, "time", return_value=1.0):
                with self.assertRaises(ValueError):
                    candidate.observe({"run_id": "fixture"}, "destination")
            state = candidate._DIAGNOSTIC.get()
            self.assertEqual((state["phase"], state["category"]),
                             ("publicationrevalidation", "os_error"))
            self.assertEqual((state["last_phase"], state["last_category"]),
                             ("publication", "value_error"))
        finally:
            candidate._DIAGNOSTIC.reset(token)


if __name__ == "__main__":
    unittest.main()
